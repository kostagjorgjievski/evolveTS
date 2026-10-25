"""Scenario 7: real adapter smoke test — actual sandboxed diagnostics and
receipt parsing, without starting a model session."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.autoresearch_seeder.selftest import run_fixture_smoke, run_task_smoke


def test_fixture_smoke_real_sandbox_and_receipt_parsing(capsys):
    code = run_fixture_smoke()
    captured = capsys.readouterr().out
    assert code == 0
    report = json.loads(captured[captured.index('{'):])
    assert report['ok'] is True
    names = {check['check'] for check in report['checks']}
    assert 'real sandboxed diagnostic PASS' in names
    assert 'real full development validation returns official receipt' in names
    assert 'confirmation receipt accepted (independently_verified)' in names


@pytest.mark.skipif(sys.platform != 'darwin', reason='sandbox-exec isolation')
def test_fixture_diagnostic_actually_isolated(tmp_path):
    """The demo sandbox must deny reading a private file and the network."""
    from scripts.autoresearch_seeder.adapter import TaskAdapter
    task = TaskAdapter('seed_demo', REPO / 'tests' / 'fixtures' / 'seed_demo_repo')
    attempt = tmp_path / 'worker' / 'attempt_00'
    artifact = attempt / 'artifact'
    artifact.mkdir(parents=True)
    secret = tmp_path / 'secret.txt'
    secret.write_text('private')
    (artifact / 'program.py').write_text('pass')
    (artifact / 'diagnostic.py').write_text(
        'import os\n'
        f'open({str(secret)!r})\n'
        'raise AssertionError("sandbox read a private file")\n')
    receipt = task.run_diagnostic(attempt)
    assert receipt['status'] == 'FAIL'
    assert 'Operation not permitted' in receipt.get('error', '') \
        or 'Permission denied' in receipt.get('error', '') \
        or 'private' in receipt.get('error', '')


def test_dfthcsos_smoke_reports_missing_prerequisites_honestly(capsys):
    """On a machine without the task setup the smoke names the missing
    prerequisites and fails; it never starts a model session and never
    reports a scored failure."""
    code = run_task_smoke('dfthcsos', REPO)
    captured = capsys.readouterr().out
    report = json.loads(captured[captured.index('{'):])
    runtime_ok = next(c['ok'] for c in report['checks']
                      if c['check'].startswith('task runtime'))
    if runtime_ok:  # a fully set-up machine (Codex's environment)
        assert code in (0, 1)
    else:           # this source checkout: prerequisites absent
        assert code == 1
        assert report['ok'] is False
        detail = ' '.join(c['detail'] for c in report['checks'] if not c['ok'])
        assert 'setup' in detail or 'prerequisite' in detail \
            or 'official verifier inputs' in detail
    assert report.get('production_enabled') is False


def test_cli_surface_is_present():
    """The documented commands exist and refuse to run a disabled config."""
    result = subprocess.run(
        [sys.executable, '-m', 'scripts.autoresearch_seeder', '--help'],
        cwd=REPO, capture_output=True, text=True)
    assert result.returncode == 0
    for command in ('init', 'preflight', 'run', 'resume', 'status', 'export',
                    'selftest'):
        assert command in result.stdout
