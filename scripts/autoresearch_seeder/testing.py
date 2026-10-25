"""Shared offline scaffolding for tests, the smoke selftest and sample exports.

Everything here runs without provider credentials or model sessions: the
fixture task is copied into a temporary tree per test (isolating queue locks),
transports are scripted fakes, and search/fetch are injected fakes.
"""
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIXTURE_SOURCE = REPO / 'tests' / 'fixtures' / 'seed_demo_repo'

sys.path.insert(0, str(REPO))

from scripts.autoresearch_seeder import config as config_module           # noqa: E402
from scripts.autoresearch_seeder.adapter import TaskAdapter               # noqa: E402
from scripts.autoresearch_seeder.controller import Controller             # noqa: E402
from scripts.autoresearch_seeder.models import new_id                     # noqa: E402
from scripts.autoresearch_seeder.store import ResearchStore               # noqa: E402
from scripts.autoresearch_seeder.tools import ToolDispatcher              # noqa: E402
from scripts.autoresearch_seeder.transport import FakeTransport           # noqa: E402

GOOD_PROGRAM = ('"""Improved demo candidate built from the fetched mechanism."""\n'
                'import sys\nfrom pathlib import Path\n'
                'out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)\n'
                '(out / "submission.npz").write_text("TRICK 40\\n")\n'
                'print("wrote improved submission")\n')
GENERATION_MD = ('# Generation instructions\n\n'
                 'Run `python -I program.py <absolute-output-dir>`; the program writes\n'
                 'submission.npz deterministically from the constants above. No network,\n'
                 'no external data, no prebuilt artifacts.\n')
GOOD_DIAGNOSTIC = ('import os\n'
                   'open(os.path.join(os.environ["TEST_OUTPUT_DIR"], "note.txt"), "w")'
                   '.write("diagnostic ok")\nprint("diagnostic ok")\n')
BAD_DIAGNOSTIC = 'raise RuntimeError("diagnostic exploded")\n'
SEARCH_RESULT = {'results': [{'title': 'Cheaper demo submissions',
                              'url': 'https://example.org/paper',
                              'snippet': 'Halving BASE cost via TRICK lines.'}]}


def fixture_repo(tmp_path) -> Path:
    """Copy the fixture tree so each job gets isolated queue locks and files."""
    base = Path(tmp_path)
    target = base / 'fixture_repo'
    suffix = 0
    while target.exists():
        suffix += 1
        target = base / f'fixture_repo_{suffix}'
    shutil.copytree(FIXTURE_SOURCE, target)
    return target


def make_config(tmp_path, overrides=None, enabled=True) -> Path:
    config = {
        'schema_version': 1,
        'enabled': enabled,
        'task': 'seed_demo',
        'provider': {'name': 'minimax',
                     'credential_file': '.credentials/minimax.env',
                     'requested_model': 'FakeModel-1',
                     'requested_effort': 'medium'},
        'budgets': {'model_session_seconds': 60,
                    'job_wall_clock_seconds': 120,
                    'max_total_cost_usd': 5.0,
                    'max_tool_calls': 200,
                    'max_web_searches': 20,
                    'max_provider_retries': 2,
                    'retry_wait_seconds': 0.01},
        'validation': {'max_development_attempts': 6,
                       'development_salt_key': 'development_salt',
                       'final_salt_key': 'final_salt',
                       'improvement_margin': 0.0,
                       'conservative_comparison': 'both_salts'},
        'research': {'blocked_hosts': ['kaggle.com', 'www.kaggle.com'],
                     'allow_network_fetch': True,
                     'max_sources': 200},
        'queue': {'heavy_lock': 'work/runtime-locks/dqi-cpu.lock'},
        'publishing': {'library_snapshot': False},
        'production': {'automatic_enable': False},
    }
    for key, value in (overrides or {}).items():
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key].update(value)
        else:
            config[key] = value
    path = Path(tmp_path) / 'config.json'
    path.write_text(json.dumps(config, indent=2))
    return path


class FakeSearch:
    def __init__(self, result=None, fail=None):
        self.result = result if result is not None else SEARCH_RESULT
        self.fail = fail
        self.queries = []

    def search(self, query):
        self.queries.append(query)
        if self.fail:
            raise self.fail
        return self.result


def fake_fetcher(job_dir, config, bodies=None, fail_urls=()):
    """A real SourceFetcher with a scripted HTTP getter and access recorder."""
    from scripts.autoresearch_seeder.tools import SourceFetcher
    fetcher = SourceFetcher(job_dir / 'sources',
                            config.get('research', {}).get('blocked_hosts', []),
                            allow_network=config.get('research', {}).get(
                                'allow_network_fetch', True))
    state = {'bodies': dict(bodies or {}), 'fail_urls': set(fail_urls),
             'fetches': [], 'checks': []}
    original_check = fetcher.check_url

    def check(url):
        state['checks'].append(url)
        return original_check(url)

    def get(url, limit=None):
        state['fetches'].append(url)
        if url in state['fail_urls']:
            raise PermissionError(f'403 Forbidden: {url}')
        body = state['bodies'].get(url, b'fixture body v1')
        if isinstance(body, list):
            return body.pop(0)
        return body

    fetcher.check_url = check
    fetcher._get = get
    fetcher.recorder = state
    return fetcher


def build_job(tmp_path, script, overrides=None, enabled=True,
              execution_observer=None, search='default', fetcher=None):
    if search == 'default':
        search = FakeSearch()
    """Create a real job directory (like `init`) and return a ready Controller."""
    root = fixture_repo(tmp_path)
    config_path = make_config(tmp_path, overrides, enabled=enabled)
    config = config_module.load(config_path)
    adapter = TaskAdapter('seed_demo', root)
    job_dir = root / 'runs' / 'autoresearch-seeder' / 'seed_demo' / new_id('job')
    for name in ('sources', 'hypotheses', 'experiments', 'artifacts', 'private',
                 'exports'):
        (job_dir / name).mkdir(parents=True)
    attempt = job_dir / 'worker' / 'attempt_00' / 'artifact'
    attempt.mkdir(parents=True)
    shutil.copyfile(adapter.seed_program, attempt / 'program.py')
    from scripts.autoresearch_seeder.models import utc
    job = {'job_id': job_dir.name, 'task': 'seed_demo', 'task_root': str(root),
           'task_manifest_sha256': adapter.identity()['manifest_sha256'],
           'task_protocol_sha256': adapter.identity()['protocol_sha256'],
           'seed_program_sha256': adapter.identity()['seed_program_sha256'],
           'config_path': str(config_path),
           'config_digest': config_module.config_digest(config),
           'enabled': enabled, 'stage': 'queued', 'created_utc': utc(),
           'worker': {'provider': 'minimax', 'requested_model': 'FakeModel-1',
                      'requested_effort': 'medium', 'served_models': []},
           'consumed': {'model_seconds': 0.0, 'wall_seconds': 0.0, 'usd': 0.0},
           'production_enabled': False}
    (job_dir / 'job.json').write_text(json.dumps(job, indent=2))
    store = ResearchStore(job_dir / 'private' / 'research.sqlite')
    transport = FakeTransport(script)
    if fetcher is None:
        fetcher = fake_fetcher(job_dir, config)
    dispatcher = ToolDispatcher(
        store, adapter, config, job_dir, search_service=search,
        fetcher=fetcher, execution_observer=execution_observer)
    controller = Controller(job_dir, adapter, config, dispatcher=dispatcher,
                            transport_factory=lambda cfg: transport)
    controller.shared_transport = transport
    return controller


E2E_SCRIPT = [
    # Session 1: research a mechanism, first diagnostic fails.
    {'tool_calls': [
        {'name': 'web_search', 'arguments': {'query': 'cheaper demo submissions'}},
        {'name': 'fetch_source', 'arguments': {
            'url': 'https://example.org/paper', 'relevance': 'primary mechanism',
            'license': 'MIT', 'attribution': 'Example Lab'}},
        {'name': 'propose_hypothesis', 'arguments': {
            'mechanism': 'TRICK lines halve BASE cost',
            'family': 'submission-line optimization',
            'source_urls': ['https://example.org/paper'],
            'affected_cost_terms': ['base contribution'],
            'compatibility_assumptions': 'verifier accepts TRICK lines',
            'expected_opportunity': 'roughly 2x cheaper submission',
            'first_test': 'diagnostic writing a TRICK line',
            'rejection_conditions': 'malformed line or cost increase',
            'may_replace_inherited_architecture': False}}],
     'writes': {'artifact/diagnostic.py': BAD_DIAGNOSTIC}},
    {'tool_calls': [
        {'name': 'run_diagnostic', 'arguments': {}}],
     'usage': {'total_cost_usd': 0.01}},
    {'tool_calls': [
        {'name': 'record_decision', 'arguments': {
            'action': 'refine', 'experiment_ids': [],
            'next_action': 'fix the crashing diagnostic before implementing',
            'notes': 'diagnostic crashed; candidate bug, not infrastructure'}},
        {'name': 'finish', 'arguments': {'reason': 'session budget segment used'}}]},
    # Session 2: fixed diagnostic passes; commit to implementation.
    {'writes': {'artifact/diagnostic.py': GOOD_DIAGNOSTIC}},
    {'tool_calls': [
        {'name': 'run_diagnostic', 'arguments': {}},
        {'name': 'record_decision', 'arguments': {
            'action': 'continue', 'experiment_ids': [],
            'next_action': 'implement the TRICK program and run full development '
                           'validation',
            'notes': 'diagnostic PASS'}}],
     'usage': {'total_cost_usd': 0.01}},
    {'tool_calls': [{'name': 'finish', 'arguments': {'reason': 'ready to implement'}}]},
    # Session 3: implement, validate, finish.
    {'writes': {'artifact/program.py': GOOD_PROGRAM,
                'artifact/GENERATION.md': GENERATION_MD}},
    {'tool_calls': [
        {'name': 'run_development_validation', 'arguments': {}},
        {'name': 'finish', 'arguments': {'reason': 'candidate ready for confirmation'}}],
     'usage': {'total_cost_usd': 0.02}},
]
