"""Trusted, attempt-bound candidate validation and development-cost accounting."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import uuid
from runtime_queue import diagnostic_slot

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tasks/dqi'))
import evaluator as dqi


def snapshot_program(attempt, target, filename="program.py"):
    if filename not in ("program.py","diagnostic.py"):raise ValueError("Unsupported source filename")
    """Walk using directory FDs: reject symlinks, hardlinks, non-files and races."""
    attempt = Path(os.path.abspath(attempt))
    if not re.fullmatch(r'attempt_\d+',attempt.name) or not re.fullmatch(r'explore_b\d+',attempt.parent.name):
        raise ValueError('Validation must be bound to one exploration attempt')
    directory = os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for component in attempt.parts[1:] + ('artifact',):
            child = os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
            os.close(directory);directory=child
        source = os.open(filename,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        try:
            before=os.fstat(source)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > 2*2**20:
                raise ValueError('program.py must be a regular, unlinked source file at most 2 MiB')
            chunks=[];size=0
            while data:=os.read(source,65536):
                size+=len(data)
                if size>2*2**20:raise ValueError('program.py exceeds 2 MiB')
                chunks.append(data)
            after=os.fstat(source)
            if (before.st_size,before.st_mtime_ns,before.st_ctime_ns) != (after.st_size,after.st_mtime_ns,after.st_ctime_ns):
                raise ValueError('program.py changed during the snapshot; retry after saving')
            payload=b''.join(chunks)
        finally:os.close(source)
    finally:os.close(directory)
    Path(target).write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def record(event):
    directory=ROOT/'runs/dqi-accounting/development-validation'
    directory.mkdir(parents=True,exist_ok=True)
    with (directory/'ledger.jsonl').open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        handle.write(json.dumps(event,ensure_ascii=False)+'\n');handle.flush()
        summary=directory/'summary.json'
        totals=json.loads(summary.read_text()) if summary.exists() else {
            'tool_calls_started':0,'tool_calls_completed':0,'passed':0,'failed':0,
            'verified_shots':0,'full_verifier_runs':0,'total_wall_seconds_including_queue':0.0}
        if event['event']=='started':totals['tool_calls_started']+=1
        else:
            totals['tool_calls_completed']+=1
            totals['passed' if event.get('status')=='PASS' else 'failed']+=1
            totals['verified_shots']+=event.get('verified_shots',0)
            totals['full_verifier_runs']=totals.get('full_verifier_runs',0)+int(event.get('purpose')=='agent_validation_tool' and event.get('stage') in ('verification','complete'))
            totals['total_wall_seconds_including_queue']+=event.get('seconds',0)
        temporary=summary.with_suffix('.tmp')
        temporary.write_text(json.dumps(totals,indent=2)+'\n');temporary.replace(summary)


def validate(attempt, diagnostic=False):
    call=uuid.uuid4().hex
    folder=ROOT/'outputs/dqi-validation'/call;folder.mkdir(parents=True)
    started=time.monotonic()
    base={'call_id':call,'attempt':str(attempt),'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'development_cost':True,'purpose':'agent_diagnostic_tool' if diagnostic else 'agent_validation_tool'}
    record(dict(base,event='started'))
    result={}
    source_hash=None
    stage='snapshot'
    try:
        source=folder/'program.py'
        source_hash=snapshot_program(attempt,source,"diagnostic.py" if diagnostic else "program.py")
        stage='preparation'
        result=diagnose(source,folder/'validation') if diagnostic else dqi.evaluate_program(source,folder/'validation',preflight=True,isolate_verifier=True)
        result.update(status='PASS',source_sha256=source_hash,stage='complete')
    except Exception as error:
        phase=folder/'validation/phase.json'
        stage=json.loads(phase.read_text())['stage'] if phase.exists() else stage
        result={'status':'FAIL','stage':stage,'error':str(error)[-6000:],'combined_score':0.0,
                'source_sha256':source_hash}
    finally:
        # Source and full metrics remain; disposable ~0.9 GB binaries do not accumulate.
        (folder/'validation/dqi.kmb').unlink(missing_ok=True)
        result['diagnostic_only']=diagnostic
        result['logs']={name: bounded_log(folder/'validation'/name) for name in ('preflight.log','generator.log','diagnostic.log') if (folder/'validation'/name).exists()}
        result.update(seconds=time.monotonic()-started,call_id=call,
                      development_cost=True,automatic_final_evaluation_still_required=True)
        (folder/'tool-result.json').write_text(json.dumps(result,indent=2)+'\n')
        record(dict(base,event='completed',status=result.get('status'),stage=result.get('stage'),
                    seconds=result['seconds'],verified_shots=result.get('official',{}).get('verified_shots',0),
                    combined_score=result.get('combined_score'),source_sha256=result.get('source_sha256')))
    return result


def bounded_log(path):
    text=path.read_text(errors='replace')
    return {'text':text[-16000:],'truncated':len(text)>16000}


def diagnose(source,output,timeout=60,memory_gib=2,persist_directory=None,workspace=None,allow_network=False,extra_env=None):
    """Run saved Python tests without automatic circuit verification."""
    import shutil
    import tempfile
    dqi.verify_sources()
    output.mkdir()
    locks=ROOT/'work/runtime-locks';locks.mkdir(parents=True,exist_ok=True)
    with diagnostic_slot(ROOT, timeout, memory_gib):
        with tempfile.TemporaryDirectory(prefix='dqi-diagnostic-') as temp:
            job=Path(temp);generated=job/'output';generated.mkdir()
            shutil.copyfile(source,job/'diagnostic.py')
            shutil.copytree(dqi.OFFICIAL/'verifiers/dqi',job/'dqi')
            shutil.copyfile(dqi.HERE/'run_candidate.py',job/'run_candidate.py')
            profile=job/'diagnostic.sb';policy=dqi.candidate_profile(job,generated)
            if allow_network:policy=policy.replace('(deny network*)\n','')
            if workspace is not None:policy+='\n(allow file-read* file-write* (subpath '+json.dumps(str(Path(workspace).resolve()))+'))\n'
            profile.write_text(policy)
            env={'PATH':'/usr/bin:/bin','HOME':str(generated),'TMPDIR':str(generated),'TEST_OUTPUT_DIR':str(generated),
                 'PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
            env.update(extra_env or {})
            if workspace is not None:env['BRANCH_WORKSPACE']=str(Path(workspace).resolve())
            (output/'phase.json').write_text(json.dumps({'stage':'diagnostic'}))
            log=dqi.run_process(['/usr/bin/sandbox-exec','-f',str(profile),str(dqi.PYTHON),'-I',
                str(job/'run_candidate.py'),str(job/'diagnostic.py')],job,env,timeout,memory_gib=memory_gib,
                **({'scratch_directory':[generated]+([workspace] if workspace is not None else [])} if persist_directory is not None else {}))
            (output/'diagnostic.log').write_text(log)
            exported=[]
            if persist_directory is not None:
                destination=Path(persist_directory);destination.mkdir(parents=True,exist_ok=False);total=0
                for path in sorted(generated.rglob('*')):
                    if path.is_symlink() or not path.is_file() or path.stat().st_nlink!=1:continue
                    if path.suffix not in ('.json','.txt','.csv','.log','.md','.py','.npy','.npz'):continue
                    if path.stat().st_size>4*2**20 or total+path.stat().st_size>16*2**20:continue
                    relative=path.relative_to(generated);target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target);total+=target.stat().st_size
                    exported.append({'file':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    return {'diagnostic_only':True,'verified_score':None,'test_timeout_seconds':timeout,'test_memory_gib':memory_gib,'test_outputs':exported,'network_enabled':allow_network,'branch_workspace':str(workspace) if workspace is not None else None}
