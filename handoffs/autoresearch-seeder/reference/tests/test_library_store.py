import copy,importlib.util,json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('library_store',ROOT/'scripts/library_rsi/store.py')
store=importlib.util.module_from_spec(spec);spec.loader.exec_module(store)

@pytest.fixture
def entry():
    return {'id':'field-transport','title':'Field transport','task':'dqi','mechanism':'basis isomorphism','family':'arithmetic','sources':[{'url':'https://example.org/paper','title':'Paper','commit':None}],'advisor':{'continue_when':[],'pivot_when':[],'explore_when':[],'first_test':'Check multiplication commutes'},'evidence':[{'level':'published_claim','claim':'A claim','artifact':None}]}

def test_revisions_search_and_snapshot(tmp_path,entry):
    db=store.connect(tmp_path/'library.db')
    first=store.ingest(db,[entry],'gpt')[0]
    entry['mechanism']='linear basis transport'
    second=store.ingest(db,[entry],'opus')[0]
    assert first['revision']!=second['revision']
    assert db.execute('SELECT count(*) FROM revisions').fetchone()[0]==2
    assert store.search(db,'linear')[0]['mechanism']==entry['mechanism']
    assert not store.search(db,'linear',task='invsqrt')
    store.snapshot(db,tmp_path/'export')
    assert json.loads((tmp_path/'export/index.json').read_text())['production_enabled'] is False

def test_invalid_batch_does_not_partially_publish(tmp_path,entry):
    db=store.connect(tmp_path/'library.db');bad=copy.deepcopy(entry);bad['id']='bad';bad['advisor'].pop('first_test')
    with pytest.raises(ValueError):store.ingest(db,[entry,bad],'gpt')
    assert db.execute('SELECT count(*) FROM methods').fetchone()[0]==0

def test_verification_requires_full_receipt_and_fresh_salt(tmp_path,entry,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path);out=tmp_path/'outputs';out.mkdir();receipt=out/'receipt.json'
    entry['evidence']=[{'level':'independently_verified','claim':'Full circuit','artifact':'outputs/receipt.json'}]
    receipt.write_text(json.dumps({'official':{'status':'PASS','verified_shots':10},'held_out':True}))
    with pytest.raises(ValueError,match='full official'):store.validate(copy.deepcopy(entry))
    receipt.write_text(json.dumps({'official':{'status':'PASS','verified_shots':102400}}))
    with pytest.raises(ValueError,match='held-out'):store.validate(copy.deepcopy(entry))
    receipt.write_text(json.dumps({'official':{'status':'PASS','verified_shots':102400},'held_out':True}))
    assert len(store.validate(entry)['evidence'][0]['receipt_sha256'])==64

def test_receipt_path_cannot_escape_results(tmp_path,entry,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path)
    entry['evidence']=[{'level':'development_verified','claim':'Claim','artifact':'../outside.json'}]
    with pytest.raises(ValueError,match='outside'):store.validate(entry)

def test_tasks_have_separate_snapshots_and_cannot_overwrite_methods(tmp_path,entry):
    db=store.connect(tmp_path/'library.db');store.ingest(db,[entry],'gpt')
    other=copy.deepcopy(entry);other.update(id='other-method',task='other_task');store.ingest(db,[other],'gpt')
    store.snapshot(db,tmp_path/'dqi',task='dqi');store.snapshot(db,tmp_path/'other',task='other_task')
    first=json.loads((tmp_path/'dqi/index.json').read_text());second=json.loads((tmp_path/'other/index.json').read_text())
    assert [e['id'] for e in first['methods']]==[entry['id']]
    assert [e['id'] for e in second['methods']]==['other-method']
    other['id']=entry['id']
    with pytest.raises(ValueError,match='another task'):store.ingest(db,[other],'gpt')
    assert store.show(db,entry['id'])['task']=='dqi'
    with pytest.raises(ValueError,match='another task'):store.snapshot(db,tmp_path/'dqi',task='other_task')
