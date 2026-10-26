"""DQI orchestration envelope; official engine behavior is injected, never edited."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.autoresearch_seeder import dqi_adapter
from scripts.autoresearch_seeder.models import ToolInfrastructureError


def fixture(tmp_path):
    runtime=tmp_path/'venv/bin/python';runtime.parent.mkdir(parents=True);runtime.touch()
    artifact=tmp_path/'attempt_00/artifact';artifact.mkdir(parents=True)
    (artifact/'program.py').write_text('original candidate')
    (artifact/'helper.py').write_text('own helper')
    calls=[]
    protocol=dict(m=4095,n=70,degree=12,r=2016,batch_size=256,log2_delta=-128.,
                  max_workers=4,num_shots=102400,verifier_timeout_seconds=28800)
    def generate(program,output,**kwargs):
        calls.append(('generate',kwargs))
        assert 'runpy.run_path' in program.read_text()
        assert (program.parent/'artifact/helper.py').read_text()=='own helper'
        output.mkdir();(output/'dqi.kmb').write_bytes(b'exact frozen circuit')
        return {'official':{'status':'PASS','verified_shots':102400},'combined_score':2.}
    def run(command,output,env,timeout):
        calls.append(('confirm',command))
        assert '--num-shots' in command and command[command.index('--num-shots')+1]=='102400'
        assert command[command.index('--salt')+1]==dqi_adapter.FINAL_SALT
        assert 'ANTHROPIC_AUTH_TOKEN' not in env
        return json.dumps({'status':'PASS','verified_shots':102400})
    ev=SimpleNamespace(PYTHON=runtime,verify_sources=lambda:None,
         candidate_profile=lambda *args:'sandbox-policy',evaluate_program=generate,
         OFFICIAL=tmp_path/'official',PROTOCOL=protocol,run_process=run,
         score_result=lambda result,smoke:{'official':result,'combined_score':2.})
    adapter=SimpleNamespace(root=tmp_path,manifest={'runtime':'venv/bin/python'},
        protocol_sha256='unchanged-protocol',_task_module=lambda _:ev,
        salt=lambda which,cfg:'development-salt' if which=='development' else dqi_adapter.FINAL_SALT,
        _classify=lambda e:{'status':'FAIL','error':str(e)})
    return adapter,artifact,calls


def test_dqi_confirmation_reuses_full_development_circuit_without_regeneration(tmp_path):
    adapter,artifact,calls=fixture(tmp_path)
    dev=dqi_adapter.validate(adapter,artifact.parent,tmp_path/'dev','development',{})
    saved=tmp_path/'dev/submission'
    final=dqi_adapter.validate(adapter,artifact.parent,tmp_path/'final','confirmation',{},saved)
    assert [c[0] for c in calls]==['generate','confirm']
    assert dev['submission_files_sha256']==final['submission_files_sha256']
    assert dev['official']['submission_sha256']==final['official']['submission_sha256']
    assert final['held_out'] and final['submission_reused']
    assert dev['salt']!=final['salt']
    assert final['protocol_sha256']=='unchanged-protocol'
    assert (saved/'dqi.kmb').read_bytes()==b'exact frozen circuit'


def test_dqi_confirmation_rejects_missing_saved_submission(tmp_path):
    adapter,artifact,calls=fixture(tmp_path)
    with pytest.raises(ToolInfrastructureError):
        dqi_adapter.validate(adapter,artifact.parent,tmp_path/'final','confirmation',{})
    assert not calls


def test_dqi_confirmation_detects_mutation_during_official_check(tmp_path):
    adapter,artifact,calls=fixture(tmp_path)
    dqi_adapter.validate(adapter,artifact.parent,tmp_path/'dev','development',{})
    ev=adapter._task_module('evaluator');original=ev.run_process
    def change(*args):
        (tmp_path/'dev/submission/dqi.kmb').write_bytes(b'changed')
        return original(*args)
    ev.run_process=change
    with pytest.raises(ToolInfrastructureError,match='changed during confirmation'):
        dqi_adapter.validate(adapter,artifact.parent,tmp_path/'final','confirmation',{},tmp_path/'dev/submission')


def test_failed_circuit_is_losslessly_archived_without_losing_receipts(tmp_path):
    import gzip,hashlib
    original=b'failed circuit fixture '*10000
    (tmp_path/'dqi.kmb').write_bytes(original)
    (tmp_path/'receipt.json').write_text('{"status":"FAIL"}')
    result=dqi_adapter.archive_failed_output(tmp_path,minimum_bytes=0)
    assert result['sha256']==hashlib.sha256(original).hexdigest()
    assert gzip.open(tmp_path/'dqi.kmb.gz','rb').read()==original
    assert not (tmp_path/'dqi.kmb').exists()
    assert (tmp_path/'receipt.json').read_text()=='{"status":"FAIL"}'
