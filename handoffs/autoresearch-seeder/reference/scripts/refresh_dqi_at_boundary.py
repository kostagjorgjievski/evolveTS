"""Refresh the DQI controller after the active first-wave agents finish."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

import psutil

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT/'runs/dqi/active-e0.json'


def main():
    run = json.loads(ACTIVE.read_text())
    workspace = Path(run['workspace'])
    original_pid = run['pid']
    print('[web-refresh] Waiting for the 10 first-wave attempts to finish.', flush=True)
    while True:
        current = json.loads(ACTIVE.read_text())
        if current['pid'] != original_pid:
            print('[web-refresh] Another controller replaced this run; no action.', flush=True)
            return
        if (workspace/'live_cycle_manifest.json').exists():
            print('[web-refresh] E0 already finished; future launches have web access.', flush=True)
            return
        states=[]
        for branch in range(10):
            path=workspace/f'explore_b{branch}/attempt_00/meta.json'
            try:states.append(json.loads(path.read_text()).get('status'))
            except (OSError,ValueError):states.append(None)
        if all(state in ('done','failed') for state in states):
            break
        if not psutil.pid_exists(original_pid):
            raise RuntimeError('Controller exited before the wave finished; refusing an automatic relaunch')
        time.sleep(2)

    controller = psutil.Process(original_pid)
    if 'tasks/dqi/launch.sh' not in controller.cmdline():
        raise RuntimeError('Active PID does not match the DQI launcher')
    targets=[controller]+controller.children(recursive=True)
    groups=set()
    for process in targets:
        try:groups.add(os.getpgid(process.pid))
        except ProcessLookupError:pass
    for group in groups:
        if group != os.getpgrp():
            try:os.killpg(group,signal.SIGTERM)
            except ProcessLookupError:pass
    _, alive = psutil.wait_procs(targets, timeout=5)
    for process in alive:
        try:process.kill()
        except psutil.Error:pass

    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    logs=Path(run['log']).parent
    snapshot=logs/f'web-refresh-{stamp}'
    shutil.copytree(workspace,snapshot/'workspace',symlinks=True)
    checks={str(p.relative_to(workspace)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in workspace.glob('explore_b*/attempt_*/eval/score.json')}
    (snapshot/'preserved-scores.json').write_text(json.dumps(checks,indent=2)+'\n')
    (snapshot/'previous-launch.json').write_text(json.dumps(run,indent=2)+'\n')
    logfile=logs/f'web-enabled-{stamp}.log'
    env=os.environ.copy()
    env.update(BACKEND='glm',RESUME='1',WORKSPACE=str(workspace),PYTHONUNBUFFERED='1',
               LC_ALL='en_US.UTF-8',LANG='en_US.UTF-8')
    env.pop('DRY_RUN',None)
    with logfile.open('w') as output:
        process=subprocess.Popen(['/usr/bin/caffeinate','-i','bash','tasks/dqi/launch.sh','e0'],
                                 cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=output,
                                 stderr=subprocess.STDOUT,start_new_session=True)
    run.update(pid=process.pid,log=str(logfile),web_research_enabled=True,
               stage='E0 resumed at wave boundary with web research',
               web_refresh_utc=stamp,preserved_scored_attempts=len(checks))
    run.pop('pending_web_refresh',None)
    ACTIVE.write_text(json.dumps(run,indent=2)+'\n')
    (logs/'launch.json').write_text(json.dumps(run,indent=2)+'\n')
    print(f'[web-refresh] Resumed pid={process.pid}; preserved {len(checks)} scored attempts.',flush=True)


if __name__=='__main__':
    main()
