"""Refresh the active DQI controller, preserving scores, drafts and SDK sessions."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import uuid
import psutil

ROOT=Path(__file__).resolve().parents[1]


def main():
    active=ROOT/'runs/dqi/active-e0.json'
    run=json.loads(active.read_text());workspace=Path(run['workspace'])
    controller=psutil.Process(run['pid'])
    if 'tasks/dqi/launch.sh' not in controller.cmdline():
        raise RuntimeError('Active PID does not match the DQI launcher')
    targets=[controller]+controller.children(recursive=True)
    groups=set()
    for process in targets:
        try:groups.add(os.getpgid(process.pid))
        except ProcessLookupError:pass
    if os.getpgrp() in groups:raise RuntimeError('Refusing to stop this refresh process group')
    for group in groups:
        try:os.killpg(group,signal.SIGTERM)
        except ProcessLookupError:pass
    _,alive=psutil.wait_procs(targets,timeout=5)
    for process in alive:
        try:process.kill()
        except psutil.Error:pass
    projects=ROOT/'.credentials/claude-glm/projects'
    sessions=[]
    for branch in workspace.glob('explore_b*'):
        drafts=[n for n in branch.glob('attempt_*') if not (n/'eval/score.json').exists() and json.loads((n/'meta.json').read_text()).get('status') not in ('done','failed')]
        if not drafts:continue
        if len(drafts)!=1:raise RuntimeError('Multiple unfinished attempts in '+str(branch))
        node=drafts[0];session=node/'agent_log/claude/sdk-session.json'
        if session.exists():continue
        folders=[p for p in projects.iterdir() if workspace.name in p.name and p.name.endswith('-'+branch.name.replace('_','-'))]
        files=[p for folder in folders for p in folder.glob('*.jsonl')]
        if files:
            latest=max(files,key=lambda p:p.stat().st_mtime)
            uuid.UUID(latest.stem)
            session.parent.mkdir(parents=True,exist_ok=True)
            session.write_text(json.dumps({'session_id':latest.stem})+'\n')
            sessions.append(str(node.relative_to(workspace)))
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    logs=Path(run['log']).parent;snapshot=logs/f'validator-refresh-{stamp}'
    shutil.copytree(workspace,snapshot/'workspace',symlinks=True)
    checks={str(p.relative_to(workspace)):hashlib.sha256(p.read_bytes()).hexdigest()
            for pattern in ('explore_b*/attempt_*/eval/score.json','explore_b*/attempt_*/artifact/program.py','explore_b*/attempt_*/proposal.md')
            for p in workspace.glob(pattern) if p.is_file()}
    (snapshot/'preserved-files.json').write_text(json.dumps(checks,indent=2)+'\n')
    (snapshot/'previous-launch.json').write_text(json.dumps(run,indent=2)+'\n')
    env=os.environ.copy();env.update(BACKEND='glm',RESUME='1',WORKSPACE=str(workspace),
        PYTHONUNBUFFERED='1',LC_ALL='en_US.UTF-8',LANG='en_US.UTF-8')
    env.pop('DRY_RUN',None)
    logfile=logs/f'validator-enabled-{stamp}.log'
    with logfile.open('w') as output:
        process=subprocess.Popen(['/usr/bin/caffeinate','-i','bash','tasks/dqi/launch.sh','e0'],
            cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
    run.update(pid=process.pid,log=str(logfile),candidate_validation_enabled=True,
        stage='E0 resumed with independent branch scheduling',independent_branches=True,validator_refresh_utc=stamp,
        preserved_scored_attempts=sum(p.endswith('/score.json') for p in checks),
        preserved_draft_sessions=sessions,preservation_receipt=str(snapshot/'preserved-files.json'))
    active.write_text(json.dumps(run,indent=2)+'\n');(logs/'launch.json').write_text(json.dumps(run,indent=2)+'\n')
    print(json.dumps({'pid':process.pid,'scores_preserved':run['preserved_scored_attempts'],
        'draft_sessions_preserved':sessions,'log':str(logfile)}))


if __name__=='__main__':main()
