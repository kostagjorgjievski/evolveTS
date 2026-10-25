"""CLI: init / preflight / run / resume / status / export / selftest / sample-export."""
import argparse
import importlib.util
import json
import os
import shutil
import sys
import time
from pathlib import Path

from . import ROOT, config as config_module
from .adapter import TaskAdapter
from .controller import Controller
from .models import BudgetExhausted, JobBusy, ToolInfrastructureError, atomic_write, \
    bundle_hash, file_digest, new_id, utc
from .store import ResearchStore

JOB_DIRS = ('sources', 'hypotheses', 'experiments', 'artifacts', 'private', 'exports')


def _load_controller(job_path, task_root=None, transport_factory=None,
                     search_service=None, fetcher=None, execution_observer=None):
    from .tools import ToolDispatcher
    job_dir = Path(job_path).resolve()
    job = json.loads((job_dir / 'job.json').read_text())
    config = config_module.load(job['config_path'])
    root = task_root or job.get('task_root') or ROOT
    adapter = TaskAdapter(job['task'], root)
    from .tools import SearchService, SourceFetcher
    dispatcher = ToolDispatcher(
        ResearchStore(job_dir / 'private' / 'research.sqlite'), adapter, config,
        job_dir, search_service=search_service, fetcher=fetcher,
        execution_observer=execution_observer)
    controller = Controller(job_dir, adapter, config, dispatcher=dispatcher,
                            transport_factory=transport_factory)
    return controller, job, config


def cmd_init(args):
    config = config_module.load(args.config)
    task_root = Path(args.task_root).resolve() if args.task_root else ROOT
    adapter = TaskAdapter(args.task, task_root)
    identity = adapter.identity()
    job_id = args.job_id or time.strftime('%Y%m%dT%H%M%SZ') + '-' + new_id('job')[4:]
    job_dir = Path(args.run_root) / 'autoresearch-seeder' / args.task / job_id
    if job_dir.exists():
        raise SystemExit(f'Job directory already exists: {job_dir}')
    for name in JOB_DIRS:
        (job_dir / name).mkdir(parents=True)
    (job_dir / 'worker' / 'attempt_00' / 'artifact').mkdir(parents=True)
    # Frozen starting artifact: the official seed program, copied unchanged.
    shutil.copyfile(adapter.seed_program,
                    job_dir / 'worker' / 'attempt_00' / 'artifact' / 'program.py')
    job = {
        'job_id': job_id,
        'task': args.task,
        'task_root': str(task_root),
        'task_manifest_sha256': identity['manifest_sha256'],
        'task_protocol_sha256': identity['protocol_sha256'],
        'seed_program_sha256': identity['seed_program_sha256'],
        'config_path': str(Path(args.config).resolve()),
        'config_digest': config_module.config_digest(config),
        'enabled': bool(config.get('enabled')),
        'stage': 'queued',
        'created_utc': utc(),
        'worker': {'provider': config.get('provider', {}).get('name'),
                   'requested_model': config.get('provider', {}).get('requested_model'),
                   'requested_effort': config.get('provider', {}).get('requested_effort'),
                   'served_models': []},
        'consumed': {'model_seconds': 0.0, 'wall_seconds': 0.0, 'usd': 0.0},
        'production_enabled': False,
    }
    atomic_write(job_dir / 'job.json', json.dumps(job, indent=2) + '\n')
    print(json.dumps({'job': str(job_dir), 'stage': 'queued', 'enabled': job['enabled']},
                    indent=2))
    return 0


def cmd_preflight(args):
    import shutil
    import tempfile
    controller, job, config = _load_controller(args.job)
    checks = []

    def record(name, ok, detail=''):
        checks.append({'check': name, 'ok': bool(ok), 'detail': detail})

    try:
        record('config valid with required budgets', True,
               'digest ' + config_module.config_digest(config)[:12])
    except Exception as exc:
        record('config valid with required budgets', False, str(exc))
    identity = controller.adapter.identity()
    record('task adapter loads', True,
           f"{identity['task_id']} protocol {identity['protocol_sha256'][:12]}")
    record('task identity unchanged', identity['manifest_sha256'] ==
           job.get('task_manifest_sha256')
           and identity['protocol_sha256'] == job.get('task_protocol_sha256'))
    artifact = controller.dispatcher.artifact
    record('frozen starting artifact present',
           (artifact / 'program.py').is_file()
           and file_digest(artifact / 'program.py') == job.get('seed_program_sha256'))
    try:
        bundle_hash(artifact)
        record('artifact bundle hashable', True)
    except ValueError as exc:
        record('artifact bundle hashable', False, str(exc))
    record('sandbox-exec available', shutil.which('sandbox-exec') is not None
           or sys.platform != 'darwin')
    # Offline diagnostic probe: the task's own diagnostic path must run without
    # provider credentials or a model session. A temporary copy of the frozen
    # artifact plus a trivial probe keeps the job's own attempt untouched.
    if args.offline_probe:
        try:
            with tempfile.TemporaryDirectory(prefix='seeder-preflight-') as temporary:
                probe = Path(temporary) / 'attempt_00' / 'artifact'
                probe.mkdir(parents=True)
                shutil.copyfile(controller.dispatcher.artifact / 'program.py',
                                probe / 'program.py')
                (probe / 'diagnostic.py').write_text(
                    'import os\n'
                    'open(os.path.join(os.environ["TEST_OUTPUT_DIR"], "probe.txt"),'
                    ' "w").write("ok")\nprint("preflight probe executed")\n')
                diagnostic = controller.adapter.run_diagnostic(probe.parent)
                record('offline diagnostic probe',
                       diagnostic.get('status') == 'PASS',
                       str(diagnostic.get('status')))
        except ToolInfrastructureError as exc:
            record('offline diagnostic probe', False, str(exc)[:500])
    if args.live:
        credential = Path(ROOT) / config['provider']['credential_file']
        record('provider credential file present', credential.is_file(),
               str(credential) + ' (contents never read or printed by preflight)')
        record('config enabled for live start', bool(config.get('enabled')))
        token_present = False
        if credential.is_file():
            for line in credential.read_text().splitlines():
                if line.strip().startswith('export ANTHROPIC_AUTH_TOKEN=') \
                        and len(line.split('=', 1)[1].strip().strip('"').strip("'")) > 8:
                    token_present = True
        record('provider token set (not printed)', token_present)
        backend_name = config['provider'].get('backend', 'claude_code')
        record('researcher backend selected',
               backend_name in ('claude_code', 'hermes'),
               f"provider.backend={backend_name!r} (claude_code default)")
        if backend_name == 'hermes':
            try:
                from .backends import HermesBackend
                backend = HermesBackend(config['provider'],
                                        Path(args.job).resolve(), app_root=ROOT)
                for check in backend.preflight():
                    record(f"hermes: {check['check']}", check['ok'],
                           check.get('detail', ''))
            except Exception as exc:
                record('hermes backend constructible', False, str(exc)[:500])
    ok = all(check['ok'] for check in checks)
    result = {'ok': ok, 'checks': checks, 'job': str(Path(args.job).resolve()),
              'production_enabled': False, 'checked_utc': utc()}
    print(json.dumps(result, indent=2))
    (Path(args.job).resolve() / 'private' / 'preflight.json').write_text(
        json.dumps(result, indent=2) + '\n')
    return 0 if ok else 1


def cmd_run(args):
    controller, job, config = _load_controller(
        args.job, transport_factory=_transport_factory_for(args))
    if not config.get('enabled'):
        raise SystemExit('Config is disabled; a live start requires enabled=true '
                         'with complete budgets. This example is intentionally disabled.')
    preflight = cmd_preflight(argparse.Namespace(
        job=args.job, live=True, offline_probe=False))
    if preflight != 0:
        raise SystemExit('Preflight failed; refusing to start a paid session')
    try:
        controller.run()
    except BudgetExhausted:
        pass   # terminal state already persisted; report below
    except JobBusy as busy:
        raise SystemExit(str(busy))
    controller.finalize_segment()
    print(json.dumps(_status(controller), indent=2))
    return 0


def _transport_factory_for(args):
    job_dir = Path(args.job).resolve()

    def factory(config):
        provider = config['provider']
        backend = provider.get('backend', 'claude_code')
        if backend == 'hermes':
            from .backends import HermesBackend
            return HermesBackend(provider, job_dir, app_root=ROOT)
        if backend == 'claude_code':
            from .transport import RealTransport
            return RealTransport(provider, job_dir, app_root=ROOT)
        raise SystemExit(
            f"Unknown researcher backend {backend!r}; expected 'claude_code' or "
            "'hermes' in provider.backend")
    return factory


def cmd_resume(args):
    controller, job, config = _load_controller(
        args.job, transport_factory=_transport_factory_for(args))
    if not config.get('enabled') and controller.job_state()['stage'] not in ('cancelled',):
        raise SystemExit('Config is disabled; resume of a live job requires enabled=true.')
    try:
        controller.resume()
    except BudgetExhausted:
        pass
    except JobBusy as busy:
        raise SystemExit(str(busy))
    controller.finalize_segment()
    print(json.dumps(_status(controller), indent=2))
    return 0


def _status(controller):
    job = controller.job_state()
    return {'job_id': job['job_id'], 'task': job['task'], 'stage': job['stage'],
            'terminal': job.get('terminal'), 'consumed': controller.consumed(),
            'budgets': controller.config.get('budgets'),
            'model_metadata': job.get('worker', {}).get(
                'model_metadata', {'requested_model': job.get('worker', {}).get(
                    'requested_model'),
                    'requested_effort': job.get('worker', {}).get('requested_effort'),
                    'served_models': job.get('worker', {}).get('served_models', []),
                    'effort_attested': False}),
            'provider_errors': [event for event in
                                controller.store.list_events('provider_error')],
            'cost_enforcement': 'Cost caps are enforced against accumulated '
                                'SDK-reported session costs only (post-hoc, not a '
                                'real-time spend limit); provider billing is not '
                                'independently reconciled.',
            'experiments': [{'kind': e['kind'], 'status': e['status'],
                             'score': (e.get('metrics') or {}).get('combined_score'),
                             'id': e['id'][:16]}
                            for e in controller.store.list_experiments()],
            'sources': len(controller.store.list_sources()),
            'hypotheses': len(controller.store.list_hypotheses()),
            'decisions': [d['action'] for d in controller.store.list_decisions()],
            'production_enabled': False}


def cmd_status(args):
    controller, job, config = _load_controller(args.job)
    print(json.dumps(_status(controller), indent=2))
    return 0


def cmd_export(args):
    from .publisher import publish
    controller, job, config = _load_controller(args.job)
    outcome = publish(controller, export=True, force=args.force)
    print(json.dumps(outcome, indent=2))
    return 0 if outcome['accepted'] else 1


def cmd_selftest(args):
    from .selftest import run_selftest
    return run_selftest(args)


def cmd_sample_export(args):
    from .samples import generate_samples
    generate_samples(Path(args.output))
    return 0


def cmd_schedule(args):
    from .scheduler import schedule
    outcomes = schedule(args.run_root, loop_passes=args.loop_passes,
                        sleep_seconds=args.sleep_seconds)
    print(json.dumps({'bounded': True, 'outcomes': outcomes,
                      'passes': len(outcomes)}, indent=2))
    return 0


SCHEDULER_NOTICE = (
    'The scheduler runs a bounded number of passes and exits; it is not a '
    'daemon. Eligibility checks are pure filesystem reads and never start a '
    'model session. Starting a job still requires the job config enabled=true '
    'and goes through the lease claim, so duplicate starts are impossible.')


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m scripts.autoresearch_seeder')
    parser.add_argument('--run-root', default=str(ROOT / 'runs'),
                        help='Root directory for runs/ (default <repo>/runs)')
    sub = parser.add_subparsers(dest='command', required=True)

    init = sub.add_parser('init', help='Create a queued job for a task')
    init.add_argument('--task', required=True)
    init.add_argument('--config', required=True)
    init.add_argument('--task-root', default=None,
                      help='Repository root holding tasks/ (defaults to this checkout)')
    init.add_argument('--job-id', default=None)
    init.set_defaults(func=cmd_init)

    preflight = sub.add_parser('preflight', help='Validate job readiness (offline)')
    preflight.add_argument('--job', required=True)
    preflight.add_argument('--live', action='store_true',
                           help='Additionally verify provider credentials exist')
    preflight.add_argument('--offline-probe', action='store_true',
                           help='Run the task diagnostic path once (no model session)')
    preflight.set_defaults(func=cmd_preflight)

    run = sub.add_parser('run', help='Run a job (requires enabled config + preflight)')
    run.add_argument('--job', required=True)
    run.set_defaults(func=cmd_run)

    resume = sub.add_parser('resume', help='Recover and continue a job')
    resume.add_argument('--job', required=True)
    resume.set_defaults(func=cmd_resume)

    status = sub.add_parser('status', help='Print job status')
    status.add_argument('--job', required=True)
    status.set_defaults(func=cmd_status)

    export = sub.add_parser('export', help='Evaluate gates and export a seed package')
    export.add_argument('--job', required=True)
    export.add_argument('--force', action='store_true')
    export.set_defaults(func=cmd_export)

    selftest = sub.add_parser('selftest', help='Real adapter smoke test (no model session)')
    selftest.add_argument('--task', default='dfthcsos')
    selftest.add_argument('--task-root', default=None)
    selftest.add_argument('--fixture', action='store_true',
                          help='Use the bundled offline demo task fixture')
    selftest.set_defaults(func=cmd_selftest)

    samples = sub.add_parser('sample-export',
                             help='Regenerate sample artifacts into a directory')
    samples.add_argument('--output', required=True)
    samples.set_defaults(func=cmd_sample_export)

    schedule = sub.add_parser('schedule',
                              help='Bounded pass: start one eligible queued job',
                              description=SCHEDULER_NOTICE)
    schedule.add_argument('--loop-passes', type=int, default=1,
                          help='Maximum passes (default 1; stops early when idle)')
    schedule.add_argument('--sleep-seconds', type=float, default=300.0,
                          help='Sleep between passes when work remains')
    schedule.set_defaults(func=cmd_schedule)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
