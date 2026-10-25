"""Bounded scheduler tests: eligibility from durable state only, no model
calls on idle, lease-guarded starts, no repeats of finished work.

All tests are offline: fixture task, scripted fake transport, fake search
and fetch injected through the scheduler's test seams.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.autoresearch_seeder.models import JobBusy
from scripts.autoresearch_seeder.scheduler import (eligible_jobs,
                                                   job_eligibility, run_once,
                                                   schedule)
from scripts.autoresearch_seeder.testing import (E2E_SCRIPT, FakeSearch,
                                                 build_job, fake_fetcher)
from scripts.autoresearch_seeder.transport import FakeTransport


def write_stage(job_dir, **fields):
    job = json.loads((job_dir / 'job.json').read_text())
    job.update(fields)
    (job_dir / 'job.json').write_text(json.dumps(job, indent=2))


def test_eligibility_comes_from_durable_state_only(tmp_path):
    root = tmp_path / 'runs'
    base = root / 'autoresearch-seeder' / 'seed_demo'

    def job_with(name, **fields):
        job_dir = base / name
        job_dir.mkdir(parents=True)
        job = {'stage': 'queued', 'enabled': True}
        job.update(fields)
        (job_dir / 'job.json').write_text(json.dumps(job))
        return job_dir

    assert job_eligibility(job_with('queued'))['eligible'] is True
    assert job_eligibility(job_with('active', stage='researching'))['eligible'] is False
    for terminal in ('seed_ready', 'completed_no_improvement', 'rejected',
                     'cancelled', 'budget_exhausted', 'infrastructure_blocked',
                     'needs_access'):
        result = job_eligibility(job_with(f'term-{terminal}', stage=terminal))
        assert result['eligible'] is False and 'terminal' in result['reason']
    assert job_eligibility(job_with('disabled', enabled=False))['eligible'] is False
    retrying = job_eligibility(job_with(
        'retry-future', stage='retry_wait',
        retry={'eligible_utc': '2999-01-01T00:00:00+00:00'}))
    assert retrying['eligible'] is False
    ready = job_eligibility(job_with(
        'retry-past', stage='retry_wait',
        retry={'eligible_utc': '2000-01-01T00:00:00+00:00'}))
    assert ready['eligible'] is True
    broken = root / 'autoresearch-seeder' / 'seed_demo' / 'broken'
    broken.mkdir(parents=True)
    (broken / 'job.json').write_text('{not json')
    assert job_eligibility(broken)['eligible'] is False


def test_idle_run_once_makes_no_model_calls(tmp_path):
    root = tmp_path / 'runs'
    root.mkdir()

    def forbidden_factory(_config):
        raise AssertionError('idle check must not construct a transport')

    outcome = run_once(root, transport_factory=forbidden_factory)
    assert outcome['started'] is None and outcome['eligible'] == 0
    assert 'no model calls' in outcome['reason']


def scheduler_seams(controller):
    """Offline search/fetch/transport seams for a scheduler-driven start."""
    return dict(transport_factory=lambda cfg: controller.shared_transport,
                search_service=FakeSearch(),
                fetcher=fake_fetcher(controller.job_dir, controller.config))


def test_run_once_starts_eligible_job_to_completion(tmp_path):
    controller = build_job(tmp_path, E2E_SCRIPT)
    run_root = controller.job_dir.parents[2]
    outcome = run_once(run_root, **scheduler_seams(controller))
    assert outcome['started'] == str(controller.job_dir)
    assert outcome['stage'] in ('seed_ready', 'completed_no_improvement')


def test_scheduler_skips_job_with_live_owner_then_starts_after_release(tmp_path):
    controller = build_job(tmp_path, E2E_SCRIPT)
    run_root = controller.job_dir.parents[2]
    transport = controller.shared_transport
    controller.claim()   # a live owner now holds the lease

    outcome = run_once(run_root, transport_factory=lambda cfg: transport)
    assert outcome['started'] is None
    assert outcome.get('skipped_busy') == str(controller.job_dir)

    controller.release()
    outcome = run_once(run_root, **scheduler_seams(controller))
    assert outcome['started'] == str(controller.job_dir)


def test_finished_jobs_are_never_rescheduled(tmp_path):
    controller = build_job(tmp_path, E2E_SCRIPT)
    run_root = controller.job_dir.parents[2]
    controller.transport_factory = lambda cfg: controller.shared_transport
    final = controller.run()
    assert final['stage'] == 'seed_ready'
    assert eligible_jobs(run_root) == []


def test_config_disabled_at_start_time_blocks_scheduler(tmp_path):
    controller = build_job(tmp_path, E2E_SCRIPT)
    run_root = controller.job_dir.parents[2]
    config_path = Path(json.loads((controller.job_dir / 'job.json')
                                  .read_text())['config_path'])
    config = json.loads(config_path.read_text())
    config['enabled'] = False
    config_path.write_text(json.dumps(config, indent=2))
    # Job record still says enabled (recorded at init); live config must win.
    outcome = run_once(run_root, transport_factory=lambda cfg: controller.shared_transport)
    assert outcome['started'] is None
    assert outcome.get('skipped_disabled') == str(controller.job_dir)


def test_schedule_is_bounded_and_stops_when_idle(tmp_path):
    root = tmp_path / 'runs'
    root.mkdir()
    outcomes = schedule(root, loop_passes=5, sleep_seconds=0.0)
    assert len(outcomes) == 1 and outcomes[0]['started'] is None


def test_schedule_run_root_default_layout(tmp_path):
    controller = build_job(tmp_path, E2E_SCRIPT)
    run_root = controller.job_dir.parents[2]
    found = [entry['job'] for entry in eligible_jobs(run_root)]
    assert str(controller.job_dir) in found
