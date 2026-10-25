"""Demo fixture evaluator: same envelope, CLI and freeze rules as the chemistry task.

Isolated generation (sandbox-exec on macOS), unchanged trusted verification,
receipt envelope identical in shape to tasks/dfthcsos/evaluator.py so the
seeder exercises one adapter contract. Never a real benchmark score.
"""
import argparse
import hashlib
import json
import math
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROTOCOL = json.loads((HERE / 'protocol.json').read_text())


def digest(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def verify_sources():
    for name, expected in PROTOCOL.get('official_sha256', {}).items():
        if digest(HERE / name) != expected:
            raise ValueError('Official source mismatch: ' + name)


def run_process(command, directory, env, timeout, memory_gib=None,
                scratch_directory=None, scratch_limit_bytes=2 * 2**20):
    """Bound the subprocess tree; candidate stdout is never trusted as a score."""
    with tempfile.TemporaryFile(mode='w+') as log:
        proc = subprocess.Popen(command, cwd=str(directory), env=env, stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True)
        started = time.monotonic()
        psutil = None
        try:
            import psutil
        except ImportError:
            psutil = None
        try:
            while proc.poll() is None:
                if time.monotonic() - started > timeout:
                    proc.kill()
                    raise TimeoutError(f'Process exceeded {timeout} seconds')
                if os.fstat(log.fileno()).st_size > 4 * 2**20:
                    proc.kill()
                    raise ValueError('Process log exceeded 4 MiB')
                if psutil is not None and memory_gib:
                    try:
                        parent = psutil.Process(proc.pid)
                        tree = [parent] + parent.children(recursive=True)
                        rss = sum(p.memory_info().rss for p in tree if p.is_running())
                        if rss > memory_gib * 2**30:
                            proc.kill()
                            raise MemoryError(f'Process tree exceeded {memory_gib} GiB RSS')
                    except psutil.NoSuchProcess:
                        pass
                time.sleep(0.05)
            log.seek(0)
            text = log.read()
            if proc.returncode:
                raise RuntimeError(text[-4000:])
            return text
        finally:
            if proc.poll() is None:
                proc.kill()


def profile(job, output):
    if sys.platform != 'darwin':
        return None
    reads = ['/System', '/usr', '/bin', '/sbin', '/Library', '/dev', '/private/etc',
             '/private/var/db', str(Path(sys.base_prefix).resolve()),
             str(Path(sys.executable).resolve()), str(job.resolve())]
    return ('(version 1)\n(allow default)\n(deny network*)\n(deny file-read* file-write*)\n'
            '(allow file-read-metadata)\n(allow file-read* (literal "/"))\n'
            + ''.join(f'(allow file-read* (subpath {json.dumps(p)}))\n' for p in reads)
            + f'(allow file-write* (subpath {json.dumps(str(Path(output).resolve()))}))\n'
            '(allow file-write* (literal "/dev/null"))\n')


def clean_environment(output):
    return {'PATH': '/usr/bin:/bin', 'HOME': str(output), 'TMPDIR': str(output),
            'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONHASHSEED': '0'}


def copy_submission(source, destination):
    """Freeze regular submission files only; reject links, devices, oversize."""
    source = Path(source)
    if source.is_symlink() or not source.is_dir():
        raise ValueError('Regular submission directory required')
    names = [p for p in source.iterdir() if p.name == 'submission.npz']
    if not names or not (source / 'submission.npz').is_file():
        raise ValueError('submission.npz required')
    total = 0
    manifest = {}
    destination.mkdir()
    for path in names:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('Submission links/special files forbidden')
        total += info.st_size
        if total > PROTOCOL['max_submission_bytes']:
            raise ValueError('Submission exceeds size limit')
        shutil.copyfile(path, destination / path.name)
        manifest[path.name] = digest(destination / path.name)
    return manifest


def verify_submission(directory, salt, shots):
    """Trusted verification: deterministic cost from the frozen submission."""
    text = (Path(directory) / 'submission.npz').read_text()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError('Empty submission')
    base = 0.0
    for line in lines:
        parts = line.split()
        if parts[0] == 'BASE' and len(parts) == 2 and parts[1].isdigit():
            base += int(parts[1])
        elif parts[0] == 'TRICK' and len(parts) == 2 and parts[1].isdigit():
            base += int(parts[1]) * 0.5
        elif parts == ['JUNK']:
            base += 25
        else:
            raise ValueError('Malformed submission line: ' + line[:100])
    salt_text = salt or ''
    salt_factor = 1 + ((sum(ord(c) for c in salt_text) * len(salt_text)) % 7) / 100.0
    cost = max(1.0, base * salt_factor)
    expected_shots = len(lines) * PROTOCOL['shots_per_address']
    return {'official': {'status': 'PASS', 'score': cost,
                         'verified_shots': expected_shots},
            'validation': {'shots_per_address': shots,
                           'expected_shots': expected_shots,
                           'metric_preflight': True}}


def score_result(result, smoke=False):
    official = result.get('official', {})
    validation = result.get('validation', {})
    if official.get('status') != 'PASS':
        raise ValueError('Official verifier did not pass')
    shots = 1 if smoke else PROTOCOL['shots_per_address']
    if validation.get('shots_per_address') != shots \
            or validation.get('metric_preflight') is not True:
        raise ValueError('Wrong verification workload or missing metric preflight')
    if not validation.get('expected_shots') \
            or official.get('verified_shots') != validation['expected_shots']:
        raise ValueError('Incomplete verification')
    cost = official.get('score')
    if isinstance(cost, bool) or not isinstance(cost, (float, int)) \
            or not math.isfinite(cost) or cost <= 0:
        raise ValueError('Invalid official cost')
    if not smoke:
        result['combined_score'] = PROTOCOL['reference_cost'] / cost
    return result


def evaluate_program(program, output, smoke=False, salt=None, submission=None):
    verify_sources()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    salt = salt or PROTOCOL['development_salt']
    env = clean_environment(output)
    with tempfile.TemporaryDirectory(prefix='seed-demo-job-') as temporary:
        job = Path(temporary)
        generated = job / 'output'
        generated.mkdir()
        manifest = None
        if submission is None:
            program = Path(program).resolve()
            shutil.copyfile(program, job / 'program.py')
            wrapper = job / 'run_candidate.py'
            wrapper.write_text("import runpy,sys\nfrom pathlib import Path\n"
                               "sys.path.insert(0,str(Path(__file__).parent))\n"
                               "p=sys.argv.pop(1)\n"
                               "runpy.run_path(p,run_name='__main__')\n")
            sandbox = job / 'generator.sb'
            text = profile(job, generated)
            command = [sys.executable, '-I', str(wrapper), str(job / 'program.py'),
                       str(generated)]
            if text is not None:
                sandbox.write_text(text)
                command = ['/usr/bin/sandbox-exec', '-f', str(sandbox)] + command
            (output / 'phase.json').write_text(json.dumps({'stage': 'generation'}))
            log = run_process(command, job, env, PROTOCOL['generator_timeout_seconds'],
                              memory_gib=PROTOCOL['memory_gib'],
                              scratch_directory=generated,
                              scratch_limit_bytes=PROTOCOL['max_submission_bytes'])
            (output / 'generator.log').write_text(log)
            manifest = copy_submission(generated, output / 'submission')
            shutil.copyfile(program, output / 'program.py')
        else:
            manifest = copy_submission(submission, output / 'submission')
    (output / 'phase.json').write_text(json.dumps({'stage': 'verification'}))
    result = verify_submission(output / 'submission', salt,
                               1 if smoke else PROTOCOL['shots_per_address'])
    result.update(scope='smoke' if smoke else 'full-development',
                  status=result['official']['status'],
                  source_sha256=digest(program) if program is not None else None,
                  submission_files_sha256=manifest,
                  protocol_sha256=digest(HERE / 'protocol.json'),
                  salt=salt, seconds=time.monotonic() - started)
    result['logs'] = {name: (output / name).read_text()[-16000:]
                      for name in ('generator.log',) if (output / name).exists()}
    score_result(result, smoke)
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def evaluate(program_path):
    try:
        verify_sources()
        return evaluate_program(program_path,
                                ROOT / 'outputs' / f'seed-demo-{uuid.uuid4().hex}')
    except Exception as exc:
        return {'combined_score': 0.0, 'error': str(exc), 'status': 'FAIL'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--program', type=Path)
    group.add_argument('--submission', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--salt')
    args = parser.parse_args()
    print(json.dumps(evaluate_program(args.program, args.output, args.smoke,
                                      args.salt, args.submission), indent=2))
