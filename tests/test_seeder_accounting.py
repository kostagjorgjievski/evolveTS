"""Accounting: crash-time model budget, provider-error records, and honest
model/effort metadata."""
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.autoresearch_seeder.controller import Controller
from scripts.autoresearch_seeder.testing import E2E_SCRIPT, build_job


def test_orphaned_session_is_charged_on_resume(tmp_path):
    """A crash mid-session must not silently forgive model time."""
    controller = build_job(tmp_path, E2E_SCRIPT)
    # Simulate: a session started, the process died before it ended.
    import datetime
    started = (datetime.datetime.now(datetime.timezone.utc)
               - datetime.timedelta(seconds=30)).isoformat()
    controller.store.event('session_started', {'session_started_utc': started})
    before = controller.job_state()['consumed']['model_seconds']
    resumed = Controller(controller.job_dir, controller.adapter, controller.config,
                         dispatcher=controller.dispatcher,
                         transport_factory=lambda cfg: controller.shared_transport)
    resumed.resume()
    charged = resumed.job_state()['consumed']['model_seconds'] - before
    # Upper bound ~30s elapsed (tolerance for test timing), capped by the
    # configured session budget of 60s.
    assert 25.0 <= charged <= 60.0
    events = [event['kind'] for event in resumed.store.list_events()]
    assert 'session_recovered' in events


def test_orphan_charge_is_capped_by_session_budget(tmp_path):
    controller = build_job(tmp_path, [],
                           overrides={'budgets': {'model_session_seconds': 5}})
    import datetime
    started = (datetime.datetime.now(datetime.timezone.utc)
               - datetime.timedelta(hours=2)).isoformat()
    controller.store.event('session_started', {'session_started_utc': started})
    controller._recover_orphan_session()
    totals = controller.store.totals()
    assert totals['model']['seconds'] <= 5.0


def test_completed_sessions_leave_no_orphan_charge(tmp_path):
    controller = build_job(tmp_path, E2E_SCRIPT)
    controller.run()
    before = controller.job_state()['consumed']['model_seconds']
    controller._recover_orphan_session()
    assert controller.job_state()['consumed']['model_seconds'] == before


def test_provider_errors_are_recorded_with_class(tmp_path):
    script = [{'error': 'rate_limit', 'detail': 'API Error: 429 throttled'},
              {'tool_calls': [{'name': 'finish',
                               'arguments': {'reason': 'done'}}]}]
    controller = build_job(tmp_path, script,
                           overrides={'budgets': {'max_provider_retries': 2,
                                                  'retry_wait_seconds': 0.01}})
    controller.run()
    errors = controller.store.list_events('provider_error')
    assert errors and errors[0]['class'] == 'rate_limit'
    assert '429' in errors[0]['detail']


def test_model_effort_metadata_recorded_honestly(tmp_path):
    """Requested vs served model/effort is recorded; effort honoring is never
    claimed without attestation."""
    controller = build_job(tmp_path, E2E_SCRIPT)
    controller.run()
    worker = controller.job_state()['worker']
    metadata = worker['model_metadata']
    assert metadata['requested_model'] == 'FakeModel-1'
    assert metadata['requested_effort'] == 'medium'
    assert 'fake-model' in metadata['served_models']
    assert metadata['effort_attested'] is False
    assert 'not independently attested' in metadata['note']


def test_status_reports_cost_enforcement_caveat(tmp_path):
    from scripts.autoresearch_seeder.__main__ import _status
    controller = build_job(tmp_path, [])
    status = _status(controller)
    assert 'post-hoc' in status['cost_enforcement']
    assert status['model_metadata']['requested_model'] == 'FakeModel-1'
    assert status['production_enabled'] is False


def test_orphan_recovery_is_idempotent(tmp_path):
    import datetime
    controller=build_job(tmp_path,[])
    start=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(seconds=5)).isoformat()
    controller.store.event('session_started',{'session_started_utc':start})
    controller._recover_orphan_session()
    before=controller.consumed()['model_seconds']
    controller._recover_orphan_session()
    assert controller.consumed()['model_seconds']==before
