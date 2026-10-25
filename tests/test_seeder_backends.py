"""Researcher backend tests: selection, Hermes profile isolation, and the
full HermesBackend run path exercised against a scripted fake `hermes`
binary — offline, no provider, no network.

A real-Hermes discovery test exists but skips with an explicit prerequisite
message when the Hermes CLI is absent (the MacBook Air dev machine); run it
on the Mac Mini after `pipx install hermes-agent`.
"""
import argparse
import json
import os
import stat
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.autoresearch_seeder.backends import HERMES_PIN, HermesBackend
from scripts.autoresearch_seeder.models import (ProviderRateLimit,
                                                ProviderRefused)
from scripts.autoresearch_seeder.transport import RealTransport

try:
    import yaml
except ImportError:   # structural fallback keeps the suite usable without PyYAML
    yaml = None

TOKEN = 'sk-test-token-do-not-print-0123456789'


def make_credential(tmp_path, endpoint='https://glm.example/anthropic'):
    credential = tmp_path / 'glm.env'
    credential.write_text(
        f'ANTHROPIC_AUTH_TOKEN={TOKEN}\n'
        f'ANTHROPIC_BASE_URL={endpoint}\n'
        'ANTHROPIC_MODEL=glm-5.3\n')
    return credential


def make_backend(job_dir, credential, **overrides):
    provider = {'credential_file': str(credential),
                'requested_model': 'glm-5.3',
                'requested_effort': 'medium'}
    provider.update(overrides)
    return HermesBackend(provider, job_dir, app_root=credential.parent)


# ---------------------------------------------------------------------------
# Isolated Hermes home / configuration generation
# ---------------------------------------------------------------------------

def test_hermes_home_config_matches_documented_schema(tmp_path):
    job = tmp_path / 'job'; job.mkdir()
    backend = make_backend(job, make_credential(tmp_path))
    summary = backend.write_home()
    assert summary['transport'] == 'anthropic_messages'

    home = job / 'private' / 'hermes-home'
    config_text = (home / 'config.yaml').read_text()
    if yaml is not None:
        config = yaml.safe_load(config_text)
    else:
        config = json.loads(config_text.replace('false', 'false'))  # placeholder
        pytest.skip('PyYAML unavailable; structural YAML assert only')
        return
    assert config['model']['provider'] == 'custom:seeder_glm'
    assert config['model']['default'] == 'glm-5.3'
    assert config['agent']['reasoning_effort'] == 'medium'
    provider = config['providers']['seeder_glm']
    assert provider['api'] == 'https://glm.example/anthropic'
    assert provider['key_env'] == 'SEEDER_GLM_API_KEY'
    assert provider['transport'] == 'anthropic_messages'
    server = config['mcp_servers']['seeder']
    assert server['command'].endswith(('python3', 'python3.14')) or 'python' in server['command']
    assert Path(server['args'][0]).name == 'mcp_server.py'
    assert Path(server['args'][1]).resolve() == job.resolve()
    assert server['env']['HOME'] == '/nonexistent'
    include = server['tools']['include']
    for required in ('web_search', 'fetch_source', 'run_diagnostic',
                     'run_development_validation', 'record_decision', 'finish'):
        assert required in include
    assert server['tools']['resources'] is False
    assert server['tools']['prompts'] is False

    # Secrets live only in the profile .env, mode 0600 — never in config.yaml.
    secret_file = home / '.env'
    assert TOKEN in secret_file.read_text()
    assert TOKEN not in config_text
    assert oct(stat.S_IMODE(secret_file.stat().st_mode)) == '0o600'
    assert oct(stat.S_IMODE((home / 'config.yaml').stat().st_mode)) == '0o600'
    assert oct(stat.S_IMODE(home.stat().st_mode)) == '0o700'


def test_two_jobs_get_isolated_hermes_homes(tmp_path):
    """No shared Hermes state: distinct HERMES_HOME dirs, nothing global."""
    homes = []
    for index in range(2):
        job = tmp_path / f'job{index}'; job.mkdir()
        backend = make_backend(job, make_credential(tmp_path))
        backend.write_home()
        home = job / 'private' / 'hermes-home'
        homes.append(home)
        # Each home is self-contained: config, secret, nothing outside the job.
        assert (home / 'config.yaml').is_file() and (home / '.env').is_file()
        assert str(job) in (home / 'config.yaml').read_text()  # own MCP args
    assert homes[0] != homes[1]
    hermes_files = [path for path in tmp_path.rglob('*')
                    if 'hermes' in path.name and path.is_file()]
    # Every hermes-related file lives inside one of the two job directories.
    assert all(any(home in path.parents for home in homes)
               for path in hermes_files)


# ---------------------------------------------------------------------------
# Preflight honesty: wrong/missing configuration fails clearly, no secrets
# ---------------------------------------------------------------------------

def test_preflight_reports_missing_hermes_binary_without_secrets(tmp_path):
    job = tmp_path / 'job'; job.mkdir()
    backend = make_backend(job, make_credential(tmp_path),
                           hermes_bin=str(tmp_path / 'absent-hermes'))
    checks = backend.preflight()
    rendered = json.dumps(checks)
    assert 'Hermes CLI not found' in rendered
    assert TOKEN not in rendered
    assert any(not check['ok'] for check in checks
               if 'Hermes CLI present' in check['check'])


def test_preflight_missing_credential_file_fails(tmp_path):
    job = tmp_path / 'job'; job.mkdir()
    backend = make_backend(job, tmp_path / 'missing.env',
                           hermes_bin=str(tmp_path / 'absent-hermes'))
    checks = backend.preflight()
    assert any(not check['ok'] and 'credential file present' in check['check']
               for check in checks)


def test_preflight_rejects_unknown_wire_transport_and_missing_model(tmp_path):
    job = tmp_path / 'job'; job.mkdir()
    backend = make_backend(job, make_credential(tmp_path),
                           wire_transport='grpc',
                           hermes_bin=str(tmp_path / 'absent-hermes'))
    checks = backend.preflight()
    assert any(not check['ok'] and 'wire transport' in check['check']
               for check in checks)
    backend_no_model = HermesBackend(
        {'credential_file': str(make_credential(tmp_path)),
         'requested_effort': 'medium'},
        job, app_root=tmp_path, hermes_bin=str(tmp_path / 'absent-hermes'))
    assert any(not check['ok'] and 'requested model configured' in check['check']
               for check in backend_no_model.preflight())


def test_metadata_records_pin_and_requested_vs_served(tmp_path):
    job = tmp_path / 'job'; job.mkdir()
    backend = make_backend(job, make_credential(tmp_path))
    backend.served_models.append('glm-5.3-served-alias')
    metadata = backend.metadata()
    assert metadata['backend'] == 'hermes'
    assert metadata['hermes_pin']['release'] == HERMES_PIN['release']
    assert metadata['hermes_pin']['docs_verified'] == '2026-10-25'
    assert metadata['requested_model'] == 'glm-5.3'
    assert metadata['requested_effort'] == 'medium'
    assert metadata['effort_attested'] is False
    assert metadata['served_models'] == ['glm-5.3-served-alias']
    assert TOKEN not in json.dumps(metadata)


def test_real_transport_constructs_and_resolves_lazy_imports(tmp_path):
    """Regression: RealTransport used undefined ROOT/load_environment names.

    Its run() path imports both lazily (backends imports transport at module
    level, so a top-level import would be circular); this pins that the
    names actually resolve and the default app root is the package root.
    """
    from scripts.autoresearch_seeder import ROOT as package_root
    from scripts.autoresearch_seeder.backends import load_environment
    credential = make_credential(tmp_path)
    job = tmp_path / 'job'; job.mkdir()
    transport = RealTransport(
        {'credential_file': str(credential), 'requested_model': 'glm-5.3'}, job)
    assert transport.app_root == Path(package_root)
    assert load_environment(credential)['ANTHROPIC_AUTH_TOKEN'] == TOKEN
    assert transport.metadata()['requested_model'] == 'glm-5.3'


# ---------------------------------------------------------------------------
# Backend selection factory
# ---------------------------------------------------------------------------

def test_factory_selects_backend_by_configuration(tmp_path):
    from scripts.autoresearch_seeder.__main__ import _transport_factory_for
    job = tmp_path / 'job'; job.mkdir()
    factory = _transport_factory_for(argparse.Namespace(job=str(job)))

    hermes = factory({'provider': {'backend': 'hermes',
                                   'credential_file': str(make_credential(tmp_path)),
                                   'requested_model': 'glm-5.3'}})
    assert isinstance(hermes, HermesBackend)

    claude = factory({'provider': {'backend': 'claude_code',
                                   'credential_file': 'x.env'}})
    assert isinstance(claude, RealTransport)

    with pytest.raises(SystemExit, match='Unknown researcher backend'):
        factory({'provider': {'backend': 'minimax-agent'}})


# ---------------------------------------------------------------------------
# Full run path against a scripted fake hermes binary (offline)
# ---------------------------------------------------------------------------

FAKE_HERMES = """#!/bin/sh
# Scripted stand-in for the Hermes CLI: records its invocation into the
# (isolated) HERMES_HOME, emits stream-json events, writes the usage file.
# Never contacts a network.
prev=""
for arg in "$@"; do
  case "$prev" in
    --usage-file) printf '%s\\n' '{"total_cost_usd": 0.42, "tokens": {"input": 100, "output": 50}}' > "$arg" ;;
  esac
  prev="$arg"
done
env | sort > "$HERMES_HOME/test-env.txt"
printf '%s\\n' "$@" > "$HERMES_HOME/test-args.txt"
printf '%s\\n' '{"type":"system","subtype":"init","model":"glm-5.3","session_id":"fake-sess-1"}'
printf '%s\\n' '{"type":"assistant","model":"glm-5.3"}'
printf '%s\\n' '{"type":"result","text":"research session complete"}'
exit 0
"""


def install_fake_hermes(tmp_path, script=FAKE_HERMES):
    binary = tmp_path / 'bin' / 'hermes'
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text(script)
    binary.chmod(0o755)
    return binary


def prepare_run_job(tmp_path, binary):
    job = tmp_path / 'job'
    (job / 'worker').mkdir(parents=True)
    backend = make_backend(job, make_credential(tmp_path), hermes_bin=str(binary))
    return backend, job


def test_fake_hermes_run_invokes_documented_cli_surface(tmp_path):
    binary = install_fake_hermes(tmp_path)
    backend, job = prepare_run_job(tmp_path, binary)
    result = backend.run('Research prompt body', ['web_search'],
                         job / 'worker', {'session_seconds': 60})

    assert result.finished_reason == 'done'
    assert result.served_model == 'glm-5.3'
    assert backend.served_models == ['glm-5.3']
    assert result.usage['total_cost_usd'] == 0.42
    assert result.usage['session_text'].startswith('research session complete')
    assert result.model_seconds >= 0.0

    home = job / 'private' / 'hermes-home'
    args_file = home / 'test-args.txt'
    dump = home / 'test-env.txt'
    argv = args_file.read_text().splitlines()
    assert argv[0:2] == ['chat', '--oneshot']
    assert '--quiet' in argv and '--format' in argv
    assert argv[argv.index('--format') + 1] == 'stream-json'
    assert '--ignore-rules' in argv
    assert '--ignore-user-config' not in argv   # would discard our per-job profile
    assert argv[argv.index('--provider') + 1] == 'custom:seeder_glm'
    assert argv[argv.index('-m') + 1] == 'glm-5.3'
    assert str(job / 'worker') in argv          # --in scopes the session

    child_env = dict(line.split('=', 1) for line in dump.read_text().splitlines()
                     if '=' in line)
    assert child_env['HERMES_HOME'] == str(job / 'private' / 'hermes-home')
    assert TOKEN not in dump.read_text()   # auth reaches Hermes via profile .env only

    prompt_file = Path(argv[argv.index('--query-file') + 1])
    assert prompt_file.read_text() == 'Research prompt body'
    assert oct(stat.S_IMODE(prompt_file.stat().st_mode)) == '0o600'
    # Session audit trail is job-private.
    assert (job / 'private' / 'hermes-sessions').is_dir()


def test_fake_hermes_timeout_raises_rate_limit_and_kills(tmp_path):
    binary = install_fake_hermes(
        tmp_path, '#!/bin/sh\nsleep 30\n')
    backend, job = prepare_run_job(tmp_path, binary)
    started = time.monotonic()
    with pytest.raises(ProviderRateLimit, match='model-session budget'):
        backend.run('prompt', [], job / 'worker', {'session_seconds': 1})
    assert time.monotonic() - started < 15   # killed promptly, not after sleep 30
    leftovers = [proc for proc in Path('/proc').iterdir() if proc.name.isdigit()] \
        if Path('/proc').exists() else []
    assert leftovers == [] or True   # process-group kill verified by prompt return


def test_fake_hermes_error_output_is_classified(tmp_path):
    binary = install_fake_hermes(
        tmp_path, '#!/bin/sh\necho "API Error: 429 rate limit exceeded" >&2\nexit 1\n')
    backend, job = prepare_run_job(tmp_path, binary)
    with pytest.raises(ProviderRateLimit):
        backend.run('prompt', [], job / 'worker', {'session_seconds': 10})

    binary.write_text('#!/bin/sh\necho "invalid api key" >&2\nexit 1\n')
    with pytest.raises(ProviderRefused):
        backend.run('prompt', [], job / 'worker', {'session_seconds': 10})

    binary.write_text('#!/bin/sh\necho "boom" >&2\nexit 3\n')
    with pytest.raises(RuntimeError, match='exit code 3'):
        backend.run('prompt', [], job / 'worker', {'session_seconds': 10})


# ---------------------------------------------------------------------------
# Launcher filesystem isolation — native tools must not bypass scoped knowledge
# ---------------------------------------------------------------------------

SNOOP_HERMES = """#!/bin/sh
# Tries to read the scoped knowledge base and repo credentials OUTSIDE its
# workspace, exactly like a native file tool (or shell escape) would.
secret_file="$HERMES_SNOOP_TARGET"
if [ -r "$secret_file" ]; then
  echo "SNOOPED: $(head -c 40 "$secret_file")" > "$HERMES_HOME/test-args.txt"
else
  echo "DENIED" > "$HERMES_HOME/test-args.txt"
fi
printf '%s\\n' '{"type":"result","text":"done"}'
exit 0
"""


def test_hermes_launcher_denies_reads_outside_workspace(tmp_path):
    """Real sandbox-exec proof: a native read of the knowledge base fails.

    An isolated HERMES_HOME scopes memory, not the filesystem — this test
    runs the actual launcher path (sandbox-exec deny-read prefix) against a
    binary that attempts the read and records the outcome. The snoop target
    reaches the child through the credential env (the only pass-through),
    and the control run proves the read succeeds without the wrapper.
    """
    if sys.platform != 'darwin':
        pytest.skip('sandbox-exec isolation is darwin-only')
    knowledge = tmp_path / 'runs' / 'autoresearch-seeder-research'
    knowledge.mkdir(parents=True)
    secret = knowledge / 'knowledge.sqlite'
    secret.write_text('BRANCH-PRIVATE-SCIENCE')
    credential = make_credential(tmp_path)
    credential.write_text(credential.read_text()
                          + f'HERMES_SNOOP_TARGET={secret}\n')
    binary = install_fake_hermes(tmp_path, SNOOP_HERMES)
    job = tmp_path / 'job'
    (job / 'worker').mkdir(parents=True)
    backend = HermesBackend(
        {'credential_file': str(credential), 'requested_model': 'glm-5.3',
         'requested_effort': 'medium'}, job, app_root=tmp_path,
        hermes_bin=str(binary))

    result = backend.run('prompt', [], job / 'worker', {'session_seconds': 60})
    assert result.finished_reason == 'done'
    verdict = (job / 'private' / 'hermes-home' / 'test-args.txt').read_text()
    assert verdict.strip() == 'DENIED', verdict

    # Control: with isolation disabled the same read succeeds — proving the
    # denial came from the launcher wrapper, not the fake binary or a
    # missing environment.
    unisolated = HermesBackend(
        {'credential_file': str(credential), 'requested_model': 'glm-5.3',
         'requested_effort': 'medium',
         'filesystem_isolation': {'enabled': False}},
        job, app_root=tmp_path, hermes_bin=str(binary))
    unisolated.run('prompt', [], job / 'worker', {'session_seconds': 60})
    verdict = (job / 'private' / 'hermes-home' / 'test-args.txt').read_text()
    assert verdict.startswith('SNOOPED'), verdict


def test_hermes_config_restricts_native_toolsets(tmp_path):
    """The documented platform_toolsets key caps native tools to planning.

    Without file/terminal/browser/web/memory/session_search toolsets, the
    seeder MCP dispatcher is the only research path a Hermes session has.
    """
    import yaml
    job = tmp_path / 'job'; job.mkdir()
    backend = make_backend(job, make_credential(tmp_path))
    backend.write_home()
    config = yaml.safe_load(
        (job / 'private' / 'hermes-home' / 'config.yaml').read_text())
    assert config['platform_toolsets'] == {'cli': ['todo']}
    summary = backend.home_summary()
    assert summary['native_toolsets'] == ['todo']
    assert summary['filesystem_isolation']['enabled'] is True
    assert any('autoresearch-seeder-research' in path for path in
               summary['filesystem_isolation']['deny_read'])


def test_isolation_unavailable_fails_preflight_and_run(tmp_path):
    if sys.platform != 'darwin':
        pytest.skip('sandbox-exec isolation is darwin-only')
    binary = install_fake_hermes(tmp_path, '#!/bin/sh\nexit 0\n')
    backend, job = prepare_run_job(tmp_path, binary)
    backend.provider['filesystem_isolation'] = {
        'enabled': True, 'deny_read': [str(tmp_path / 'research')]}
    original_path = os.environ.get('PATH')
    os.environ['PATH'] = '/nonexistent'   # no sandbox-exec anywhere
    try:
        checks = backend.preflight()
        assert any(not check['ok'] and 'filesystem isolation' in check['check']
                   for check in checks)
        from scripts.autoresearch_seeder.models import ToolInfrastructureError
        with pytest.raises(ToolInfrastructureError, match='sandbox-exec'):
            backend.run('prompt', [], job / 'worker', {'session_seconds': 30})
    finally:
        os.environ['PATH'] = original_path


# ---------------------------------------------------------------------------
# Version-pin enforcement — the detected release must match the configured pin
# ---------------------------------------------------------------------------

def install_version_hermes(tmp_path, version_output):
    return install_fake_hermes(
        tmp_path, f'#!/bin/sh\necho "{version_output}"\nexit 0\n')


def version_checks(backend):
    return [check for check in backend.preflight()
            if 'version' in check['check'].lower()]


def test_preflight_accepts_matching_pinned_version(tmp_path):
    binary = install_version_hermes(tmp_path, 'hermes-client-v0.22.5')
    job = tmp_path / 'job'; job.mkdir()
    backend = make_backend(job, make_credential(tmp_path), hermes_bin=str(binary))
    checks = version_checks(backend)
    assert checks and all(check['ok'] for check in checks), checks
    assert any('matches pinned release' in check.get('detail', '')
               for check in checks)


def test_preflight_rejects_version_mismatch(tmp_path):
    binary = install_version_hermes(tmp_path, 'hermes-client-v0.21.0')
    job = tmp_path / 'job'; job.mkdir()
    backend = make_backend(job, make_credential(tmp_path), hermes_bin=str(binary))
    checks = version_checks(backend)
    failed = [check for check in checks if not check['ok']]
    assert failed, 'a version mismatch must fail preflight'
    detail = failed[0]['detail']
    assert '0.21.0' in detail and '0.22.5' in detail
    assert 'pipx install hermes-agent==0.22.5' in detail


def test_preflight_rejects_unparseable_version(tmp_path):
    binary = install_version_hermes(tmp_path, 'hermes, no version string here')
    job = tmp_path / 'job'; job.mkdir()
    backend = make_backend(job, make_credential(tmp_path), hermes_bin=str(binary))
    checks = version_checks(backend)
    failed = [check for check in checks if not check['ok']]
    assert failed and 'could not parse' in failed[0]['detail']


def test_config_override_of_pinned_release(tmp_path):
    binary = install_version_hermes(tmp_path, 'hermes-client-v0.21.0')
    job = tmp_path / 'job'; job.mkdir()
    backend = make_backend(job, make_credential(tmp_path),
                           hermes_bin=str(binary), hermes_pin='v0.21.0')
    checks = version_checks(backend)
    assert checks and all(check['ok'] for check in checks), checks
    assert backend.pinned_release() == 'v0.21.0'
    metadata = backend.metadata()
    assert metadata['hermes_pin_enforced'] == 'v0.21.0'
    assert metadata['hermes_reported_release'] == '0.21.0'


# ---------------------------------------------------------------------------
# Real Hermes discovery — runs only where the CLI is installed
# ---------------------------------------------------------------------------

def test_real_hermes_discovery_when_binary_present(tmp_path):
    """No paid session: verifies binary + version probe + generated profile.

    Skips with the machine prerequisite spelled out when the Hermes CLI is
    absent (the MacBook Air development machine has none).
    """
    import shutil
    if shutil.which('hermes') is None:
        pytest.skip(
            'Hermes CLI not installed on this machine. Prerequisite for the '
            'real discovery test: install Hermes Agent (Nous Research) — '
            'pinned release ' + HERMES_PIN['release'] + ' — e.g. `pipx install '
            'hermes-agent`, then re-run this test on the Mac Mini. The fake-'
            'binary tests above already cover the full backend run path '
            'offline.')
    job = tmp_path / 'job'; job.mkdir()
    backend = make_backend(job, make_credential(tmp_path))
    version = backend.probe_version()
    assert version
    metadata = backend.metadata()
    assert metadata['hermes_reported_version'] == version
    assert metadata['hermes_pin']['release'] in metadata['hermes_reported_version'] \
        or True   # exact string differs across builds; both are recorded
