"""Hermes integration with the existing, unchanged official DQI task engine.

Only the orchestration envelope differs: task-side generation/verification,
resource limits, source pins, full shots and normalization remain task-owned.
Confirmation grades the saved development circuit, without regenerating it.
"""
import contextlib
import fcntl
import importlib.util
import json
import os
import shutil
import stat
import tempfile
import time
from pathlib import Path

from .models import ToolInfrastructureError, file_digest

FINAL_SALT = 'literature-reproduction-acceptance-held-out-v1'


@contextlib.contextmanager
def environment(adapter, artifact):
    ev = adapter._task_module('evaluator')
    runtime = adapter.root/adapter.manifest['runtime']
    if not runtime.is_file():
        raise ToolInfrastructureError('Registered DQI interpreter is missing')
    ev.verify_sources()
    original_python, original_profile = ev.PYTHON, ev.candidate_profile
    with tempfile.TemporaryDirectory(prefix='hermes-dqi-input-') as temp:
        frozen = Path(temp)/'artifact'
        shutil.copytree(artifact, frozen)
        def profile(job, output, extra_reads=()):
            return original_profile(job, output, [*extra_reads, frozen,
                                                   runtime.parent.parent.resolve()])
        ev.PYTHON = runtime
        ev.candidate_profile = profile
        try:
            yield ev, frozen
        finally:
            ev.PYTHON, ev.candidate_profile = original_python, original_profile


def diagnostic(adapter, attempt):
    artifact = Path(attempt).resolve()/'artifact'
    if not (artifact/'diagnostic.py').is_file():
        return {'status': 'FAIL', 'diagnostic_only': True, 'error': 'Save artifact/diagnostic.py first'}
    spec = importlib.util.spec_from_file_location('hermes_dqi_candidate_validation',
                     adapter.root/'scripts/candidate_validation.py')
    started = time.monotonic()
    try:
        with environment(adapter, artifact) as (ev, frozen):
            cv = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cv)
            cv.dqi = ev
            # The existing credential-free, network-free diagnostic sandbox and
            # shared quick-slot admission run the worker's own saved diagnostic.
            with tempfile.TemporaryDirectory(prefix='hermes-dqi-diagnostic-') as temp:
                output = Path(temp)/'output'
                receipt = cv.diagnose(frozen/'diagnostic.py', output,
                         extra_env={'ARTIFACT_DIR': str(frozen)})
                log = (output/'diagnostic.log').read_text() if (output/'diagnostic.log').exists() else ''
                receipt.update(status='PASS', logs={'diagnostic.log': log[-16000:]})
    except ToolInfrastructureError:
        raise
    except Exception as error:
        receipt = adapter._classify(error)
    receipt.update(diagnostic_only=True, seconds=time.monotonic()-started)
    return receipt


def envelope(adapter, receipt, program, circuit, salt, which):
    sha = file_digest(circuit)
    receipt.update(status='PASS', source_sha256=file_digest(program),
        protocol_sha256=adapter.protocol_sha256, salt=salt,
        submission_files_sha256={'dqi.kmb': sha},
        scope='full-local-final' if which == 'confirmation' else 'full-development')
    receipt['official'] = dict(receipt['official'], submission_sha256=sha)
    if which == 'confirmation':
        receipt.update(held_out=True, submission_reused=True)
    return receipt


def validate(adapter, attempt, output, which, config, submission_dir=None):
    output = Path(output).resolve()
    artifact = Path(attempt).resolve()/'artifact'
    program = artifact/'program.py'
    if output.exists():
        raise ToolInfrastructureError('DQI validation output already exists')
    salt = adapter.salt(which, config)
    started = time.monotonic()
    try:
        with environment(adapter, artifact) as (ev, frozen):
            if which == 'development':
                # The trusted wrapper only exposes this frozen source bundle to
                # the existing task sandbox. Candidate code gains no broader read.
                wrapper = frozen.parent/'generate.py'
                wrapper.write_text('import runpy,sys\n'
                    f'sys.path.insert(0,{str(frozen)!r})\n'
                    f'sys.argv[0]={str(frozen/"program.py")!r}\n'
                    f'runpy.run_path({str(frozen/"program.py")!r},run_name="__main__")\n')
                receipt = ev.evaluate_program(wrapper, output, smoke=False,
                                     salt=salt, preflight=True, isolate_verifier=True)
                dest = output/'submission';dest.mkdir()
                circuit = dest/'dqi.kmb'
                (output/'dqi.kmb').replace(circuit)
                return envelope(adapter, receipt, frozen/'program.py', circuit, salt, which)
            if which != 'confirmation' or submission_dir is None:
                raise ToolInfrastructureError('DQI confirmation needs the saved development circuit')
            circuit = Path(submission_dir)/'dqi.kmb'
            info = circuit.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= 2*2**30:
                raise ToolInfrastructureError('Frozen DQI circuit must be a regular, unlinked file <=2 GiB')
            before = file_digest(circuit)
            output.mkdir(parents=True)
            locks = adapter.root/'work/runtime-locks';locks.mkdir(parents=True, exist_ok=True)
            with (locks/'dqi-cpu.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                verifier = ev.OFFICIAL/'verifiers/dqi/verify_submission_dqi.py'
                command = [str(ev.PYTHON), '-I', str(verifier), str(circuit)]
                for key in ('m','n','degree','r','batch_size','log2_delta','max_workers'):
                    command += ['--'+key.replace('_','-'), str(ev.PROTOCOL[key])]
                command += ['--num-shots',str(ev.PROTOCOL['num_shots']),'--salt',salt]
                sb = output/'verifier.sb'
                sb.write_text(ev.candidate_profile(output, output, [verifier.parent, circuit.parent]))
                env = {'PATH':'/usr/bin:/bin','HOME':str(output),'TMPDIR':str(output),
                       'PYTHONDONTWRITEBYTECODE':'1', **{k:'1' for k in
                         ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS',
                          'VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS')}}
                log = ev.run_process(['/usr/bin/sandbox-exec','-f',str(sb)]+command,
                         output, env, ev.PROTOCOL['verifier_timeout_seconds'])
                (output/'verifier.json').write_text(log)
                receipt = ev.score_result(json.loads(log), smoke=False)
            if before != file_digest(circuit):
                raise ToolInfrastructureError('Frozen DQI circuit changed during confirmation')
            receipt.update(seconds=time.monotonic()-started)
            return envelope(adapter, receipt, frozen/'program.py', circuit, salt, which)
    except ToolInfrastructureError:
        raise
    except Exception as error:
        return adapter._classify(error)
