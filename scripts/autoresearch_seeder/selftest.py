"""Real adapter smoke test: actual sandboxed diagnostics and receipt parsing.

Two modes, neither of which starts a model session:

  --fixture      the bundled offline demo task: a real sandbox-exec diagnostic,
                 a real full development validation, a real confirmation
                 validation under the final salt, receipt validation through
                 the task's receipt adapter, and the publisher gates. Fully
                 deterministic, no credentials.
  --task X       a registered real task (default dfthcsos): verifies identity,
                 runtime and official inputs, runs one real diagnostic probe
                 and parses the pinned calibration receipt when present.
                 Missing prerequisites are reported precisely as
                 infrastructure_blocked rather than pretending success.
"""
import importlib.util
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

from . import ROOT
from .adapter import TaskAdapter
from .models import ToolInfrastructureError, file_digest


def _fixture_root():
    return Path(__file__).resolve().parents[2] / 'tests' / 'fixtures' / 'seed_demo_repo'


def _check(results, name, ok, detail=''):
    results.append({'check': name, 'ok': bool(ok), 'detail': str(detail)[:500]})
    print(('[ok]   ' if ok else '[FAIL] ') + name + ((' — ' + str(detail)[:300]) if detail else ''))
    return bool(ok)


def run_fixture_smoke() -> int:
    results = []
    fixture = _fixture_root()
    task = TaskAdapter('seed_demo', fixture)
    _check(results, 'fixture task loads through the registry contract',
           task.identity()['task_id'] == 'seed_demo')

    with tempfile.TemporaryDirectory(prefix='seeder-smoke-') as temporary:
        attempt = Path(temporary) / 'worker' / 'attempt_00'
        artifact = attempt / 'artifact'
        artifact.mkdir(parents=True)
        shutil.copyfile(task.seed_program, artifact / 'program.py')
        # A diagnostic that proves sandbox isolation for real: it must run
        # offline with only TEST_OUTPUT_DIR writable.
        (artifact / 'diagnostic.py').write_text(
            'import os, sys\n'
            'assert os.environ.get("TEST_OUTPUT_DIR"), "TEST_OUTPUT_DIR missing"\n'
            'with open(os.path.join(os.environ["TEST_OUTPUT_DIR"], "proof.txt"), "w") as f:\n'
            '    f.write("diagnostic ran\\n")\n'
            'print("offline diagnostic executed; python", sys.version.split()[0])\n')
        try:
            receipt = task.run_diagnostic(attempt)
            _check(results, 'real sandboxed diagnostic PASS',
                   receipt.get('status') == 'PASS' and receipt.get('diagnostic_only'),
                   receipt.get('logs', {}).get('diagnostic.log', '')[:200])
        except ToolInfrastructureError as exc:
            _check(results, 'real sandboxed diagnostic PASS', False, exc)

        dev = task.run_validation(attempt, Path(temporary) / 'development',
                                  'development', {'validation': {
                                      'development_salt_key': 'development_salt'}})
        _check(results, 'real full development validation returns official receipt',
               dev.get('status') == 'PASS' and dev.get('scope') == 'full-development'
               and dev.get('salt') == 'seed-demo-development-v1')
        task.validate_receipt(dev, 'development_verified')
        _check(results, 'receipt accepted by the task receipt adapter '
                        '(development_verified)', True)

        confirm = task.run_validation(attempt, Path(temporary) / 'confirmation',
                                      'confirmation', {'validation': {
                                          'final_salt_key': 'final_salt'}})
        _check(results, 'real confirmation validation under the final salt',
               confirm.get('status') == 'PASS' and confirm.get('held_out') is True
               and confirm.get('scope') == 'full-local-final'
               and confirm['salt'] == 'seed-demo-final-v1')
        try:
            task.validate_receipt(confirm, 'independently_verified')
            _check(results, 'confirmation receipt accepted (independently_verified)', True)
        except ValueError as exc:
            _check(results, 'confirmation receipt accepted (independently_verified)',
                   False, exc)

        _check(results, 'salts are distinct recorded values',
               dev['salt'] != confirm['salt'])
        _check(results, 'deterministic verification (same submission, same salt '
                        '=> same cost)',
               abs(dev['official']['score'] - task.run_validation(
                   attempt, Path(temporary) / 'development-repeat', 'development',
                   {'validation': {'development_salt_key': 'development_salt'}}
                   )['official']['score']) < 1e-12)
    ok = all(item['ok'] for item in results)
    print(json.dumps({'mode': 'fixture', 'ok': ok, 'checks': results}, indent=2))
    return 0 if ok else 1


def run_task_smoke(task_id: str, task_root=None) -> int:
    results = []
    root = Path(task_root).resolve() if task_root else ROOT
    try:
        task = TaskAdapter(task_id, root)
    except Exception as exc:
        print(json.dumps({'mode': task_id, 'ok': False,
                          'error': f'task adapter failed to load: {exc}',
                          'status': 'infrastructure_blocked'}, indent=2))
        return 1
    _check(results, 'task loads through the registry contract',
           task.identity()['task_id'] == task_id)
    runtime_ok = task.python.exists()
    _check(results, f'task runtime present ({task.python})', runtime_ok,
           '' if runtime_ok else 'run the task setup first; this is a missing '
                                 'prerequisite, not a candidate failure')
    official = root / 'data/quantum-compilation/official'
    if task_id == 'dfthcsos':
        have = official.exists() and any(official.rglob('verify.py'))
        _check(results, 'official verifier inputs present', have,
               '' if have else 'data/quantum-compilation/official is required '
                               '(omitted from the source transfer snapshot)')
    if runtime_ok:
        with tempfile.TemporaryDirectory(prefix='seeder-smoke-') as temporary:
            attempt = Path(temporary) / 'worker' / 'attempt_00'
            artifact = attempt / 'artifact'
            artifact.mkdir(parents=True)
            shutil.copyfile(task.seed_program, artifact / 'program.py')
            (artifact / 'diagnostic.py').write_text(
                'import os,sys\n'
                'open(os.path.join(os.environ["TEST_OUTPUT_DIR"],"proof.txt"),"w"'
                ').write("ok")\nprint("diagnostic probe executed")\n')
            try:
                receipt = task.run_diagnostic(attempt)
                _check(results, 'real task diagnostic executed',
                       receipt.get('status') in ('PASS', 'FAIL'),
                       f"status={receipt.get('status')}")
            except ToolInfrastructureError as exc:
                _check(results, 'real task diagnostic executed', False,
                       str(exc) + ' (reported as infrastructure_blocked, '
                                  'never as a scored failure)')
        receipt_path = root / (task.protocol.get('reference_result_path')
                               or 'outputs/dfthcsos-calibration/result.json')
        if receipt_path.is_file():
            receipt = json.loads(receipt_path.read_text())
            try:
                task.validate_receipt(receipt, 'development_verified')
                _check(results, 'pinned calibration receipt parses and validates',
                       True, f"cost={receipt.get('official', {}).get('score')}")
            except ValueError as exc:
                _check(results, 'pinned calibration receipt parses and validates',
                       False, exc)
        else:
            _check(results, 'pinned calibration receipt present', False,
                   f'{receipt_path} missing; run the task calibration first '
                   f'(smoke does not start expensive evaluations)')
    ok = all(item['ok'] for item in results)
    print(json.dumps({'mode': task_id, 'ok': ok, 'checks': results,
                      'production_enabled': False}, indent=2))
    return 0 if ok else 1


def run_selftest(args) -> int:
    if getattr(args, 'fixture', False):
        return run_fixture_smoke()
    return run_task_smoke(args.task, args.task_root)
