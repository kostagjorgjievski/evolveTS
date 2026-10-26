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
from .models import atomic_write, digest, utc
from .scheduler import _maybe_research_session


def validate_service(config):
    if not config.get('enabled') or not config.get('service', {}).get('enabled'):
        raise ValueError('Research and service must both be explicitly enabled')
    for key in ('session_seconds', 'daily_model_seconds', 'daily_sessions', 'daily_reported_usd'):
        value = config.get('budgets', {}).get(key)
        if key=='daily_sessions' and value is None:continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError('Finite positive budget required: ' + key)
    workers=config.get('service',{}).get('reproducer_workers',1)
    if isinstance(workers,bool) or not isinstance(workers,int) or workers<1:
        raise ValueError('reproducer_workers must be a positive integer')
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


def enqueue_public_follow_up(root, config, agenda, records):
    """Advance an unchosen model-authored hypothesis, never invent a method.

    Only terminal shared R&D with a certified export can supply a handoff.
    No branch-private discoveries or recursive chains of fresh budgets enter.
    The ordinary daily admission gates have already run before this function.
    """
    if not config.get('service', {}).get('follow_up_hypotheses'):
        return None
    from .publisher import verify_export
    from .store import ResearchStore
    root = Path(root).resolve()
    origins = {r['origin'] for r in records}
    for parent in sorted(records, key=lambda r: r['created_utc'], reverse=True):
        if parent['branch'] is not None or parent['status'] != 'completed':
            continue
        if parent['origin'].startswith('public_hypothesis_follow_up:'):
            continue
        if parent['checkpoint'].get('job_stage') != 'seed_ready':
            continue
        job = root/'jobs/autoresearch-seeder'/config['task']/parent['id']
        if not (job/'private/research.sqlite').is_file():
            continue
        exports = [p for p in (job/'exports').glob('seed-*') if verify_export(p)['ok']]
        if not exports:
            continue
        export = sorted(exports)[-1]
        store = ResearchStore(job/'private/research.sqlite')
        try:
            decisions = store.list_decisions()
            chosen = (store.last_decision() or {}).get('hypothesis_id')
            rejected = {d.get('hypothesis_id') for d in decisions if d['action'] == 'reject'}
            sources = store.list_sources('accessed')
            source_map = {s['url']: s for s in sources}
            for hypothesis in reversed(store.list_hypotheses()):
                hid = hypothesis['id']
                origin = 'public_hypothesis_follow_up:' + parent['id'] + ':' + hid
                if not chosen or hid == chosen or hid in rejected or origin in origins:
                    continue
                cited = set(hypothesis.get('source_urls', [])) & set(source_map)
                if not cited:
                    continue
                handoff = root/'follow-up-inputs'/digest(origin)[:20]
                if handoff.exists() and not (handoff/'RESEARCH-HANDOFF.json').exists():
                    # A previous interrupted copy never became a usable handoff.
                    shutil.rmtree(handoff)
                if not handoff.exists():
                    artifact_files = list((export/'source-bundle').rglob('*'))
                    if sum(p.stat().st_size for p in artifact_files if p.is_file()) > 96*2**20:
                        continue
                    handoff.mkdir(parents=True)
                    shutil.copytree(export/'source-bundle', handoff/'parent-artifact')
                    shutil.copyfile(export/'SOURCES.json', handoff/'PARENT-SOURCES.json')
                    references = []
                    reference_bytes = 0
                    for url in sorted(cited):
                        source = source_map[url]
                        path = Path(source.get('local_path', ''))
                        if path.is_file() and not path.is_symlink() and path.is_relative_to(job/'sources'):
                            if reference_bytes + path.stat().st_size > 24*2**20:
                                continue
                            dest = handoff/'reference-sources'/path.name
                            dest.parent.mkdir(exist_ok=True)
                            shutil.copyfile(path, dest)
                            reference_bytes += path.stat().st_size
                            references.append({'url': url, 'path': str(dest.relative_to(handoff)),
                                               'content_sha256': source.get('content_sha256')})
                    atomic_write(handoff/'RESEARCH-HANDOFF.json', json.dumps({
                        'label': 'UNTESTED model-authored direction; parent seed does not prove this mechanism',
                        'hypothesis': hypothesis, 'parent_decisions': decisions,
                        'parent_export': str(export), 'public_sources': sources,
                        'copied_references': references,
                        'instruction': 'Parent artifact is already fully verified. Use it as prepared context; '
                            'perform the proposed new diagnostic/implementation before requesting full validation. '
                            'Do not merely repackage or revalidate the unchanged parent.'}, indent=2))
                topic = ('Continue this unchosen, source-backed hypothesis from your own public R&D: '
                         + hypothesis['mechanism'] + '\nCheapest proposed test: '
                         + hypothesis['first_test'] + '\nRead sources/provided-0/RESEARCH-HANDOFF.json '
                         'and its certified parent-artifact. Preserve negative results; '
                         'a prior seed does not establish this new direction.')
                item = agenda.create(topic, origin=origin,
                    budgets=config.get('agenda', {}).get('default_budgets'))
                item['checkpoint'].update(start_role='reproducer', parent_investigation=parent['id'],
                    hypothesis_id=hid, public_inputs=[{'path': str(handoff),
                        'url': 'public-research-follow-up:' + digest(origin),
                        'license': 'Preserve PARENT-SOURCES.json and source-specific license qualifications',
                        'attribution': 'Own shared R&D; original public authors retained in provenance'}])
                agenda.db.execute('UPDATE investigations SET checkpoint=? WHERE id=?',
                                  (json.dumps(item['checkpoint']), item['id']))
                agenda.db.commit()
                return item
        finally:
            store.close()
    return None


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
    if (config['budgets']['daily_sessions'] is not None and used['sessions'] >= config['budgets']['daily_sessions']) or used['model_seconds'] >= config['budgets']['daily_model_seconds'] or used['usd'] >= config['budgets']['daily_reported_usd']:
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
            candidate = enqueue_public_follow_up(root, config, agenda, records)
        if (candidate is None and service.get('continuous_discovery')
                and config.get('topics')):
            # Continue the public research frontier after completed work, under
            # the same daily admission gates. Never renew a depleted job's
            # budget or turn a branch-private checkpoint into public research.
            prefix = 'discovery_sweep:' + today + ':'
            sweep = sum(r['origin'].startswith(prefix) for r in records)
            topic = config['topics'][sweep % len(config['topics'])]
            candidate = agenda.create(
                topic + '\nPublic discovery sweep: consult the shared research knowledge and '
                'negative results first. Find a distinct, source-backed direction beyond '
                'already certified byte portfolios. Do not repeat completed reproductions '
                'or resume a budget-exhausted investigation under a new identity. '
                'You choose and interpret the sources and proposed mechanism.',
                origin=prefix + str(sweep),
                budgets=config.get('agenda', {}).get('default_budgets'))
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
        if config.get('service', {}).get('parallel_scout_reproducer'):
            if once:
                raise ValueError('Parallel service requires the persistent supervisor')
            from .parallel_service import serve_parallel_locked
            return serve_parallel_locked(root, config, config_path)
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
