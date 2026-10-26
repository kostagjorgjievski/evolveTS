"""Parallel lane selection and durable admission; no provider calls."""
import datetime
import json
from pathlib import Path

from scripts.autoresearch_seeder.investigations import Investigations
from scripts.autoresearch_seeder.parallel_service import ParallelOwner, select_candidate, write
from tests.test_hermes_service import config


def make(tmp_path):
    cfg = config()
    cfg['budgets'].update(session_seconds=20, daily_model_seconds=100, daily_sessions=3)
    cfg['service'].update(continuous_discovery=True, parallel_scout_reproducer=True)
    agenda = Investigations(tmp_path/'investigations.sqlite')
    repro = agenda.create('Own public candidate')
    agenda.record_session(repro['id'], model_seconds=5, checkpoint_update={'role': 'scout'})
    repro = agenda.get(repro['id'])
    scout = agenda.create('Next independent public direction')
    agenda.close()
    return cfg, repro, scout


def launch(work, record):
    # Fake child identity: never starts paid work.
    return {'pid': 99999999, 'create_time': 1.}


def test_two_lanes_reserve_combined_budget_and_prevent_duplicates(tmp_path):
    cfg, repro, scout = make(tmp_path)
    owner = ParallelOwner(tmp_path, cfg)
    assert owner.admit('reproducer', repro, launch)
    assert owner.admit('scout', scout, launch)
    assert not owner.admit('scout', scout, launch)
    assert not owner.admit('other', scout, launch)
    used = next(iter(owner.state['ledger'].values()))
    assert used['sessions'] == 2 and used['model_seconds'] == 60
    recovered = ParallelOwner(tmp_path, cfg)
    assert len(recovered.state['active']) == 2
    assert recovered.state['ledger'] == owner.state['ledger']


def test_reconciliation_refunds_unused_time_once_and_preserves_usage(tmp_path):
    cfg, repro, scout = make(tmp_path)
    owner = ParallelOwner(tmp_path, cfg)
    owner.admit('scout', scout, launch)
    entry = owner.state['active']['scout']
    agenda = Investigations(tmp_path/'investigations.sqlite')
    agenda.record_session(scout['id'], model_seconds=7, usd=.2, checkpoint_update={'role': 'scout'})
    agenda.close()
    write(Path(entry['session_dir'])/'result.json', {'ok': True})
    owner.reconcile(is_alive=lambda _: False)
    owner.reconcile(is_alive=lambda _: False)
    used = next(iter(owner.state['ledger'].values()))
    assert used == {'sessions': 1, 'model_seconds': 7., 'usd': .2}
    assert not owner.state['active']


def test_reservations_block_last_daily_slot_and_small_time_remainder(tmp_path):
    cfg, repro, scout = make(tmp_path)
    cfg['budgets']['daily_sessions'] = 1
    owner = ParallelOwner(tmp_path, cfg)
    assert owner.admit('scout', scout, launch)
    assert not owner.admit('reproducer', repro, launch)
    cfg['budgets']['daily_sessions'] = 3
    cfg['budgets']['daily_model_seconds'] = 35
    assert not owner.admit('reproducer', repro, launch)


def test_reproducer_is_prioritized_and_scout_runs_on_different_job(tmp_path):
    cfg, repro, scout = make(tmp_path)
    assert select_candidate(tmp_path, cfg, {})[1]['id'] == repro['id']
    active = {'reproducer': {'investigation': repro['id']}}
    role, selected = select_candidate(tmp_path, cfg, active)
    assert role == 'scout' and selected['id'] == scout['id']
    active['scout'] = {'investigation': scout['id']}
    assert select_candidate(tmp_path, cfg, active) is None


def test_completed_scout_backlog_prevents_unbounded_discovery(tmp_path):
    cfg, repro, scout = make(tmp_path)
    agenda = Investigations(tmp_path/'investigations.sqlite')
    agenda.record_session(scout['id'], model_seconds=3, checkpoint_update={'role': 'scout'})
    agenda.close()
    assert select_candidate(tmp_path, cfg, {'reproducer': {'investigation': repro['id']}}) is None


def test_dead_worker_fails_closed_without_duplicate_or_unbilled_retry(tmp_path):
    cfg, repro, scout = make(tmp_path)
    owner = ParallelOwner(tmp_path, cfg)
    owner.admit('scout', scout, launch)
    owner.reconcile(is_alive=lambda _: False)
    assert (tmp_path/'PAUSE').exists()
    assert next(iter(owner.state['ledger'].values()))['model_seconds'] == 30
    assert not owner.state['active']


def test_two_benchmark_roots_share_inflight_daily_admission(tmp_path):
    first=tmp_path/'chemistry';second=tmp_path/'dqi'
    first.mkdir();second.mkdir()
    cfg,a,b=make(first)
    cfg2,c,d=make(second)
    for conf in [cfg,cfg2]:
        conf['budgets']['daily_sessions']=2
        conf['service'].update(budget_group_roots=[str(first),str(second)],
                              budget_group_lock=str(tmp_path/'shared.lock'))
    chemistry=ParallelOwner(first,cfg);dqi=ParallelOwner(second,cfg2)
    assert chemistry.admit('scout',b,launch)
    assert dqi.admit('scout',d,launch)
    assert not chemistry.admit('reproducer',a,launch)
    assert not dqi.admit('reproducer',c,launch)
    assert sum(next(iter(o.state['ledger'].values()))['sessions'] for o in [chemistry,dqi])==2


def test_continuous_scout_ignores_count_and_daily_time_but_not_reproducer_time(tmp_path):
    cfg,repro,scout=make(tmp_path);cfg['budgets']['daily_sessions']=None
    cfg['service']['scout_ahead_queue']=True
    owner=ParallelOwner(tmp_path,cfg);day=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    owner.state['ledger'][day]={'sessions':900,'model_seconds':200,'usd':0}
    assert owner.admit('scout',scout,launch)
    assert not owner.admit('reproducer',repro,launch)
    assert owner.state['ledger'][day]['sessions']==901


def test_continuous_discovery_not_blocked_by_reproducer_backlog(tmp_path):
    cfg,repro,scout=make(tmp_path);cfg['service']['scout_ahead_queue']=True
    cfg['topics']=['A genuinely different public research mechanism']
    agenda=Investigations(tmp_path/'investigations.sqlite');agenda.shelve(scout['id'],'fixture');agenda.close()
    active={'reproducer':{'investigation':repro['id']}}
    selected=select_candidate(tmp_path,cfg,active)
    assert selected and selected[0]=='scout'


def test_no_session_count_limit_still_preserves_time_budget(tmp_path):
    agenda=Investigations(tmp_path/'investigations.sqlite')
    r=agenda.create('Long sequence',budgets={'max_sessions':None,'max_model_seconds':100})
    for i in range(15):r=agenda.record_session(r['id'],model_seconds=1,activity_digest=str(i))
    assert r['status']=='active' and r['consumed']['sessions']==15
    r=agenda.record_session(r['id'],model_seconds=100,activity_digest='last')
    assert r['status']=='shelved';agenda.close()


def test_only_ready_packet_enters_kimi_queue(tmp_path):
    from scripts.autoresearch_seeder.parallel_service import role_of
    from scripts.autoresearch_seeder.store import ResearchStore
    cfg,repro,scout=make(tmp_path)
    job=tmp_path/'jobs/autoresearch-seeder/dfthcsos'/scout['id']
    store=ResearchStore(job/'private/research.sqlite')
    store.record_hypothesis({'id':'hyp','mechanism':'unreviewed idea'})
    assert role_of(tmp_path,scout,'dfthcsos',True)=='scout'
    store.event('scout_packet',{'packet':{'handoff_status':'ready_for_review'}})
    assert role_of(tmp_path,scout,'dfthcsos',True)=='reproducer'
    store.close()


def test_removing_count_cap_keeps_active_investigation_unchanged_until_boundary(tmp_path):
    cfg,repro,scout=make(tmp_path);cfg['agenda']={'default_budgets':{'max_sessions':None}}
    cfg['service']['scout_ahead_queue']=True
    active={'scout':{'investigation':scout['id']}}
    select_candidate(tmp_path,cfg,active)
    agenda=Investigations(tmp_path/'investigations.sqlite')
    assert agenda.get(scout['id'])['budgets']['max_sessions'] is not None
    assert agenda.get(repro['id'])['budgets']['max_sessions'] is None
    assert agenda.get(repro['id'])['consumed']==repro['consumed']
    agenda.close()
