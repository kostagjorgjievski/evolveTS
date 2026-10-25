"""Lease ownership: live owners beat expiry, tokens protect replacements,
real second processes are refused, dead owners are reclaimed."""
import json
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.autoresearch_seeder.controller import Controller
from scripts.autoresearch_seeder.models import JobBusy
from scripts.autoresearch_seeder.testing import build_job

HOLDER = textwrap.dedent('''
    import sys, time
    sys.path.insert(0, {repo!r})
    from scripts.autoresearch_seeder.__main__ import _load_controller
    controller, _, _ = _load_controller({job_dir!r})
    controller.claim()
    print("claimed", flush=True)
    time.sleep(60)
''')


def test_second_real_process_is_refused_until_owner_dies(tmp_path):
    job = build_job(tmp_path, [])
    holder = subprocess.Popen(
        [sys.executable, '-c',
         HOLDER.format(repo=str(REPO), job_dir=str(job.job_dir))],
        stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == 'claimed'
        duplicate = Controller(job.job_dir, job.adapter, job.config,
                               dispatcher=job.dispatcher,
                               transport_factory=lambda cfg: None)
        duplicate.store = job.store
        with pytest.raises(JobBusy):
            duplicate.claim()
    finally:
        holder.terminate()
        holder.wait(timeout=10)
    # The owner is dead; a new controller reclaims the same job.
    survivor = Controller(job.job_dir, job.adapter, job.config,
                          dispatcher=job.dispatcher,
                          transport_factory=lambda cfg: None)
    survivor.store = job.store
    lease = survivor.claim()
    assert lease['token']
    events = [event['kind'] for event in job.store.list_events()]
    assert 'lease_reclaimed' in events
    survivor.release()


def test_expired_lease_still_blocks_while_owner_is_alive(tmp_path):
    """Expiry must not override a live owner (the TTL bug)."""
    job = build_job(tmp_path, [])
    job.claim()
    # The lease expires one hour ago, but its owner identity is THIS live
    # process with the correct command line and start time.
    lease_file = job.job_dir / 'private' / 'lease.json'
    lease = json.loads(lease_file.read_text())
    lease['expires_utc'] = '2000-01-01T00:00:00+00:00'
    lease_file.write_text(json.dumps(lease))
    duplicate = Controller(job.job_dir, job.adapter, job.config,
                           dispatcher=job.dispatcher,
                           transport_factory=lambda cfg: None)
    duplicate.store = job.store
    with pytest.raises(JobBusy):
        duplicate.claim()
    job.release()


def test_renewal_extends_and_stale_owner_cannot_release_or_renew(tmp_path):
    job = build_job(tmp_path, [])
    job.claim()
    # A replacement owner took over after our process "died": the lease now
    # carries a different token.
    lease_file = job.job_dir / 'private' / 'lease.json'
    replacement = json.loads(lease_file.read_text())
    replacement['token'] = 'replacement-token'
    replacement['owner'] = {**replacement['owner'], 'pid': 999999}
    lease_file.write_text(json.dumps(replacement))
    # The stale original controller must not touch the replacement's lease.
    job.release()
    job.renew()
    after = json.loads(lease_file.read_text())
    assert after['token'] == 'replacement-token'
    assert not after.get('released')
    events = [event['kind'] for event in job.store.list_events()]
    assert 'lease_release_refused' in events
    assert 'lease_renew_refused' in events
    # The replacement (correct token) can still release cleanly.
    job._lease_token = 'replacement-token'
    job.release()
    assert json.loads(lease_file.read_text())['released'] is True


def test_renewal_extends_expiry_for_long_jobs(tmp_path):
    job = build_job(tmp_path, [])
    job.claim(ttl_seconds=1)
    before = json.loads((job.job_dir / 'private' / 'lease.json').read_text())
    time.sleep(0.01)
    assert job.renew(ttl_seconds=3600) is True
    after = json.loads((job.job_dir / 'private' / 'lease.json').read_text())
    assert after['token'] == job._lease_token
    assert after['expires_utc'] > before['expires_utc']
    job.release()


def test_pid_reuse_is_detected_by_identity(tmp_path):
    from scripts.autoresearch_seeder.controller import _process_alive
    import platform
    # A dead PID whose identity fields belong to another process.
    dead = subprocess.Popen(['true'])
    dead.wait()
    assert _process_alive({'hostname': platform.node(), 'pid': dead.pid}) is False
    # Our own PID with a mismatched process start time models PID reuse.
    assert _process_alive({'hostname': platform.node(), 'pid': __import__('os').getpid(),
                           'process_start': 'Thu Jan  1 00:00:00 1970'}) is False
