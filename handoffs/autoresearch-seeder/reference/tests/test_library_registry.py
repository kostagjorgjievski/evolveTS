import importlib.util,json
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('task_registry',ROOT/'scripts/library_rsi/registry.py')
registry=importlib.util.module_from_spec(spec);spec.loader.exec_module(registry)

def test_real_dqi_contract_points_to_task_owned_code():
    t=registry.load('dqi')
    assert t['paths']['receipt_adapter']==ROOT/'tasks/dqi/library_receipts.py'
    assert t['library_directory']==ROOT/'library/dqi'
    assert len(t['protocol_sha256'])==64

def test_rejects_task_traversal():
    for task in ('../dqi','dqi/../../credentials','/dqi',''):
        with pytest.raises(ValueError):registry.load(task)

def test_manifest_rejects_cross_task_paths(tmp_path):
    folder=tmp_path/'tasks/new_task';folder.mkdir(parents=True)
    (folder/'library.json').write_text(json.dumps({'schema_version':1,'task_id':'new_task','description':'tasks/other/task.txt'}))
    with pytest.raises(ValueError,match='inside'):registry.load('new_task',root=tmp_path)

def test_unknown_task_cannot_claim_dqi_verification():
    with pytest.raises(ValueError,match='No registered receipt'):
        registry.validate_receipt('not_registered',{'official':{'status':'PASS','verified_shots':102400}},'development_verified')
