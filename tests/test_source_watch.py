import json
from types import SimpleNamespace
import pytest
from scripts.autoresearch_seeder.source_watch import listing, tick
from scripts.autoresearch_seeder.tools import ToolDispatcher


def item(i): return {'id':i,'scriptVersionId':i,'scriptUrl':'/code/author/notebook-'+str(i)}


def test_listing_rejects_shell_and_repeated_pagination():
    with pytest.raises(ValueError): listing(lambda page: {'html':'shell'})
    with pytest.raises(ValueError): listing(lambda page: {'kernels':[item(i) for i in range(1,101)]})
    pages=[]
    def fetch(page):
        pages.append(page)
        return {'kernels':[item(i) for i in range(1,101)] if page==1 else [item(101)]}
    assert len(listing(fetch))==101 and pages==[1,2]


def test_failure_preserves_success_and_retries_without_paid_work(tmp_path):
    good=lambda page:{'kernels':[item(1)]}
    first=tick(tmp_path,[],good,now=10000)
    assert first['last_successful_check_epoch']==10000
    second=tick(tmp_path,[],lambda p:{},now=11800)
    assert second['state']=='retrieval_unresolved'
    assert second['last_successful_check_epoch']==10000
    assert second['next_attempt_epoch']==12100
    repaired=tick(tmp_path,[],good,now=12100)
    assert repaired['state']=='healthy' and repaired['new_count']==0


def test_kaggle_model_claim_not_accepted_as_auth_fact():
    records=[]
    store=SimpleNamespace(get_source=lambda url:None,record_source=records.append,event=lambda *a:None)
    obj=SimpleNamespace(store=store)
    result=ToolDispatcher._tool_report_access_needed(obj,{'url':'https://www.kaggle.com/competitions/x/code','reason':'needs account'})
    assert result['status']=='retrieval_unresolved'
    assert records[0]['access_claim_verified'] is False


def test_agendas_deduplicate_versions_and_daily_papers_keep_budgets(tmp_path):
    from scripts.autoresearch_seeder.investigations import Investigations
    roots=[tmp_path/'dqi',tmp_path/'chemistry']
    for root in roots:
        root.mkdir()
        (root/'config.json').write_text(json.dumps({'daily_paper_topics':['Search primary papers'],
            'agenda':{'default_budgets':{'max_sessions':12,'max_model_seconds':14400,'max_usd':5}}}))
    watch=tmp_path/'watch'
    tick(watch,roots,lambda p:{'kernels':[item(1)]},now=10000)
    tick(watch,roots,lambda p:{'kernels':[item(1)]},now=11800)
    for root in roots:
        agenda=Investigations(root/'investigations.sqlite')
        rows=agenda.list(); assert len(rows)==2
        assert all(r['budgets']['max_model_seconds']==14400 for r in rows)
        assert all(r['consumed']['sessions']==0 for r in rows)
        assert sum(r['origin'].startswith('daily-papers:') for r in rows)==1
        agenda.close()


def test_notebook_claims_are_ordering_metadata_not_verifier_scores(tmp_path):
    from scripts.autoresearch_seeder.source_watch import score_claim,enqueue_notebooks
    from scripts.autoresearch_seeder.investigations import Investigations
    root=tmp_path/'dqi';root.mkdir();(root/'config.json').write_text('{}')
    row={**item(1),'title':'15.75 circuits, 448 qubits','bestPublicScore':13.71}
    claim=score_claim(row)
    assert claim['claimed_score']==15.75 and len(claim['claims'])==2
    assert score_claim({**item(2),'title':'VQC v15 verified 448q'})['claimed_score'] is None
    assert score_claim({**item(3),'bestPublicScore':float('nan')})['claimed_score'] is None
    enqueue_notebooks(tmp_path/'watch',[root],[row],'2026-10-26T00:00:00Z')
    enqueue_notebooks(tmp_path/'watch',[root],[row],'2026-10-26T00:30:00Z')
    agenda=Investigations(root/'investigations.sqlite');rows=agenda.list();agenda.close()
    assert len(rows)==1 and rows[0]['consumed']['sessions']==0
    assert rows[0]['checkpoint']['scheduling']['claimed_score']==15.75
    assert 'combined_score' not in rows[0]['checkpoint']['scheduling']


def test_legacy_queued_batches_split_but_active_work_and_usage_stay_intact(tmp_path):
    from scripts.autoresearch_seeder.source_watch import enqueue,migrate_queued_listings
    from scripts.autoresearch_seeder.investigations import Investigations
    root=tmp_path/'dqi';root.mkdir();(root/'config.json').write_text('{}')
    bundle=tmp_path/'bundle';bundle.mkdir()
    (bundle/'listing.json').write_text(json.dumps({'checked_utc':'2026-10-26T00:00:00Z',
        'new_notebooks':[{**item(1),'title':'15.75 circuits'},{**item(2),'title':'15.05 portfolio'}]}))
    queued=enqueue(root,'kaggle-freshness:queued','Batch',[{'path':str(bundle)}])
    active=enqueue(root,'kaggle-freshness:active','In progress',[{'path':str(bundle)}])
    agenda=Investigations(root/'investigations.sqlite')
    before=agenda.record_session(active['id'],model_seconds=123,activity_digest='own work')
    migrate_queued_listings(tmp_path/'watch',[root])
    migrate_queued_listings(tmp_path/'watch',[root])
    assert agenda.get(queued['id'])['status']=='superseded'
    assert agenda.get(active['id'])==before
    children=[r for r in agenda.list() if r['origin'].startswith('kaggle-notebook:')]
    assert len(children)==2 and all(r['consumed']['sessions']==0 for r in children)
    agenda.close()


def test_metadata_updates_reorder_idle_candidate_without_mutating_frozen_receipt(tmp_path):
    from scripts.autoresearch_seeder.source_watch import enqueue_notebooks
    from scripts.autoresearch_seeder.investigations import Investigations
    root=tmp_path/'dqi';root.mkdir();(root/'config.json').write_text('{}')
    first={**item(1),'title':'15.05 circuits'}
    enqueue_notebooks(tmp_path/'watch',[root],[first],'2026-10-26T00:00:00Z')
    agenda=Investigations(root/'investigations.sqlite');record=agenda.list()[0]
    snapshot=__import__('pathlib').Path(record['checkpoint']['public_inputs'][0]['path'])/'listing.json'
    original=snapshot.read_bytes()
    changed={**first,'title':'15.75 circuits'}
    enqueue_notebooks(tmp_path/'watch',[root],[changed],'2026-10-26T00:30:00Z')
    assert snapshot.read_bytes()==original
    current=agenda.get(record['id'])
    assert current['checkpoint']['scheduling']['claimed_score']==15.75
    assert current['consumed']==record['consumed'] and len(agenda.list())==1
    active=agenda.record_session(record['id'],model_seconds=12,activity_digest='in flight')
    enqueue_notebooks(tmp_path/'watch',[root],[{**changed,'title':'16.25 circuits'}],'2026-10-26T01:00:00Z')
    assert agenda.get(record['id'])==active
    agenda.close()


def test_new_version_supersedes_only_untouched_queued_old_version(tmp_path):
    from scripts.autoresearch_seeder.source_watch import enqueue_notebooks
    from scripts.autoresearch_seeder.investigations import Investigations
    root=tmp_path/'dqi';root.mkdir();(root/'config.json').write_text('{}')
    row={**item(1),'title':'15.05 circuits'}
    enqueue_notebooks(tmp_path/'watch',[root],[row],'2026-10-26T00:00:00Z')
    agenda=Investigations(root/'investigations.sqlite');old=agenda.list()[0]
    enqueue_notebooks(tmp_path/'watch',[root],[{**row,'scriptVersionId':2,'title':'15.75 circuits'}],'2026-10-26T00:30:00Z')
    assert agenda.get(old['id'])['status']=='superseded'
    assert len(agenda.list('queued'))==1
    agenda.close()
