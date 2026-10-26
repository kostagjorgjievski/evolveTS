import json
from scripts.autoresearch_seeder.transport import provider_error_detail,classify_provider_error
from scripts.autoresearch_seeder.models import ProviderRateLimit
from scripts.autoresearch_seeder.testing import build_job


def test_structured_http503_wins_over_session_only_stderr():
    stdout=json.dumps({'type':'result','exit_code':1,'error':'HTTP 503: Service temporarily unavailable'})
    detail=provider_error_detail(stdout,'Session: opaque-id')
    assert 'HTTP 503' in detail
    assert isinstance(classify_provider_error(detail),ProviderRateLimit)


def test_service_retry_is_saved_without_sleep_or_extra_paid_window(tmp_path):
    job=build_job(tmp_path,[{'error':'rate_limit','detail':'HTTP 503: Service temporarily unavailable'}],
                  overrides={'research':{'defer_provider_retries':True},'budgets':{'retry_wait_seconds':300}})
    job._sleep_bounded=lambda _:(_ for _ in ()).throw(AssertionError('must defer wait'))
    result=job.run(max_sessions=1)
    assert result['stage']=='retry_wait'
    assert result['retry']['attempt']==1 and result['retry']['resume_stage']=='researching'
