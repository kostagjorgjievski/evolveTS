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


def test_time_bounded_research_has_no_lifetime_call_ceiling(tmp_path):
    import pytest
    from scripts.autoresearch_seeder.models import BudgetExhausted
    job=build_job(tmp_path,[],overrides={'research':{'time_bounded_calls':True},
        'budgets':{'max_tool_calls':None,'max_web_searches':None}})
    job.store.charge('tool',tool_calls=600)
    job._check_budgets()
    assert job.remaining_tool_calls() is None
    state=job.job_state();state['consumed']['model_seconds']=60
    job.save_job(**state)
    with pytest.raises(BudgetExhausted,match='Model-session'):job._check_budgets()


def test_normal_turn_cap_exit_is_checkpoint_but_failed_provider_is_not(tmp_path,monkeypatch):
    import sys
    import pytest
    from scripts.autoresearch_seeder.backends import HermesBackend
    for failed in [False,True]:
        folder=tmp_path/str(failed);folder.mkdir();(folder/'worker').mkdir()
        binary=folder/'hermes'
        binary.write_text('#!'+sys.executable+'\n'+
            'import json,sys\nfrom pathlib import Path\n'+
            'assert sys.argv[sys.argv.index("--max-turns")+1]=="0"\n'+
            'Path(sys.argv[sys.argv.index("--usage-file")+1]).write_text(json.dumps('+repr({'failed':failed,'turn_exit_reason':'max_iterations_reached(15/15)'})+'))\n'+
            'print(json.dumps({"type":"system","model":"fixture"}))\nraise SystemExit(1)\n')
        binary.chmod(0o755)
        backend=HermesBackend({'name':'fixture','credential_file':'unused'},folder)
        monkeypatch.setattr(backend,'preflight',lambda:[])
        monkeypatch.setattr(backend,'resolve_binary',lambda b=binary:str(b))
        if failed:
            with pytest.raises(RuntimeError):backend.run('probe',{},folder,{'session_seconds':5,'remaining_turns':15})
        else:
            result=backend.run('probe',{},folder,{'session_seconds':5,'remaining_turns':None})
            assert result.finished_reason=='done' and result.usage['interrupted']
            assert result.usage['checkpoint_reason']=='max_iterations_reached(15/15)'
