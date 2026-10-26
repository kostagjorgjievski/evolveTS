"""Two process-isolated research lanes with one durable budget owner.

One scout can discover ahead while one reproducer works. Reservations include
in-flight sessions in daily admission; the parent alone writes the shared ledger.
Workers retain the existing own-job leases, official grading and provider slots.
"""
import datetime
import contextlib
import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import psutil

from .investigations import Investigations
from .models import atomic_write, utc


def write(path, value):
    atomic_write(path, json.dumps(value, indent=2))


def alive(entry):
    try:
        proc = psutil.Process(entry['pid'])
        return (abs(proc.create_time()-entry['create_time']) < .01
                and 'scripts.autoresearch_seeder.parallel_service' in proc.cmdline()
                and entry['session_dir'] in proc.cmdline()
                and not proc.status() == psutil.STATUS_ZOMBIE)
    except (psutil.Error, KeyError):
        return False


def role_of(root, record, task):
    if record['consumed']['sessions'] or record['checkpoint'].get('start_role') == 'reproducer':
        return 'reproducer'
    job = Path(root)/'jobs/autoresearch-seeder'/task/record['id']
    if (job/'private/research.sqlite').exists():
        from .store import ResearchStore
        store = ResearchStore(job/'private/research.sqlite')
        try:
            if store.list_hypotheses():
                return 'reproducer'
        finally:
            store.close()
    return 'scout'


def select_candidate(root, config, active):
    """No work is invented here: broad topics and public follow-ups stay model-led."""
    from .service import enqueue_public_follow_up
    agenda = Investigations(Path(root)/'investigations.sqlite')
    try:
        records = agenda.list()
        busy_ids = {a['investigation'] for a in active.values()}
        def cooldown_ready(record):
            checkpoint=record.get('checkpoint',{})
            if checkpoint.get('job_stage')!='retry_wait':return True
            state=Path(checkpoint['job'])/'job.json'
            job=json.loads(state.read_text())
            return job.get('retry',{}).get('eligible_utc','')<=utc()
        candidates = [r for r in records if r['status'] in ('queued', 'active')
                      and agenda._budget_remaining(r) and r['id'] not in busy_ids
                      and cooldown_ready(r)]
        for role in ('reproducer', 'scout'):
            if role not in active:
                for record in candidates:
                    if role_of(root, record, config['task']) == role:
                        return role, record
        if 'scout' in active:
            return None
        # Backpressure: at most one completed scout waits for the reproducer.
        if any(role_of(root, r, config['task']) == 'reproducer' for r in candidates):
            return None
        item = enqueue_public_follow_up(root, config, agenda, records)
        if item:
            return ('reproducer', item) if 'reproducer' not in active else None
        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        topics = config.get('topics', [])
        seen = {r['topic'] for r in records if r['created_utc'].startswith(today)}
        topic = next((t for t in topics if t not in seen), None)
        origin = 'agenda'
        if topic is None and topics and config.get('service', {}).get('continuous_discovery'):
            prefix = 'discovery_sweep:' + today + ':'
            index = sum(r['origin'].startswith(prefix) for r in records)
            topic = (topics[index % len(topics)] + '\nConsult shared public knowledge and negative results first. '
                     'Choose a distinct source-backed direction; do not repeat certified portfolios '
                     'or reopen budget-exhausted work under a new identity.')
            origin = prefix + str(index)
        if topic:
            return 'scout', agenda.create(topic, origin=origin,
                         budgets=config.get('agenda', {}).get('default_budgets'))
        return None
    finally:
        agenda.close()


class ParallelOwner:
    def __init__(self, root, config):
        self.root = Path(root)
        self.config = config
        self.path = self.root/'parallel-state.json'
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
        else:
            ledger = self.root/'service-ledger.json'
            self.state = {'ledger': json.loads(ledger.read_text()) if ledger.exists() else {},
                          'active': {}, 'serial': 0}

    def save(self):
        # This snapshot is authoritative on restart; ledger is a status mirror.
        write(self.path, self.state)
        write(self.root/'service-ledger.json', self.state['ledger'])

    def reconcile(self, is_alive=alive):
        for role, entry in list(self.state['active'].items()):
            work = Path(entry['session_dir'])
            result = work/'result.json'
            identity = work/'identity.json'
            if 'pid' not in entry and identity.exists():
                entry.update(json.loads(identity.read_text()))
                self.save()
            if not result.exists() and is_alive(entry):
                # Adopt a known surviving child only after durable reservation.
                (work/'admitted').touch(exist_ok=True)
                continue
            if not result.exists() and 'pid' not in entry and time.time()-entry['created_epoch'] < 30:
                continue
            agenda = Investigations(self.root/'investigations.sqlite')
            try:
                record = agenda.get(entry['investigation'])
            finally:
                agenda.close()
            if result.exists():
                outcome = json.loads(result.read_text())
            else:
                outcome = {'ok': False, 'error': 'Worker interrupted; own job retained'}
            after = record['consumed']
            before = entry['before']
            seconds = max(0, after['model_seconds']-before['model_seconds'])
            # An abruptly killed worker may not have flushed agenda accounting.
            # Keep its full reservation charged until its own recovery accounts it.
            if not outcome['ok'] and seconds == 0:
                seconds = entry['reserved_seconds']
            used = self.state['ledger'][entry['day']]
            used['model_seconds'] += seconds-entry['reserved_seconds']
            used['usd'] += max(0, after['usd']-before['usd'])
            entry.update(outcome=outcome, actual_model_seconds=seconds, finished_utc=utc())
            write(work/'settled.json', entry)
            del self.state['active'][role]
            if not outcome['ok']:
                (self.root/'PAUSE').write_text('Parallel worker failed; inspect preserved session result\n')
            self.save()

    def admit(self, role, record, launcher=None):
        lock_path = self.config.get('service', {}).get('budget_group_lock')
        with contextlib.ExitStack() as stack:
            if lock_path:
                path = Path(lock_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                lock = stack.enter_context(path.open('a'))
                fcntl.flock(lock, fcntl.LOCK_EX)
            return self._admit(role, record, launcher)

    def _admit(self, role, record, launcher=None):
        if role not in ('scout', 'reproducer'):
            return False
        day = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        used = self.state['ledger'].setdefault(day, {'sessions': 0, 'model_seconds': 0., 'usd': 0.})
        limits = self.config['budgets']
        combined = dict(used)
        for peer in self.config.get('service', {}).get('budget_group_roots', []):
            peer = Path(peer).resolve()
            if peer == self.root.resolve():
                continue
            state = peer/'parallel-state.json'
            ledger = peer/'service-ledger.json'
            data = (json.loads(state.read_text())['ledger'] if state.exists()
                    else json.loads(ledger.read_text()) if ledger.exists() else {})
            for key in combined:
                combined[key] += data.get(day, {}).get(key, 0)
        remaining = limits['daily_model_seconds']-combined['model_seconds']
        if (role in self.state['active'] or combined['sessions'] >= limits['daily_sessions']
                or remaining <= 10 or combined['usd'] >= limits['daily_reported_usd']):
            return False
        if any(e['investigation'] == record['id'] for e in self.state['active'].values()):
            return False
        seconds = min(limits['session_seconds'], remaining-10,
                      record['budgets']['max_model_seconds']-record['consumed']['model_seconds'])
        if seconds <= 0:
            return False
        self.state['serial'] += 1
        work = self.root/'parallel-sessions'/(str(self.state['serial'])+'-'+uuid.uuid4().hex[:8])
        work.mkdir(parents=True, exist_ok=False)
        runtime = {**self.config, 'root': str(self.root),
                   'budgets': {**limits, 'session_seconds': seconds}}
        write(work/'runtime.json', runtime)
        entry = {'investigation': record['id'], 'role': role, 'day': day,
                 'before': record['consumed'], 'reserved_seconds': seconds+10,
                 'created_epoch': time.time(), 'started_utc': utc(), 'session_dir': str(work)}
        used['sessions'] += 1
        used['model_seconds'] += entry['reserved_seconds']
        self.state['active'][role] = entry
        self.save()  # reserve BEFORE a child can make a paid call
        if launcher is None:
            def launcher(work, record):
                log = (work/'worker.log').open('ab', buffering=0)
                try:
                    proc = subprocess.Popen([sys.executable, '-m', __name__, str(work), record['id']],
                        cwd=str(Path(__file__).resolve().parents[2]), stdin=subprocess.DEVNULL,
                        stdout=log, stderr=log, start_new_session=True)
                finally:
                    log.close()
                return {'pid': proc.pid, 'create_time': psutil.Process(proc.pid).create_time()}
        try:
            entry.update(launcher(work, record))
            self.save()
            (work/'admitted').touch()
        except BaseException:
            # Keep reservation for identity/result reconciliation, never blind-retry.
            raise
        return True

    def tick(self):
        self.reconcile()
        for marker, state in [('STOP', 'stopped'), ('PAUSE', 'paused')]:
            if (self.root/marker).exists():
                return state
        if shutil.disk_usage(self.root).free < self.config['service'].get('min_free_gib', 4)*2**30:
            return 'resource_wait'
        for _ in range(2):
            selected = select_candidate(self.root, self.config, self.state['active'])
            if selected is None or not self.admit(*selected):
                break
        return 'running' if self.state['active'] else 'idle_or_budget_wait'


def worker(work, investigation):
    from .knowledge import KnowledgeBase
    from .research_runtime import run_materialized_investigation
    work = Path(work)
    write(work/'identity.json', {'pid': os.getpid(), 'create_time': psutil.Process().create_time()})
    for _ in range(300):
        if (work/'admitted').exists():
            break
        time.sleep(.1)
    else:
        return  # no durable admission, no provider calls
    config = json.loads((work/'runtime.json').read_text())
    agenda = Investigations(Path(config['root'])/'investigations.sqlite')
    knowledge = KnowledgeBase(Path(config['root'])/'knowledge.sqlite')
    try:
        record = agenda.get(investigation)
        updated = run_materialized_investigation(agenda, record, knowledge, config)
        write(work/'result.json', {'ok': True, 'status': updated['status']})
    except BaseException as error:
        write(work/'result.json', {'ok': False, 'error_class': type(error).__name__,
                                  'error': str(error)[:2000]})
        raise
    finally:
        agenda.close()
        knowledge.close()


def serve_parallel_locked(root, config, config_path=None):
    """Called only while the ordinary service owns its exclusive root lock."""
    from .service import validate_service, totals
    owner = ParallelOwner(root, config)
    stop = False
    def finish(signum, frame):
        nonlocal stop
        stop = True  # drain saved sessions, never kill a productive child
    signal.signal(signal.SIGTERM, finish)
    signal.signal(signal.SIGINT, finish)
    while True:
        if config_path:
            updated = validate_service(json.loads(Path(config_path).read_text()))
            if updated['task'] != config['task'] or updated.get('task_root') != config.get('task_root'):
                raise ValueError('Cannot change task identity')
            owner.config = updated
        if stop:
            owner.reconcile()
            state = 'draining'
        else:
            state = owner.tick()
        _, records = totals(root)
        status = {'pid': os.getpid(), 'state': state, 'updated_utc': utc(),
                  'task': config['task'], 'mode': 'parallel_scout_reproducer',
                  'active_sessions': owner.state['active'], 'usage': owner.state['ledger'],
                  'investigations': records,
                  'cost_note': 'In-flight time/session reservations included. USD unknown when provider omits billing.'}
        write(Path(root)/'status.json', status)
        write(Path(root)/'current-session.json', {'state': state, 'pid': os.getpid(),
                                                'sessions': list(owner.state['active'].values())})
        if (stop or state == 'stopped') and not owner.state['active']:
            (Path(root)/'current-session.json').unlink(missing_ok=True)
            break
        time.sleep(2)


if __name__ == '__main__':
    worker(sys.argv[1], sys.argv[2])
