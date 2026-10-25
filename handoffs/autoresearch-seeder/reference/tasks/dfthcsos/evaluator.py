"""Isolated DFTHC-SOS generation and unchanged official full verification."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import time
import uuid

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OFFICIAL=ROOT/'data/quantum-compilation/official'
METRIC=ROOT/'data/quantum-compilation/metric/metric.py'
PYTHON=ROOT/'.dfthcsos-venv/bin/python'
PROTOCOL=json.loads((HERE/'protocol.json').read_text())
BASELINE=OFFICIAL/'sample_submission/dfthcsos'
# Shared, process-tree resource limiter; importing it does not start a DQI job.
_spec=importlib.util.spec_from_file_location('_dfthcsos_process_limits',ROOT/'tasks/dqi/evaluator.py')
_limits=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_limits)
run_process=_limits.run_process


def digest(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def verify_sources():
    for name,expected in PROTOCOL['official_sha256'].items():
        if digest(OFFICIAL/name)!=expected:raise ValueError('Official source mismatch: '+name)
    if digest(METRIC)!=PROTOCOL['metric_sha256']:raise ValueError('Pinned Kaggle metric changed')


def profile(job,output):
    reads=['/System','/usr','/bin','/sbin','/Library','/dev','/private/etc','/private/var/db',
           str(Path(sys.base_prefix).resolve()),str((ROOT/'.dfthcsos-venv').resolve()),str(job.resolve()),
           str(OFFICIAL/'verifiers/dfthcsos'),str(BASELINE)]
    return ('(version 1)\n(allow default)\n(deny network*)\n(deny file-read* file-write*)\n'
            '(allow file-read-metadata)\n(allow file-read* (literal "/"))\n'+
            f'(allow file-read* (literal {json.dumps(str(OFFICIAL/"verifiers"))}))\n'+
            ''.join(f'(allow file-read* (subpath {json.dumps(p)}))\n' for p in reads)+
            f'(allow file-write* (subpath {json.dumps(str(output.resolve()))}))\n'+
            '(allow file-write* (literal "/dev/null"))\n')


def clean_environment(output):
    return {'PATH':'/usr/bin:/bin','HOME':str(output),'TMPDIR':str(output),'PYTHONDONTWRITEBYTECODE':'1',
            'PYTHONHASHSEED':'0',**{k:'1' for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS',
            'MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS']}}


def copy_submission(source,destination):
    """Freeze regular submission files only; reject links, devices and oversized output."""
    source=Path(source)
    if source.is_symlink() or not source.is_dir():raise ValueError('Regular submission directory required')
    names=[p for p in source.iterdir() if p.name=='submission.npz' or p.name.startswith('angle_k_')]
    if not names or not (source/'submission.npz').is_file():raise ValueError('submission.npz and ANGLE files required')
    total=0;manifest={}
    destination.mkdir()
    for path in names:
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise ValueError('Submission links/special files forbidden')
        total+=info.st_size
        if total>PROTOCOL['max_submission_bytes']:raise ValueError('Submission exceeds size limit')
        shutil.copyfile(path,destination/path.name)
        manifest[path.name]=digest(destination/path.name)
    return manifest


def score_result(result,smoke=False):
    official=result.get('official',{});validation=result.get('validation',{})
    if official.get('status')!='PASS':raise ValueError('Official verifier did not pass')
    shots=1 if smoke else PROTOCOL['shots_per_address']
    if validation.get('shots_per_address')!=shots or validation.get('metric_preflight') is not True:
        raise ValueError('Wrong verification workload or missing metric preflight')
    if not validation.get('expected_shots') or official.get('verified_shots')!=validation['expected_shots']:
        raise ValueError('Incomplete verification')
    cost=official.get('score')
    if isinstance(cost,bool) or not isinstance(cost,(float,int)) or not math.isfinite(cost) or cost<=0:
        raise ValueError('Invalid official cost')
    if not smoke:
        if not PROTOCOL.get('reference_cost'):raise ValueError('Full baseline calibration required')
        result['combined_score']=PROTOCOL['reference_cost']/cost
    return result


def evaluate_program(program,output,smoke=False,salt=None,submission=None):
    verify_sources()
    if sys.platform!='darwin':raise RuntimeError('Candidate isolation currently requires macOS')
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();locks=ROOT/'work/runtime-locks';locks.mkdir(parents=True,exist_ok=True)
    with (locks/'dqi-cpu.lock').open('a') as lock:
        # Share the memory-heavy quantum execution slot with existing DQI work.
        fcntl.flock(lock,fcntl.LOCK_EX)
        env=clean_environment(output)
        manifest=None
        with tempfile.TemporaryDirectory(prefix='dfthcsos-job-') as temporary:
            job=Path(temporary);generated=job/'output';generated.mkdir()
            if submission is None:
                program=Path(program).resolve()
                shutil.copyfile(program,job/'program.py')
                if program.parent.name=='artifact':
                    total=0;file_count=0
                    for path in program.parent.rglob('*'):
                        if path.is_symlink():raise ValueError('Artifact links forbidden')
                        if path.is_dir():continue
                        info=path.lstat()
                        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise ValueError('Regular artifact files required')
                        total+=info.st_size;file_count+=1
                        if file_count>4096:raise ValueError('Artifact exceeds4096 files')
                        if total>128*2**20:raise ValueError('Artifact source/data exceeds128MiB')
                        target=job/path.relative_to(program.parent);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
                wrapper=job/'run_candidate.py'
                wrapper.write_text("import runpy,sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path(__file__).parent))\np=sys.argv.pop(1)\nrunpy.run_path(p,run_name='__main__')\n")
                sandbox=job/'generator.sb';sandbox.write_text(profile(job,generated))
                command=['/usr/bin/sandbox-exec','-f',str(sandbox),str(PYTHON),'-I',str(wrapper),str(job/'program.py'),str(generated)]
                (output/'phase.json').write_text(json.dumps({'stage':'generation'}))
                log=run_process(command,job,env,PROTOCOL['generator_timeout_seconds'],memory_gib=PROTOCOL['memory_gib'],scratch_directory=generated,scratch_limit_bytes=PROTOCOL['max_submission_bytes'])
                (output/'generator.log').write_text(log)
                manifest=copy_submission(generated,output/'submission')
                shutil.copyfile(program,output/'program.py')
            else:manifest=copy_submission(submission,output/'submission')
        (output/'phase.json').write_text(json.dumps({'stage':'verification'}))
        command=[str(PYTHON),'-I',str(HERE/'verify_runner.py'),str(output/'submission'),
                 '--metric',str(METRIC),'--shots-per-address',str(1 if smoke else PROTOCOL['shots_per_address']),
                 '--salt',salt or PROTOCOL['development_salt']]
        log=run_process(command,output,env,PROTOCOL['verifier_timeout_seconds'],memory_gib=PROTOCOL['memory_gib'])
        (output/'verifier.log').write_text(log)
        result=json.loads(log)
        result.update(scope='smoke' if smoke else 'full-development',status=result['official']['status'],
                      source_sha256=digest(program) if program is not None else None,
                      submission_files_sha256=manifest,protocol_sha256=digest(HERE/'protocol.json'),
                      salt=salt or PROTOCOL['development_salt'],seconds=time.monotonic()-started)
        result['logs']={name:(output/name).read_text()[-16000:] for name in ('generator.log','verifier.log') if (output/name).exists()}
        score_result(result,smoke)
        (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        return result


def evaluate(program_path):
    folder=None
    try:
        verify_sources()
        receipt=ROOT/PROTOCOL.get('reference_result_path','outputs/dfthcsos-calibration/result.json')
        if (digest(program_path)==PROTOCOL.get('reference_program_sha256') and receipt.exists()
                and digest(receipt)==PROTOCOL.get('reference_result_sha256')):
            result=json.loads(receipt.read_text());score_result(result);result['cached_baseline']=True
            return result
        folder=ROOT/'outputs/dfthcsos'/f'evaluation-{uuid.uuid4().hex}'
        return evaluate_program(program_path,folder)
    except Exception as exc:
        return {'combined_score':0.0,'error':str(exc),'logs':{name:(folder/name).read_text()[-16000:] for name in ('generator.log','verifier.log') if folder is not None and (folder/name).exists()}}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--program',type=Path)
    group.add_argument('--submission',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--smoke',action='store_true')
    parser.add_argument('--salt')
    args=parser.parse_args()
    print(json.dumps(evaluate_program(args.program,args.output,args.smoke,args.salt,args.submission),indent=2))
