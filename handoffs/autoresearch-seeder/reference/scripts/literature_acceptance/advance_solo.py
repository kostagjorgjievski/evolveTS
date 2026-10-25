"""Advance a standalone pilot after its current attempt, keeping its conversation."""
import argparse
import datetime
import json
from pathlib import Path
import shutil
import subprocess
import time

import psutil
import solo_pilot

ROOT = solo_pilot.ROOT


def save(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def advance(run):
    queue = run / 'private/queued-next-attempt.json'
    requested = json.loads(queue.read_text())
    expected_pid = requested['previous_pid']
    expected_created = requested.get('previous_process_created')
    while True:
        try:
            process = psutil.Process(expected_pid)
            if expected_created is None or process.create_time() != expected_created or process.status() == psutil.STATUS_ZOMBIE:
                break
            time.sleep(3)
        except psutil.NoSuchProcess:
            break
    meta = json.loads((run / 'pilot.json').read_text())
    if meta.get('status') == 'stopped_by_user':
        requested.update(status='cancelled', reason='Previous pilot was stopped by user')
        save(queue, requested)
        return
    previous_index = meta.get('continuation_attempt_index', 0)
    if previous_index != requested['previous_attempt_index']:
        raise RuntimeError('Attempt advanced elsewhere; refusing duplicate continuation')
    branch = run / 'worker/explore_b0'
    previous = branch / f'attempt_{previous_index:02d}'
    following = branch / f'attempt_{previous_index+1:02d}'
    archive = run / f'private/completed-attempts/{previous_index:02d}'
    shutil.copytree(previous, archive)
    receipts = {}
    for name in ('final-development.json', 'held-out.json', 'gate.json', 'status.json'):
        path = run / 'private' / name
        if path.exists():
            shutil.copyfile(path, archive / name)
            if name in ('final-development.json', 'held-out.json'):
                data = json.loads(path.read_text())
                receipts[name] = {k: data.get(k) for k in ('status', 'combined_score', 'call_id', 'source_sha256')}
    if not (run / 'private/sdk/sdk-session.json').exists():
        raise RuntimeError('Saved parent conversation required')
    shutil.copyfile(run / 'private/sdk/sdk-session.json', archive / 'sdk-session.json')
    shutil.copytree(previous / 'artifact', following / 'artifact')
    if (previous / 'proposal.md').exists():
        shutil.copyfile(previous / 'proposal.md', following / 'proposal.md')
    prior_seconds = meta.get('session_seconds_used', 0)
    meta.update(continuation_attempt_index=previous_index+1, attempts=max(meta.get('attempts', 1), previous_index+2),
                previous_scored_receipts=receipts, fresh_attempt_allowance=True,
                session_seconds_used=0, max_session_seconds=12000,
                budget_scope='per_attempt', prior_attempt_seconds=prior_seconds,
                next_attempt_authorized_utc=requested['requested_utc'])
    save(run / 'pilot.json', meta)
    requested.update(status='starting', next_attempt_index=previous_index+1)
    save(queue, requested)
    command = [str(ROOT / '.venv/bin/python'), str(Path(__file__).with_name('solo_pilot.py')), 'resume', str(run)]
    process = subprocess.Popen(command, cwd=ROOT)
    requested.update(status='started', next_pid=process.pid)
    save(queue, requested)
    pointer = ROOT / 'runs/dqi-solo/active.json'
    if pointer.exists():
        data = json.loads(pointer.read_text())
        if data.get('run') == str(run):
            data.update(pid=process.pid, attempt=previous_index+1)
            save(pointer, data)
    process.wait()
    requested['status'] = 'finished'
    requested['exit_code'] = process.returncode
    save(queue, requested)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    try:
        advance(args.run.resolve())
    except BaseException as exc:
        queue = args.run.resolve() / 'private/queued-next-attempt.json'
        data = json.loads(queue.read_text())
        data.update(status='error', error=str(exc))
        save(queue, data)
        raise
