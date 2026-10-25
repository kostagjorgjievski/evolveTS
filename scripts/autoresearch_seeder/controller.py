"""Controller: durable jobs, atomic leases, budgets, stage machine, recovery.

Ordinary trusted code owns every state transition and validation gate. The
worker proposes; receipts decide. Automatic vs. manual transitions are
documented in docs/autoresearch-seeder.md.

Stage machine (automatic transitions marked [auto]):

  queued -> researching                         [auto]  on run/resume after preflight+lease
  researching -> compatibility_test             [auto]  when a diagnostic experiment exists
  compatibility_test -> implementing            [auto]  on a recorded continue/refine
                                                        decision after diagnostics
  implementing -> development_validation        [auto]  when a development validation
                                                        experiment exists for the
                                                        current bundle
  development_validation -> implementing        [auto]  receipt FAIL, attempts remain
                                                        (experiment failure != job failure)
  development_validation -> confirmation        [auto]  receipt PASS and improvement
  development_validation -> completed_no_improvement [auto] PASS but no improvement
  confirmation -> seed_ready                    [auto]  all publisher gates pass
  confirmation -> implementing                  [auto]  receipt FAIL, attempts remain
  confirmation -> rejected                      [auto]  attempts exhausted without a
                                                        passing improved candidate
  any -> retry_wait                             [auto]  provider rate-limit, bounded
  retry_wait -> previous stage                  [auto]  after retry_wait_seconds
  any -> infrastructure_blocked                 [auto]  sandbox/queue/system fault
  any -> budget_exhausted                       [auto]  any finite budget consumed
  any -> needs_access                           [auto]  when every source is blocked and
                                                        no accessible evidence exists
  any -> cancelled                              manual only (cancel command)
"""
import json
import os
import platform
import subprocess
import time
from pathlib import Path

from .adapter import CONFIRMATION, TaskAdapter
from .models import (BudgetExhausted, JobBusy, ProviderRateLimit, ProviderRefused,
                     ToolInfrastructureError, atomic_write, bundle_hash, digest,
                     experiment_id, utc)
from .store import ResearchStore
from .tools import ToolDispatcher

TERMINAL = {'seed_ready', 'rejected', 'completed_no_improvement', 'budget_exhausted',
            'infrastructure_blocked', 'cancelled'}
HOLD = {'retry_wait', 'needs_access'}
STAGES = ['queued', 'researching', 'compatibility_test', 'implementing',
          'development_validation', 'confirmation', 'seed_ready']


def _process_identity(pid: int) -> dict:
    return {'hostname': platform.node(), 'pid': pid, 'boot': platform.release()}


def _process_alive(identity: dict) -> bool:
    """Liveness by identity and create-time, never PID existence alone."""
    if identity.get('hostname') != platform.node():
        return False   # a lease from another host cannot be reconciled locally
    pid = identity.get('pid')
    if not isinstance(pid, int):
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    try:
        command = subprocess.run(['ps', '-p', str(pid), '-o', 'lstart=,command='],
                                 capture_output=True, text=True, timeout=5).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return False
    if not command:
        return False
    # PID reuse shows a different start time or command line.
    if identity.get('process_start') and not command.startswith(identity['process_start']):
        return False
    if identity.get('command') and identity['command'] not in command:
        return False
    return True


class Controller:
    def __init__(self, job_dir, adapter: TaskAdapter, config: dict,
                 dispatcher: ToolDispatcher = None, transport_factory=None):
        self.job_dir = Path(job_dir)
        self.adapter = adapter
        self.config = config
        self.store = ResearchStore(self.job_dir / 'private' / 'research.sqlite')
        self.dispatcher = dispatcher or ToolDispatcher(
            self.store, adapter, config, self.job_dir)
        self.transport_factory = transport_factory
        self._job = None

    # -- durable job state ----------------------------------------------------
    def job_path(self):
        return self.job_dir / 'job.json'

    def job_state(self) -> dict:
        if self._job is None or self._job.get('_dirty'):
            self._job = json.loads(self.job_path().read_text())
            self._job.pop('_dirty', None)
        return self._job

    def save_job(self, **updates) -> dict:
        job = self.job_state()
        job.update(updates)
        job['updated_utc'] = utc()
        atomic_write(self.job_path(), json.dumps(job, indent=2) + '\n')
        self._job = job
        return job

    # -- leases -----------------------------------------------------------------
    def lease_path(self):
        return self.job_dir / 'private' / 'lease.json'

    def claim(self, ttl_seconds: int = 3600) -> dict:
        """Atomically claim the job; reconcile any previous owner first."""
        lock_path = self.job_dir / 'private' / 'claim.lock'
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open('a') as lock:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
            lease_file = self.lease_path()
            if lease_file.exists():
                lease = json.loads(lease_file.read_text())
                if not lease.get('released') and lease.get('expires_utc') > utc() \
                        and _process_alive(lease.get('owner', {})):
                    raise JobBusy('A live owner holds this job lease: '
                                  + json.dumps(lease.get('owner', {})))
                self.store.event('lease_reclaimed', {'previous': lease})
            owner = _process_identity(os.getpid())
            try:
                command = subprocess.run(['ps', '-p', str(os.getpid()), '-o', 'command='],
                                         capture_output=True, text=True, timeout=5).stdout.strip()
                start = subprocess.run(['ps', '-p', str(os.getpid()), '-o', 'lstart='],
                                       capture_output=True, text=True, timeout=5).stdout.strip()
            except (subprocess.SubprocessError, OSError):
                command, start = '', ''
            owner.update({'command': command[:200], 'process_start': start})
            lease = {'owner': owner, 'claimed_utc': utc(),
                     'expires_utc': time.strftime(
                         '%Y-%m-%dT%H:%M:%S+00:00',
                         time.gmtime(time.time() + ttl_seconds))}
            atomic_write(lease_file, json.dumps(lease, indent=2))
            self.store.event('lease_claimed', {'owner': owner})
            return lease

    def release(self) -> None:
        lease_file = self.lease_path()
        if lease_file.exists():
            lease = json.loads(lease_file.read_text())
            lease['released'] = True
            atomic_write(lease_file, json.dumps(lease, indent=2))

    # -- budgets ------------------------------------------------------------------
    def consumed(self) -> dict:
        job = self.job_state()
        totals = self.store.totals()
        tool_totals = totals.get('tool', {'tool_calls': 0})
        wall = job.get('consumed', {}).get('wall_seconds', 0.0)
        segment_start = job.get('segment_started_monotonic')
        if segment_start is not None:
            wall += time.monotonic() - segment_start
        return {
            'model_seconds': job.get('consumed', {}).get('model_seconds', 0.0),
            'wall_seconds': wall,
            'usd': job.get('consumed', {}).get('usd', 0.0),
            'tool_calls': int(tool_totals.get('tool_calls', 0)),
            'web_searches': self.store.search_count(),
        }

    def remaining_session_seconds(self) -> float:
        budgets = self.config['budgets']
        job = self.job_state()
        session_used = job.get('session', {}).get('model_seconds', 0.0)
        return max(0.0, float(budgets['model_session_seconds']) - session_used)

    def remaining_tool_calls(self) -> int:
        used = self.store.tool_call_count()
        return max(0, int(self.config['budgets']['max_tool_calls']) - used)

    def _check_budgets(self) -> None:
        budgets = self.config['budgets']
        consumed = self.consumed()
        if consumed['tool_calls'] >= int(budgets['max_tool_calls']):
            raise BudgetExhausted('Tool-call budget exhausted')
        if consumed['web_searches'] >= int(budgets['max_web_searches']):
            raise BudgetExhausted('Search budget exhausted')
        if consumed['usd'] >= float(budgets['max_total_cost_usd']):
            raise BudgetExhausted('Cost budget exhausted')
        if consumed['model_seconds'] >= float(budgets['model_session_seconds']):
            raise BudgetExhausted('Model-session budget exhausted')
        if consumed['wall_seconds'] >= float(budgets['job_wall_clock_seconds']):
            raise BudgetExhausted('Job wall-clock budget exhausted')

    def _charge_session(self, outcome) -> None:
        job = self.job_state()
        consumed = job.setdefault('consumed', {})
        consumed['model_seconds'] = consumed.get('model_seconds', 0.0) + outcome.model_seconds
        consumed['usd'] = consumed.get('usd', 0.0) + (outcome.usd or 0.0)
        worker = job.setdefault('worker', {})
        if outcome.served_model:
            served = set(worker.get('served_models') or [])
            served.add(outcome.served_model)
            worker['served_models'] = sorted(served)
        checkpoint = job.setdefault('checkpoint', {})
        from pathlib import PurePosixPath
        checkpoint.update({'stage': job.get('stage'),
                           'artifact': str(self.dispatcher.artifact
                                           / PurePosixPath(self.adapter.candidate_file).name),
                           'updated_utc': utc()})
        self.store.charge('model', seconds=outcome.model_seconds, usd=outcome.usd or 0.0,
                          note='session')
        self.save_job(consumed=consumed, worker=worker, checkpoint=checkpoint)

    # -- main loop -----------------------------------------------------------------
    def run(self, *, max_sessions: int = None) -> dict:
        """Drive the job to a terminal or hold state. Crash-safe by construction:
        every mutation is persisted before the next step; recovery is `resume`."""
        self.claim()
        job = self.save_job(segment_started_monotonic=time.monotonic())
        sessions = 0
        no_progress = 0
        try:
            while True:
                job = self.job_state()
                stage = job['stage']
                if stage in TERMINAL or stage in HOLD:
                    break
                try:
                    self._check_budgets()
                except BudgetExhausted as exhausted:
                    self.save_job(stage='budget_exhausted',
                                  terminal={'reason': str(exhausted)[:2000],
                                            'utc': utc()})
                    self.store.event('terminal', {'stage': 'budget_exhausted',
                                                  'detail': str(exhausted)[:2000]})
                    break
                marker = self._activity_fingerprint()
                self._advance(stage)
                progressed = self.job_state()['stage'] != stage
                if not progressed:
                    # No progress from stage rules alone -> run a worker session.
                    if max_sessions is not None and sessions >= max_sessions:
                        break
                    sessions += 1
                    self._run_one_session()
                    if self._activity_fingerprint() == marker:
                        no_progress += 1
                        if no_progress >= 2:
                            self.save_job(stage='rejected',
                                          terminal={'reason': 'worker sessions made no '
                                                             'recorded progress', 'utc': utc()})
                            self.store.event('terminal', {'stage': 'rejected',
                                                          'reason': 'no_progress'})
                            break
                    else:
                        no_progress = 0
            return self.finalize_segment()
        finally:
            self.release()

    def finalize_segment(self) -> dict:
        """Persist this process's wall-clock segment into the durable budget."""
        job = self.job_state()
        segment_start = job.pop('segment_started_monotonic', None)
        if segment_start is not None:
            consumed = job.setdefault('consumed', {})
            consumed['wall_seconds'] = (consumed.get('wall_seconds', 0.0)
                                        + max(0.0, time.monotonic() - segment_start))
            self.save_job(**job)
            self._job = None
        return self.job_state()

    def _activity_fingerprint(self) -> tuple:
        return (len(self.store.list_experiments()), len(self.store.list_decisions()),
                len(self.store.list_events()), len(self.store.list_sources()))

    def _run_one_session(self) -> None:
        from .worker import run_session
        if self.transport_factory is None:
            raise ToolInfrastructureError('No transport configured')
        retries = int(self.config['budgets']['max_provider_retries'])
        wait = float(self.config['budgets']['retry_wait_seconds'])
        attempt = 0
        while True:
            transport = self.transport_factory(self.config)
            try:
                outcome = run_session(self, transport)
                self._charge_session(outcome)
                self._post_session()
                return
            except ProviderRateLimit as limited:
                attempt += 1
                job = self.job_state()
                previous = job['stage']
                if attempt > retries:
                    self.save_job(stage='infrastructure_blocked',
                                  terminal={'reason': 'provider_rate_limit_exhausted',
                                            'detail': str(limited)[:2000], 'utc': utc()})
                    self.store.event('terminal', {'stage': 'infrastructure_blocked',
                                                  'detail': str(limited)[:2000]})
                    return
                self.save_job(stage='retry_wait',
                              retry={'reason': 'provider_rate_limit',
                                     'detail': str(limited)[:1000],
                                     'attempt': attempt, 'resume_stage': previous,
                                     'eligible_utc': time.strftime(
                                         '%Y-%m-%dT%H:%M:%S+00:00',
                                         time.gmtime(time.time() + wait))})
                self.store.event('retry_wait', {'attempt': attempt,
                                                'detail': str(limited)[:1000]})
                self._sleep_bounded(wait)
                self.save_job(stage=previous)
            except ProviderRefused as refused:
                self.save_job(stage='infrastructure_blocked',
                              terminal={'reason': 'provider_refused',
                                        'detail': str(refused)[:2000], 'utc': utc()})
                self.store.event('terminal', {'stage': 'infrastructure_blocked',
                                              'detail': str(refused)[:2000]})
                return
            except BudgetExhausted as exhausted:
                self.save_job(stage='budget_exhausted',
                              terminal={'reason': str(exhausted)[:2000], 'utc': utc()})
                self.store.event('terminal', {'stage': 'budget_exhausted',
                                              'detail': str(exhausted)[:2000]})
                return

    def _sleep_bounded(self, seconds: float) -> None:
        time.sleep(max(0.0, seconds))

    def _post_session(self) -> None:
        """Stage rules evaluated after each worker session, then again in _advance."""
        self._advance(self.job_state()['stage'], post_session=True)

    # -- stage rules -------------------------------------------------------------------
    def _advance(self, stage: str, post_session: bool = False) -> None:
        job = self.job_state()
        experiments = self.store.list_experiments()
        decisions = self.store.list_decisions()
        dev_attempts = [e for e in experiments if e['kind'] == 'development_validation']
        diagnostics = [e for e in experiments if e['kind'] == 'diagnostic']
        confirmations = [e for e in experiments if e['kind'] == 'confirmation_validation']
        max_attempts = int(self.config.get('validation', {}).get(
            'max_development_attempts', 6))

        if stage == 'queued':
            self.save_job(stage='researching')
            return
        if stage == 'researching':
            if diagnostics:
                self.save_job(stage='compatibility_test')
            return
        if stage == 'compatibility_test':
            if diagnostics and decisions and decisions[-1]['action'] in ('continue', 'refine'):
                self.save_job(stage='implementing')
            return
        if stage in ('implementing', 'development_validation'):
            # The worker triggers validation through the tool; when the receipt
            # exists the controller takes over trust decisions.
            latest_bundle = self._current_bundle()
            for experiment in reversed(dev_attempts):
                if experiment['input_bundle_sha256'] == latest_bundle:
                    self.save_job(stage='development_validation')
                    self._resolve_development(experiment, max_attempts)
                    return
            if stage == 'development_validation':
                # Receipt belongs to an older bundle; back to implementing.
                self.save_job(stage='implementing')
            return
        if stage == 'confirmation':
            latest = confirmations[-1] if confirmations else None
            if latest is None:
                self._run_confirmation()
            else:
                self._resolve_confirmation(latest, max_attempts)
            return

    def _current_bundle(self) -> str:
        return bundle_hash(self.dispatcher.artifact)

    def _resolve_development(self, experiment, max_attempts: int) -> None:
        score = (experiment.get('metrics') or {}).get('combined_score')
        baseline = self.adapter.baseline_score()
        margin = float(self.config.get('validation', {}).get('improvement_margin', 0.0))
        if experiment['status'] == 'pass' and score is not None and score > baseline + margin:
            self.save_job(stage='confirmation',
                          checkpoint={**self.job_state().get('checkpoint', {}),
                                      'development_experiment': experiment['id'],
                                      'candidate_bundle': experiment['input_bundle_sha256'],
                                      'updated_utc': utc()})
            self._run_confirmation()
            return
        if experiment['status'] == 'pass':
            # PASS without improvement: honest no-improvement outcome.
            self.save_job(stage='completed_no_improvement',
                          terminal={'reason': 'development PASS without improvement',
                                    'score': score, 'utc': utc()})
            self.store.event('terminal', {'stage': 'completed_no_improvement',
                                          'score': score})
            return
        attempts = len([e for e in self.store.list_experiments()
                        if e['kind'] == 'development_validation'])
        if attempts >= max_attempts:
            self.save_job(stage='rejected',
                          terminal={'reason': 'development attempts exhausted', 'utc': utc()})
            self.store.event('terminal', {'stage': 'rejected',
                                          'attempts': attempts})
            return
        self.save_job(stage='implementing',
                      checkpoint={**self.job_state().get('checkpoint', {}),
                                  'last_failed_development': experiment['id'],
                                  'updated_utc': utc()})

    def _run_confirmation(self) -> None:
        """Controller-owned independent confirmation with the final salt."""
        job = self.job_state()
        candidate_bundle = job.get('checkpoint', {}).get('candidate_bundle')
        frozen = self._current_bundle()
        if candidate_bundle and candidate_bundle != frozen:
            raise ToolInfrastructureError(
                'Artifact changed between development and confirmation; freeze first')
        params = {'which': 'confirmation',
                  'protocol_sha256': self.adapter.protocol_sha256}
        identifier = experiment_id('confirmation_validation',
                                   self.adapter.protocol_sha256, frozen, params)
        existing = self.store.get_experiment(identifier)
        if existing and existing['status'] in ('pass', 'fail'):
            self._resolve_confirmation(existing, int(self.config.get(
                'validation', {}).get('max_development_attempts', 6)))
            return
        output = self.job_dir / 'experiments' / f'confirmation-{identifier[:16]}'
        from .models import Experiment
        experiment = Experiment(kind='confirmation_validation',
                                input_bundle_sha256=frozen, params=params,
                                started_utc=utc())
        experiment.id = identifier
        started = time.monotonic()
        receipt = self.adapter.run_validation(
            self.dispatcher.attempt, output, CONFIRMATION, self.config)
        engine = receipt.get('seconds') or 0.0
        experiment.status = 'pass' if receipt.get('status') == 'PASS' else 'fail'
        experiment.receipt = receipt
        experiment.receipt_sha256 = digest(receipt)
        experiment.metrics = {'combined_score': receipt.get('combined_score')}
        experiment.wall_seconds = time.monotonic() - started
        experiment.engine_seconds = float(engine)
        experiment.conclusion = ('confirmation ' + experiment.status).upper()
        experiment.log_excerpt = ''.join(str(t) for t in (receipt.get('logs') or {}).values())[-8000:]
        log_dir = self.job_dir / 'experiments' / f'confirmation-{identifier[:16]}'
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / 'receipt.json').write_text(json.dumps(receipt, indent=2))
        experiment.log_path = str(log_dir / 'receipt.json')
        experiment.finished_utc = utc()
        self.store.record_experiment(experiment.record())
        self.store.charge('execution', seconds=float(engine), note='confirmation')
        self._resolve_confirmation(experiment.record(), int(self.config.get(
            'validation', {}).get('max_development_attempts', 6)))

    def _resolve_confirmation(self, experiment, max_attempts: int) -> None:
        from .publisher import publish
        if experiment['status'] != 'pass':
            attempts = len(self.store.list_experiments('confirmation_validation'))
            if attempts >= max_attempts:
                self.save_job(stage='rejected',
                              terminal={'reason': 'confirmation failed; attempts exhausted',
                                        'utc': utc()})
                self.store.event('terminal', {'stage': 'rejected'})
            else:
                self.save_job(stage='implementing',
                              checkpoint={**self.job_state().get('checkpoint', {}),
                                          'last_failed_confirmation': experiment['id'],
                                          'updated_utc': utc()})
            return
        outcome = publish(self, export=False)
        if outcome['accepted']:
            self.save_job(stage='seed_ready',
                          terminal={'reason': 'seed accepted', 'seed_id': outcome['seed_id'],
                                    'utc': utc()})
            self.store.event('terminal', {'stage': 'seed_ready',
                                          'seed_id': outcome['seed_id']})
        else:
            self.save_job(stage='rejected',
                          terminal={'reason': 'publisher gates failed',
                                    'reasons': outcome['reasons'], 'utc': utc()})
            self.store.event('terminal', {'stage': 'rejected',
                                          'reasons': outcome['reasons']})

    # -- recovery -----------------------------------------------------------------------
    def resume(self) -> dict:
        """Recover a job after a crash/restart: budgets and artifacts preserved,
        completed experiments recovered from the store, duplicate sessions prevented
        by lease reconciliation."""
        job = self.job_state()
        if job.get('stage') == 'retry_wait':
            retry = job.get('retry', {})
            self.save_job(stage=retry.get('resume_stage', 'researching'))
        self.store.event('resume', {'stage': self.job_state()['stage']})
        return self.run()
