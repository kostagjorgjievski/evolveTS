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
