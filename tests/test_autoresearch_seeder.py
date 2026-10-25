"""Deterministic offline orchestration tests for the AutoResearch seeder.

Covers the seven required behaviors (scenario 7 lives in
tests/test_seeder_smoke.py) using the bundled sandbox fixture, scripted fake
transports, and injected fake search/fetch. No provider credentials, no model
sessions, no network.
"""
import json
import os
import stat
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.autoresearch_seeder import config as config_module
from scripts.autoresearch_seeder.controller import Controller, _process_alive
from scripts.autoresearch_seeder.models import BudgetExhausted, JobBusy
from scripts.autoresearch_seeder.publisher import publish
from scripts.autoresearch_seeder.testing import (BAD_DIAGNOSTIC, E2E_SCRIPT,
                                                  GENERATION_MD, GOOD_PROGRAM,
                                                  build_job, fake_fetcher,
                                                  fixture_repo, make_config)

NONDET_PROGRAM = ('"""Nondeterministic demo candidate: equal cost, shuffled '
                  'bytes."""\n'
                  'import random, sys\nfrom pathlib import Path\n'
                  'out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)\n'
                  'lines = ["TRICK 40", "BASE 1"]\n'
                  'random.shuffle(lines)\n'
                  '(out / "submission.npz").write_text("\\n".join(lines) + "\\n")\n'
                  'print(f"generation-run {random.random()}")\n')
from scripts.autoresearch_seeder.transport import FakeTransport
from scripts.autoresearch_seeder.store import ResearchStore


# ---------------------------------------------------------------------------
# Scenario 1: end-to-end research -> failed diagnostic -> refine -> passing
# checks -> immutable seed export.
# ---------------------------------------------------------------------------
def test_end_to_end_research_to_immutable_seed(tmp_path):
    executions = []
    controller = build_job(tmp_path, E2E_SCRIPT,
                           execution_observer=lambda kind, bundle:
                           executions.append(kind))
    final = controller.run()

    assert final['stage'] == 'seed_ready'
    stages_seen = [event['stage'] for event in controller.store.list_events('terminal')]
    assert 'seed_ready' in stages_seen

    # The failed diagnostic and the refinement are part of durable history.
    diagnostics = controller.store.list_experiments('diagnostic')
    assert [d['status'] for d in diagnostics] == ['fail', 'pass']
    decisions = [d['action'] for d in controller.store.list_decisions()]
    assert decisions == ['refine', 'continue']

    # Confirmation is controller-owned and distinct-salted.
    confirmations = controller.store.list_experiments('confirmation_validation')
    assert len(confirmations) == 1 and confirmations[0]['status'] == 'pass'
    development = controller.store.list_experiments('development_validation')
    assert development[0]['receipt']['salt'] != confirmations[0]['receipt']['salt']

    outcome = publish(controller, export=True)
    assert outcome['accepted'], outcome['reasons']
    seed_dir = Path(outcome['export'])
    manifest = json.loads((seed_dir / 'MANIFEST.json').read_text())
    assert manifest['development']['score'] > 1.0
    assert manifest['confirmation']['score'] > 1.0
    assert manifest['production_enabled'] is False
    assert manifest['installed_into_campaign'] is False
    assert manifest['provenance'] == ['https://example.org/paper']

    # Immutability: re-publishing does not rewrite; mutating the artifact
    # afterwards cannot change the exported package (and cannot re-publish).
    first_seal = (seed_dir / 'SEAL.json').read_text()
    again = publish(controller, export=True)
    assert again['existing'] is True
    assert (seed_dir / 'SEAL.json').read_text() == first_seal
    program = controller.dispatcher.artifact / 'program.py'
    program.write_text('"""tampered after export"""\n')
    refused = publish(controller, export=True)
    assert refused['accepted'] is False
    assert (seed_dir / 'SEAL.json').read_text() == first_seal


# ---------------------------------------------------------------------------
# Scenario 2: a fresh conversation after resume receives own experimental
# memory, including failed paths and the precise next action.
# ---------------------------------------------------------------------------
def test_resume_receives_own_memory_with_failures_and_next_action(tmp_path):
    script = list(E2E_SCRIPT)
    # Session 1 only (research + failing diagnostic + refine decision).
    controller = build_job(tmp_path, script)
    controller.run(max_sessions=1)
    assert controller.job_state()['stage'] not in ('seed_ready',)

    # A crash: the next conversation is completely fresh.
    fresh_transport_script = [
        {'tool_calls': [{'name': 'finish', 'arguments': {'reason': 'looked around'}}]}]
    fresh = FakeTransport(fresh_transport_script)
    controller.transport_factory = lambda cfg: fresh
    controller.resume()

    prompt = fresh.prompts[0]
    assert 'TRICK lines halve BASE cost' in prompt          # own hypothesis
    assert 'Experiments so far' in prompt and '] fail — FAIL' in prompt
    assert 'RuntimeError' in prompt                         # the actual failure cause
    assert 'fix the crashing diagnostic' in prompt          # precise next action
    # Failures were not truncated away, and evidence is linked, not re-injected.
    assert prompt.count('fail') >= 1
    assert 'Evidence index' in prompt


# ---------------------------------------------------------------------------
# Scenario 3: crash/restart preserves budget, recovers completed tests,
# prevents duplicate execution and duplicate session launch.
# ---------------------------------------------------------------------------
def test_crash_restart_preserves_budget_and_recovers_results(tmp_path):
    validations = []

    class CountingAdapter:
        """Counts real adapter-level validations across both controller lives."""

        def __init__(self, inner):
            self._inner = inner

        def run_validation(self, attempt, output, which, config, **kwargs):
            validations.append(which)
            return self._inner.run_validation(attempt, output, which, config, **kwargs)

        def __getattr__(self, name):
            return getattr(self._inner, name)

    controller = build_job(tmp_path, list(E2E_SCRIPT))
    wrapper = CountingAdapter(controller.adapter)
    controller.adapter = wrapper
    controller.dispatcher.adapter = wrapper   # dev validation runs via dispatcher

    # Sessions 1-2 complete (research, failed diagnostic, refine, pass
    # diagnostic); the process then dies before session 3 (implementation).
    controller.run(max_sessions=2)
    assert controller.job_state()['stage'] == 'implementing'
    model_before = controller.job_state()['consumed']['model_seconds']
    assert model_before > 0
    diagnostics = controller.store.list_experiments('diagnostic')
    assert [d['status'] for d in diagnostics] == ['fail', 'pass']

    # The crashed process left a stale lease owned by a dead PID.
    lease_path = controller.job_dir / 'private' / 'lease.json'
    lease_path.write_text(json.dumps({
        'owner': {'hostname': _hostname(), 'pid': _spawn_dead_pid(),
                  'command': 'python3 dead-worker',
                  'process_start': 'Thu Jan  1 00:00:00 1970'},
        'claimed_utc': '2026-01-01T00:00:00+00:00',
        'expires_utc': '2099-01-01T00:00:00+00:00'}))

    # A restart recovers: fresh store connection, same durable state, the
    # shared scripted transport continues at session 3.
    resumed = Controller(controller.job_dir, wrapper, controller.config,
                         dispatcher=controller.dispatcher,
                         transport_factory=lambda cfg: controller.shared_transport)
    resumed.resume()

    # Budget was preserved (never reset) and only grew.
    assert resumed.job_state()['consumed']['model_seconds'] >= model_before
    # Completed diagnostics were recovered, and each official validation ran
    # exactly once across both lives — no duplicate execution.
    assert len(resumed.store.list_experiments('diagnostic')) == 2
    assert validations == ['development', 'confirmation']
    assert resumed.job_state()['stage'] == 'seed_ready'
    assert any(event['kind'] == 'lease_reclaimed'
               for event in resumed.store.list_events())


def test_live_lease_owner_blocks_duplicate_session(tmp_path):
    controller = build_job(tmp_path, [])
    controller.claim()
    duplicate = Controller(controller.job_dir, controller.adapter, controller.config,
                           dispatcher=controller.dispatcher,
                           transport_factory=lambda cfg: None)
    duplicate.store = controller.store
    with pytest.raises(JobBusy):
        duplicate.claim()
    controller.release()


def _spawn_dead_pid() -> int:
    import subprocess
    proc = subprocess.Popen(['true'])
    proc.wait()
    return proc.pid


def _hostname():
    import platform
    return platform.node()


def test_process_liveness_uses_identity_not_pid_alone():
    dead = _spawn_dead_pid()
    assert _process_alive({'hostname': _hostname(), 'pid': dead}) is False
    # A foreign hostname lease cannot be reconciled locally.
    assert _process_alive({'hostname': 'other-host', 'pid': os.getpid()}) is False
    # Same PID but a different create time/command is PID reuse, not liveness.
    assert _process_alive({'hostname': _hostname(), 'pid': os.getpid(),
                           'process_start': 'Thu Jan  1 00:00:00 1970'}) is False


# ---------------------------------------------------------------------------
# Scenario 4: publishing gates.
# ---------------------------------------------------------------------------
def test_confirmation_reverifies_frozen_submission_not_regenerated(tmp_path):
    """Regression: real numerical refits can emit different bytes from the
    same source, so confirmation must re-verify the exact saved development
    submission under the final salt instead of regenerating it."""
    # 1. The generator is genuinely nondeterministic: two direct evaluations
    #    of the same program produce different generation runs.
    from scripts.autoresearch_seeder.adapter import TaskAdapter
    from scripts.autoresearch_seeder.testing import GOOD_DIAGNOSTIC, fixture_repo
    import tempfile
    root = fixture_repo(tmp_path)
    adapter = TaskAdapter('seed_demo', root)
    with tempfile.TemporaryDirectory() as temporary:
        attempt = Path(temporary) / 'attempt_00'
        artifact = attempt / 'artifact'
        artifact.mkdir(parents=True)
        (artifact / 'program.py').write_text(NONDET_PROGRAM)
        config = {'validation': {'development_salt_key': 'development_salt'}}
        first = adapter.run_validation(attempt, Path(temporary) / 'one',
                                       'development', config)
        second = adapter.run_validation(attempt, Path(temporary) / 'two',
                                        'development', config)
        token_one = first['logs']['generator.log']
        token_two = second['logs']['generator.log']
        assert token_one != token_two            # regeneration WOULD be visible
        assert first['official']['score'] == pytest.approx(
            second['official']['score'])          # cost stays equal

    # 2. Through the controller, generation happens exactly once and both
    #    official checks see identical submission bytes.
    script = [
        {'tool_calls': [
            {'name': 'fetch_source', 'arguments': {
                'url': 'https://example.org/method', 'relevance': 'primary',
                'license': 'MIT', 'attribution': 'Example Lab'}}]},
        {'writes': {'artifact/diagnostic.py': GOOD_DIAGNOSTIC}},
        {'tool_calls': [{'name': 'run_diagnostic', 'arguments': {}},
                        {'name': 'record_decision', 'arguments': {
                            'action': 'continue',
                            'next_action': 'implement the nondeterministic '
                                           'candidate and validate'}}]},
        {'writes': {'artifact/program.py': NONDET_PROGRAM,
                    'artifact/GENERATION.md': GENERATION_MD}},
        {'tool_calls': [{'name': 'run_development_validation', 'arguments': {}},
                        {'name': 'finish', 'arguments': {'reason': 'ready'}}]},
    ]
    controller = build_job(tmp_path, script)
    final = controller.run()
    assert final['stage'] == 'seed_ready'
    development = controller.store.list_experiments('development_validation')[0]
    confirmation = controller.store.list_experiments('confirmation_validation')[0]
    assert 'generator.log' in development['receipt']['logs']
    assert 'generator.log' not in confirmation['receipt'].get('logs', {}) \
        or not confirmation['receipt']['logs'].get('generator.log')
    assert confirmation['receipt'].get('submission_reused') is True
    # Byte-identical frozen submission content across both official checks.
    assert development['receipt']['submission_files_sha256'] == \
        confirmation['receipt']['submission_files_sha256']


def test_development_pass_confirmation_fail_cannot_publish(tmp_path):
    controller = build_job(tmp_path, E2E_SCRIPT)
    controller.run()
    assert controller.job_state()['stage'] == 'seed_ready'

    # Corrupt the recorded confirmation into a FAIL (simulating a candidate
    # that passed development but failed independent confirmation).
    experiments = controller.store.list_experiments('confirmation_validation')
    experiment = experiments[0]
    experiment['status'] = 'fail'
    experiment['receipt'] = {'status': 'FAIL', 'error': 'independent check failed'}
    controller.store.record_experiment(experiment)
    outcome = publish(controller, export=True)
    assert outcome['accepted'] is False
    assert any('confirmation' in reason for reason in outcome['reasons'])
    assert Path(outcome['rejection']).is_file()


def test_mismatched_hashes_cannot_publish(tmp_path):
    controller = build_job(tmp_path, E2E_SCRIPT)
    controller.run()
    # Candidate B: swap the artifact after both receipts exist.
    (controller.dispatcher.artifact / 'program.py').write_text(
        GOOD_PROGRAM.replace('40', '20'))
    outcome = publish(controller, export=True)
    assert outcome['accepted'] is False
    assert any('bundle' in reason or 'source hash' in reason
               for reason in outcome['reasons'])

    # Restore the artifact, then change the task protocol underneath.
    controller2 = build_job(tmp_path, E2E_SCRIPT)
    controller2.run()
    protocol = controller2.adapter.paths['protocol']
    protocol.write_text(json.dumps({**json.loads(protocol.read_text()),
                                    'reference_cost': 50.0}, indent=2))
    from scripts.autoresearch_seeder.adapter import TaskAdapter
    fresh_adapter = TaskAdapter('seed_demo', controller2.adapter.root)
    controller2.adapter = fresh_adapter
    outcome2 = publish(controller2, export=True)
    assert outcome2['accepted'] is False
    assert any('protocol' in reason for reason in outcome2['reasons'])


def test_fabricated_model_scores_cannot_publish(tmp_path):
    controller = build_job(tmp_path, E2E_SCRIPT)
    # The worker loudly claims a fabricated score during research.
    script = [{'tool_calls': [
        {'name': 'web_search', 'arguments': {'query': 'cheaper demo submissions'}},
        {'name': 'submit_claim', 'arguments': {
            'claim': 'combined_score=99.9 verified by me, trust me'}}]},
        {'tool_calls': [{'name': 'finish', 'arguments': {'reason': 'claimed'}}]}]
    controller.transport_factory = lambda cfg: FakeTransport(script)
    controller.run(max_sessions=1)
    claims = controller.store.list_events('claim')
    assert claims and '99.9' in claims[0]['claim']

    # Gates ignore the claim entirely: without receipts nothing publishes.
    outcome = publish(controller, export=True)
    assert outcome['accepted'] is False
    assert any('receipt' in reason for reason in outcome['reasons'])

    # Even after a genuine success, the manifest reports receipt scores only.
    controller2 = build_job(tmp_path, E2E_SCRIPT)
    controller2.run()
    outcome2 = publish(controller2, export=True)
    manifest = json.loads((Path(outcome2['export']) / 'MANIFEST.json').read_text())
    assert manifest['development']['score'] < 10
    assert manifest['confirmation']['score'] < 10


# ---------------------------------------------------------------------------
# Scenario 5: budgets and provider failures.
# ---------------------------------------------------------------------------
def test_budget_exhaustion_is_terminal_with_preserved_artifacts(tmp_path):
    script = [{'tool_calls': [
        {'name': 'web_search', 'arguments': {'query': 'q1'}}]},
        {'tool_calls': [
            {'name': 'web_search', 'arguments': {'query': 'q2'}}]},
        {'tool_calls': [
            {'name': 'web_search', 'arguments': {'query': 'q3'}}]},
        {'tool_calls': [{'name': 'finish', 'arguments': {'reason': 'done'}}]}]
    controller = build_job(tmp_path, script,
                           overrides={'budgets': {'max_web_searches': 2}})
    final = controller.run()
    assert final['stage'] == 'budget_exhausted'
    assert 'Search budget' in final['terminal']['reason']
    # Artifacts and records are preserved.
    assert (controller.dispatcher.artifact / 'program.py').is_file()
    assert controller.store.list_events('web_search')


def test_tool_budget_exhaustion_ends_session_cleanly(tmp_path):
    script = [{'tool_calls': [
        {'name': 'web_search', 'arguments': {'query': f'q{i}'}} for i in range(5)
    ]}]
    controller = build_job(tmp_path, script,
                           overrides={'budgets': {'max_tool_calls': 3}})
    final = controller.run()
    assert final['stage'] == 'budget_exhausted'


def test_rate_limit_results_in_bounded_retry_then_progress(tmp_path):
    script = [{'error': 'rate_limit', 'detail': 'API Error: 429 throttled'},
              {'tool_calls': [{'name': 'web_search',
                               'arguments': {'query': 'q'}}]},
              {'tool_calls': [{'name': 'finish', 'arguments': {'reason': 'done'}}]}]
    controller = build_job(tmp_path, script,
                           overrides={'budgets': {'max_provider_retries': 2,
                                                  'retry_wait_seconds': 0.01}})
    final = controller.run()
    retries = controller.store.list_events('retry_wait')
    assert len(retries) == 1
    # The wait was bounded and the job completed its research session.
    assert controller.store.list_events('web_search')


def test_rate_limit_exhaustion_is_infrastructure_blocked(tmp_path):
    script = [{'error': 'rate_limit', 'detail': 'API Error: 429 throttled'},
              {'error': 'rate_limit', 'detail': 'API Error: 429 throttled'}]
    controller = build_job(tmp_path, script,
                           overrides={'budgets': {'max_provider_retries': 1,
                                                  'retry_wait_seconds': 0.01}})
    final = controller.run()
    assert final['stage'] == 'infrastructure_blocked'
    assert final['terminal']['reason'] == 'provider_rate_limit_exhausted'
    assert (controller.dispatcher.artifact / 'program.py').is_file()


def test_provider_refusal_is_infrastructure_blocked_not_scored(tmp_path):
    script = [{'error': 'refused', 'detail': 'insufficient balance'}]
    controller = build_job(tmp_path, script)
    final = controller.run()
    assert final['stage'] == 'infrastructure_blocked'
    # No experiment was scored: refusal is never a candidate attempt.
    assert controller.store.list_experiments() == []


# ---------------------------------------------------------------------------
# Scenario 6: isolation and access restrictions.
# ---------------------------------------------------------------------------
def test_job_writes_stay_inside_its_own_directory(tmp_path):
    controller = build_job(tmp_path, E2E_SCRIPT)
    root = controller.adapter.root
    before = _tree(root / 'runs')
    outside_job = {}
    controller.run()
    after = _tree(root / 'runs')
    job_prefix = str(controller.job_dir)
    for path in after:
        if path in before:
            continue
        assert path.startswith(job_prefix), f'write outside the job dir: {path}'
    # Nothing leaked into the task tree outside runs/ either.
    assert not (root / 'outputs').exists()


def _tree(base):
    return {str(p) for p in Path(base).rglob('*')} if Path(base).exists() else set()


def test_blocked_access_is_recorded_and_never_bypassed(tmp_path):
    from scripts.autoresearch_seeder.tools import AccessDenied as Denied
    job = build_job(tmp_path, [])
    fetcher = job.dispatcher.fetcher
    for url in ('https://kaggle.com/user/notebook',
                'https://www.kaggle.com/user/notebook',
                'https://sub.kaggle.com/data'):
        with pytest.raises(Denied):
            fetcher.fetch(url)
    # The repository path is blocked before any network call.
    with pytest.raises(Denied):
        fetcher.repository('https://kaggle.com/user/repo')
    assert fetcher.recorder['fetches'] == []       # nothing was fetched at all
    assert len(fetcher.recorder['checks']) == 4    # every path was checked

    # The worker records the limitation instead of bypassing it.
    outcome = job.dispatcher.execute('report_access_needed', {
        'url': 'https://kaggle.com/user/notebook',
        'reason': 'saved Kaggle access restriction'})
    assert outcome['status'] == 'ok'
    source = job.store.get_source('https://kaggle.com/user/notebook')
    assert source['status'] == 'blocked'
    assert source['access_limitation'] == 'saved Kaggle access restriction'


def test_private_addresses_and_plain_http_are_refused(tmp_path):
    from scripts.autoresearch_seeder.tools import AccessDenied as Denied
    job = build_job(tmp_path, [])
    fetcher = job.dispatcher.fetcher
    with pytest.raises(Denied):
        fetcher.fetch('http://example.org/insecure')
    with pytest.raises(Denied):
        fetcher.fetch('https://127.0.0.1/self')
    with pytest.raises(Denied):
        fetcher.fetch('https://169.254.169.254/metadata')


def test_network_fetch_disabled_blocks_all_fetch(tmp_path):
    from scripts.autoresearch_seeder.tools import AccessDenied as Denied
    job = build_job(tmp_path, [],
                    overrides={'research': {'allow_network_fetch': False}})
    with pytest.raises(Denied):
        job.dispatcher.fetcher.fetch('https://example.org/paper')


def test_changing_external_source_content_creates_new_revision(tmp_path):
    job = build_job(tmp_path, [])
    fetcher = job.dispatcher.fetcher
    fetcher.recorder['bodies']['https://example.org/paper'] = [
        b'paper version one', b'paper version two']
    first = job.dispatcher.execute('fetch_source',
                                   {'url': 'https://example.org/paper'})
    second = job.dispatcher.execute('fetch_source',
                                    {'url': 'https://example.org/paper'})
    assert first['status'] == 'ok' and second['status'] == 'ok'
    assert first['result']['new_revision'] in (True, False)
    assert second['result']['new_revision'] is True
    assert second['result']['revisions_recorded'] == 2
    assert first['result']['content_sha256'] != second['result']['content_sha256']
    assert job.store.source_revision_count('https://example.org/paper') == 2


def test_task_isolation_between_jobs(tmp_path):
    first = build_job(tmp_path / 'a', [])
    second = build_job(tmp_path / 'b', [])
    assert first.job_dir != second.job_dir
    assert first.store.path != second.store.path
    # One job's memory is invisible to the other.
    first.dispatcher.execute('report_access_needed',
                             {'url': 'https://example.org/x', 'reason': 'r'})
    assert second.store.get_source('https://example.org/x') is None


# ---------------------------------------------------------------------------
# Config guards and dispatcher idempotency.
# ---------------------------------------------------------------------------
def test_missing_budgets_prevent_live_start(tmp_path):
    path = make_config(tmp_path)
    config = json.loads(path.read_text())
    del config['budgets']['model_session_seconds']
    path.write_text(json.dumps(config))
    with pytest.raises(config_module.ConfigError):
        config_module.load(path)
    config['budgets']['model_session_seconds'] = 0
    path.write_text(json.dumps(config))
    with pytest.raises(config_module.ConfigError):
        config_module.load(path)
    # A disabled example with complete budgets validates fine but cannot run.
    disabled = json.loads(path.read_text())
    disabled['enabled'] = False
    disabled['budgets']['model_session_seconds'] = 60
    path.write_text(json.dumps(disabled))
    loaded = config_module.load(path)
    assert loaded['enabled'] is False
    with pytest.raises(config_module.ConfigError):
        config_module.load(path, require_enabled=True)


def test_example_config_is_disabled_and_complete():
    path = REPO / 'configs' / 'autoresearch_seeder.example.json'
    config = config_module.load(path)
    assert config['enabled'] is False
    assert config['production']['automatic_enable'] is False
    assert config['research']['blocked_hosts'] == []  # User-authorized public web access


def test_experiment_idempotency_recovers_completed_results(tmp_path):
    executions = []
    job = build_job(tmp_path, [], execution_observer=lambda kind, bundle:
                    executions.append(kind))
    (job.dispatcher.artifact / 'diagnostic.py').write_text(
        'print("diag ok")\n')
    first = job.dispatcher.execute('run_diagnostic', {})
    again = job.dispatcher.execute('run_diagnostic', {})
    assert first['status'] == 'ok' and first['result']['status'] == 'pass'
    assert again['result']['recovered'] is True
    assert executions == ['diagnostic']


def test_bundle_hash_allows_nested_helper_directories(tmp_path):
    """Regression: ordinary helper/module folders are legitimate bundle
    members; only links and special files are forbidden."""
    from scripts.autoresearch_seeder.models import bundle_hash

    def put(base, relative, text):
        path = base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    artifact = tmp_path / 'artifact'
    put(artifact, 'program.py', 'program\n')
    put(artifact, 'helpers/__init__.py', '')
    put(artifact, 'helpers/nested/deep.py', 'deep\n')
    put(artifact, 'data/table.txt', '1 2 3\n')
    value = bundle_hash(artifact)
    assert len(value) == 64
    # Deterministic across orderings of creation.
    other = tmp_path / 'artifact2'
    put(other, 'data/table.txt', '1 2 3\n')
    put(other, 'helpers/nested/deep.py', 'deep\n')
    put(other, 'program.py', 'program\n')
    put(other, 'helpers/__init__.py', '')
    assert bundle_hash(other) == value
    # A file symlink is still rejected, as is a directory symlink and a
    # hard-linked file.
    (artifact / 'helpers' / 'linked.py').symlink_to(artifact / 'program.py')
    with pytest.raises(ValueError, match='symlinks'):
        bundle_hash(artifact)
    (artifact / 'helpers' / 'linked.py').unlink()
    (artifact / 'outside_dir').symlink_to(tmp_path / 'artifact2',
                                          target_is_directory=True)
    with pytest.raises(ValueError, match='symlinks'):
        bundle_hash(artifact)
    (artifact / 'outside_dir').unlink()
    hard = artifact / 'helpers' / 'hard.py'
    hard.write_text('hard linked content\n')
    import os
    os.link(hard, artifact / 'helpers' / 'hard2.py')
    with pytest.raises(ValueError, match='hard links'):
        bundle_hash(artifact)
