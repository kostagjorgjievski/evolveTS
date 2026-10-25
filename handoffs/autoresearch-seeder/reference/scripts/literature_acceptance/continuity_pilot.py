"""Three scored DQI attempts in one persistent, isolated MiniMax conversation."""
import argparse
import asyncio
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import effort_proxy
import run_worker as runner
import solo_pilot

ROOT = solo_pilot.ROOT


def save(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2))
    temporary.replace(path)


def session_id(run):
    path = run / 'private/sdk/sdk-session.json'
    return json.loads(path.read_text())['session_id'] if path.exists() else None


def continuation_prompt(index, previous):
    receipt = json.dumps(previous, indent=2) if previous else 'No earlier scored attempt.'
    return f'''This is attempt {index + 1} of 3 in a persistent-conversation DQI branch pilot.
Your current writable attempt is attempt_{index:02d}. All prior conversation and
research belong to this same branch. Do not restart task discovery unnecessarily.
{solo_pilot.PROMPT.replace('attempt_00', f'attempt_{index:02d}').replace('You have up to 200 minutes and 1000 turns.', 'The whole three-attempt branch shares a 200-minute working allowance. There is no short per-attempt time target.')}
Choose a meaningful executable milestone for each attempt; do not stop merely
because a fixed number of minutes passed. Save your best runnable candidate;
keep partial improvements/helpers too. Write proposal.md with current approach,
source/code locations, verified measurements, failed tests, unresolved blockers,
and your next experiment. Return after saving so the controller can score it and
resume THIS conversation for the next attempt. A checkpoint is not the end of the
branch. Do not claim an improvement without official validation.
Previous attempt's controller receipt:
{receipt}
'''


def work(run, smoke=False, seeded=False):
    meta = json.loads((run / 'pilot.json').read_text())
    config = runner.environment(ROOT / '.credentials/minimax.env')
    proxy, url = effort_proxy.start(config['ANTHROPIC_AUTH_TOKEN'], run / 'private/provider-requests.jsonl', provider='minimax', upstream=config['ANTHROPIC_BASE_URL'])
    meta.update(status='running', pid=os.getpid(), started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    save(run / 'pilot.json', meta)
    records = []
    previous = None
    coding_used = 0.0
    try:
        seed_session = None
        if seeded:
            branch = run / 'worker/explore_b0'
            preparation = branch / 'attempt_99'
            (preparation / 'artifact').mkdir(parents=True)
            seed_prompt = """Prepare a reusable DQI task/API orientation checkpoint for independent future workers.
Read task.txt, protocol.json, reference_program.py and verify_submission_dqi.py.
Learn the objective, verifier contract, input/output conventions and kickmix APIs.
Use small executable diagnostics to verify array shapes, register operations,
controlled operations, simulation and candidate import conventions as useful.
You can use diagnose_candidate (60s/2GiB) and integration_test (600s/10GiB),
both run attempt_99/artifact/diagnostic.py with no arguments. Own Python helpers
are importable. Integration has network and own-branch write access; keep this
preparation focused on the supplied task/reference/API, not optimization research.
Do NOT search literature, select an optimization method, or propose a better
algorithm. Do not inspect any other run or branch. Do not generate a full circuit
merely for orientation. Write attempt_99/proposal.md as a concise tested API guide,
with exact examples, actual diagnostic results, pitfalls and uncertainties. Save
useful tested examples/helpers in attempt_99/artifact/. Do not create a claimed
optimized program.py. Stop after you have a useful preparation checkpoint.
Only Read/Grep/Glob inside this branch and Write/Edit inside attempt_99/artifact/**
or attempt_99/proposal.md. This is shared preparation, not an optimization attempt.
"""
            if smoke:
                seed_prompt = 'No tools. Remember the marker copper-orchid-714 for future cloned sessions. Reply with that marker and stop.'
            def prepare_seed(directory):
                return branch, preparation, seed_prompt
            started = time.monotonic()
            asyncio.run(runner.agent(run, prepare_fn=prepare_seed, server_script=Path(__file__).with_name('solo_server.py'), tool_names=('diagnose_candidate', 'integration_test'), base_url=url, max_session_seconds=180 if smoke else 12000, provider_override='minimax', config_override=config, lease_glm=False))
            coding_used = time.monotonic() - started
            seed_session = session_id(run)
            if not seed_session:
                raise RuntimeError('Preparation checkpoint has no saved conversation')
            archive = run / 'private/preparation'
            shutil.copytree(preparation, archive / 'files')
            shutil.copyfile(run / 'private/sdk/sdk-session.json', archive / 'sdk-session.json')
            shutil.copyfile(run / 'private/status.json', archive / 'status.json')
            auth = ROOT / '.credentials' / ('acceptance-' + run.name) / 'cli'
            transcript = list(auth.rglob(seed_session + '.jsonl'))
            if len(transcript) != 1:
                raise RuntimeError('Expected exactly one saved preparation transcript')
            shutil.copyfile(transcript[0], archive / 'conversation.jsonl')
            save(archive / 'receipt.json', {'session_id': seed_session, 'preparation_seconds': coding_used, 'transcript_sha256': hashlib.sha256(transcript[0].read_bytes()).hexdigest()})
            shutil.copytree(preparation / 'artifact', branch / 'attempt_00/artifact', dirs_exist_ok=True)
            if (preparation / 'proposal.md').exists():
                shutil.copyfile(preparation / 'proposal.md', branch / 'preparation-guide.md')
            meta['preparation_seconds'] = coding_used
            meta['preparation_session_id'] = seed_session
            save(run / 'pilot.json', meta)
            print(json.dumps({'preparation_seconds': coding_used, 'status': 'preparation_complete'}), flush=True)
        for index in range(2 if smoke else 3):
            branch = run / 'worker/explore_b0'
            attempt = branch / f'attempt_{index:02d}'
            if index:
                shutil.copytree(branch / f'attempt_{index-1:02d}/artifact', attempt / 'artifact')
            before = session_id(run)
            if not smoke and coding_used >= 12000:
                raise RuntimeError('Shared 200-minute branch allowance exhausted')
            prompt = continuation_prompt(index, previous) + f'\nRemaining branch working allowance: {(12000-coding_used)/60:.1f} minutes.\n'
            if seeded:
                prompt += '\nYou inherit a tested preparation session. Its files are at attempt_99/ and preparation-guide.md if present. Use this knowledge; independently choose your optimization approach now.\n'
            if smoke:
                prompt = ('Conversation-continuity smoke test. No tools needed. Remember the marker copper-orchid-714. Reply with that marker and stop.' if index == 0 and not seeded else 'Without reading any files or using tools, recall the marker I gave you in the previous conversation turn. Reply with it and stop.')
            def prepare(directory):
                return branch, attempt, prompt
            started = time.monotonic()
            asyncio.run(runner.agent(run, prepare_fn=prepare, server_script=Path(__file__).with_name('solo_server.py'), tool_names=solo_pilot.TOOLS, base_url=url, max_session_seconds=180 if smoke else max(1, 12000 - coding_used), provider_override='minimax', config_override=config, lease_glm=False, fork_session=bool(seeded and index == 0)))
            coding_seconds = time.monotonic() - started
            coding_used += coding_seconds
            after = session_id(run)
            if seeded and index == 0:
                if not after or after == seed_session:
                    raise RuntimeError('Child must fork preparation into a distinct conversation')
            elif not after or (before and before != after):
                raise RuntimeError('Conversation continuity failed; refusing a silent fresh session')
            if seeded and hashlib.sha256(transcript[0].read_bytes()).hexdigest() != json.loads((run / 'private/preparation/receipt.json').read_text())['transcript_sha256']:
                raise RuntimeError('Child modified the preparation conversation')
            archive = run / f'private/attempts/{index:02d}'
            archive.mkdir(parents=True)
            for name in ['status.json', 'sdk/sdk-session.json']:
                shutil.copyfile(run / 'private' / name, archive / Path(name).name)
            # Freeze an authoritative copy outside all candidate/agent file permissions.
            shutil.copytree(attempt / 'artifact', archive / 'artifact')
            if (attempt / 'proposal.md').exists():
                shutil.copyfile(attempt / 'proposal.md', archive / 'proposal.md')
            manifest = {str(p.relative_to(archive / 'artifact')): hashlib.sha256(p.read_bytes()).hexdigest() for p in (archive / 'artifact').rglob('*') if p.is_file()}
            record = {'attempt': index, 'coding_seconds': coding_seconds, 'session_id': after, 'resumed': bool(before), 'artifact_sha256': manifest}
            if not smoke:
                started = time.monotonic()
                if (attempt / 'artifact/program.py').exists():
                    env = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'TMPDIR': str(ROOT / 'outputs/dqi-validation/tmp'), 'PYTHONDONTWRITEBYTECODE': '1'}
                    result = subprocess.run([str(ROOT / '.venv/bin/python'), str(Path(__file__).with_name('solo_worker.py')), str(attempt)], cwd=ROOT, capture_output=True, text=True, env=env)
                    receipt = json.loads(result.stdout) if result.returncode == 0 else {'status': 'ERROR', 'error': result.stderr[-3000:]}
                else:
                    receipt = {'status': 'NO_PROPOSAL', 'error': 'No program.py saved; partial drafts preserved'}
                record['validation_seconds'] = time.monotonic() - started
                record['validation'] = receipt
            else:
                record['answer'] = json.loads((run / 'private/status.json').read_text()).get('result', {}).get('result')
                if 'copper-orchid-714' not in (record['answer'] or ''):
                    raise RuntimeError('Continuation did not recall the marker')
            save(archive / 'receipt.json', record)
            records.append(record)
            previous = {'attempt': index, 'coding_seconds': coding_seconds, 'validation': record.get('validation'), 'checkpoint': f'attempt_{index:02d}/proposal.md'}
            save(run / 'private/progress.json', {'status': 'between_attempts', 'records': records})
            print(json.dumps({'attempt': index, 'coding_seconds': coding_seconds, 'validation_seconds': record.get('validation_seconds'), 'resumed': bool(before), 'score': record.get('validation', {}).get('combined_score'), 'status': record.get('validation', {}).get('status')}), flush=True)
        meta['status'] = 'completed'
    except BaseException as error:
        meta.update(status='error', error=str(error).replace(config['ANTHROPIC_AUTH_TOKEN'], '[REDACTED]'))
        raise
    finally:
        proxy.shutdown()
        proxy.server_close()
        save(run / 'pilot.json', meta)
        save(run / 'private/progress.json', {'status': meta['status'], 'records': records})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['prepare', 'run', 'smoke'])
    parser.add_argument('directory', type=Path)
    parser.add_argument('--seeded', action='store_true')
    args = parser.parse_args()
    run = args.directory.resolve()
    if args.command == 'prepare':
        solo_pilot.initialize(run, provider='minimax')
        meta = json.loads((run / 'pilot.json').read_text())
        meta.update(experiment='persistent_branch_conversation', attempts=3, max_session_seconds=12000, per_attempt_target_seconds=None, harness_revision='integration_v2')
        meta['seeded_preparation'] = args.seeded
        save(run / 'pilot.json', meta)
    else:
        work(run, smoke=args.command == 'smoke', seeded=args.seeded)
