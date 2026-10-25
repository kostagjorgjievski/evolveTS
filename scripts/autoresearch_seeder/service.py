"""Single-owner, always-on researcher. Idle polling never invokes a model.

Each wake runs at most one job session. Per-investigation and UTC-day limits
bound paid work; STOP/PAUSE files are read before every new session. This is
an ordinary project process, not a Codex scheduled task.
"""
import argparse
import datetime
import fcntl
import json
import math
import os
import shutil
import signal
import time
from pathlib import Path

from .investigations import Investigations
from .models import atomic_write, utc
from .scheduler import _maybe_research_session


def validate_service(config):
    if not config.get('enabled') or not config.get('service', {}).get('enabled'):
        raise ValueError('Research and service must both be explicitly enabled')
    for key in ('session_seconds', 'daily_model_seconds', 'daily_sessions', 'daily_reported_usd'):
        value = config.get('budgets', {}).get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError('Finite positive budget required: ' + key)
    for role in ('provider', 'reproducer'):
        if config.get(role, {}).get('backend') != 'hermes':
            raise ValueError('Service requires the tested Hermes backend for both roles')
    return config


def totals(root):
    agenda = Investigations(Path(root) / 'investigations.sqlite')
    try:
        records = agenda.list()
        return ({key: sum(r['consumed'][key] for r in records)
                 for key in ('sessions', 'model_seconds', 'usd')}, records)
    finally:
        agenda.close()


def wake(root, config, ledger, runner=_maybe_research_session):
    """One deterministic admission step, then at most one bounded session."""
    root = Path(root)
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    used = ledger.setdefault(today, {'sessions': 0, 'model_seconds': 0.0, 'usd': 0.0})
    before, records = totals(root)
    service = config.get('service', {})
    if (root / 'STOP').exists():
        return {'state': 'stopped', 'reason': 'STOP requested'}
    if (root / 'PAUSE').exists():
        return {'state': 'paused', 'reason': 'PAUSE requested; no model calls'}
    if used['sessions'] >= config['budgets']['daily_sessions'] or used['model_seconds'] >= config['budgets']['daily_model_seconds'] or used['usd'] >= config['budgets']['daily_reported_usd']:
        return {'state': 'daily_budget_wait', 'reason': 'UTC-day admission limit; no model calls'}
    if shutil.disk_usage(root).free < float(service.get('min_free_gib', 4)) * 2**30:
        return {'state': 'resource_wait', 'reason': 'Insufficient free scratch disk; no model calls'}
    agenda = Investigations(root / 'investigations.sqlite')
    try:
        if agenda.next_eligible() is None:
            seen_today = {r['topic'] for r in records if r['created_utc'].startswith(today)}
            for topic in config.get('topics', []):
                if topic not in seen_today:
                    agenda.create(topic, budgets=config.get('agenda', {}).get('default_budgets'))
                    break
        candidate = agenda.next_eligible()
        if candidate is None:
            return {'state': 'idle', 'reason': 'No eligible investigations; no model calls'}
    finally:
        agenda.close()
    runtime = {**config, 'root': str(root), 'materialized_jobs': True,
               'budgets': {**config['budgets'], 'session_seconds': min(config['budgets']['session_seconds'],
                   config['budgets']['daily_model_seconds'] - used['model_seconds'])}}
    atomic_write(root / 'current-session.json', json.dumps({'state': 'running', 'pid': os.getpid(),
        'investigation': candidate['id'], 'topic': candidate['topic'], 'started_utc': utc()}))
    try:
        result = runner(runtime)
        return {'state': 'ready', 'outcome': result}
    finally:
        after, _ = totals(root)
        for key in used:
            used[key] += max(0, after[key] - before[key])
        atomic_write(root / 'service-ledger.json', json.dumps(ledger, indent=2))
        (root / 'current-session.json').unlink(missing_ok=True)


def serve(root, config, *, once=False, wait_for_owner=False, config_path=None):
    validate_service(config)
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    lock = (root / 'service.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | (0 if wait_for_owner else fcntl.LOCK_NB))
    except BlockingIOError:
        raise SystemExit('Another researcher already owns this root')
    ledger_path = root / 'service-ledger.json'
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
    stop = False
    def interrupt(signum, frame):
        nonlocal stop
        stop = True
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    failures = 0
    atomic_write(root/'status.json',json.dumps({'pid':os.getpid(),'state':'starting','task':config['task'],'updated_utc':utc(),'current_session_file':str(root/'current-session.json')},indent=2))
    try:
        while not stop:
            try:
                if config_path is not None:
                    updated = validate_service(json.loads(Path(config_path).read_text()))
                    if updated['task'] != config['task'] or updated.get('task_root') != config.get('task_root'):
                        raise ValueError('Live reload cannot change task identity')
                    config = updated
                result = wake(root, config, ledger)
                failures = 0
            except KeyboardInterrupt:
                result = {'state': 'stopped', 'reason': 'Interrupted; own drafts retained'}
                stop = True
            except Exception as error:
                failures += 1
                result = {'state': 'infrastructure_backoff', 'error_class': type(error).__name__,
                          'reason': 'Research session failed; preserved job requires inspection. See job-local events.',
                          'consecutive_failures': failures}
                # Never loop paid starts against a broken runtime.
                if failures >= 3:
                    (root / 'PAUSE').write_text('Automatic infrastructure circuit breaker\n')
            _, records = totals(root)
            status = {'pid': os.getpid(), 'updated_utc': utc(), **result,
                      'task': config['task'], 'usage': ledger,
                      'investigations': [{'id': r['id'], 'topic': r['topic'], 'status': r['status'],
                                          'checkpoint': r['checkpoint'], 'consumed': r['consumed']} for r in records],
                      'cost_note': 'Provider-reported cost may be unavailable. Time/session admission limits are enforced; USD is not a billing guarantee.'}
            atomic_write(root / 'status.json', json.dumps(status, indent=2))
            if once or stop or result['state'] == 'stopped':
                break
            delay = min(300, 15 * 2**failures) if failures else config.get('service', {}).get('poll_seconds', 60)
            time.sleep(max(1, float(delay)))
    finally:
        lock.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--config', required=True)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--wait-for-owner', action='store_true')
    args = parser.parse_args()
    serve(args.root, json.loads(Path(args.config).read_text()), once=args.once, wait_for_owner=args.wait_for_owner, config_path=args.config)


if __name__ == '__main__':
    main()
