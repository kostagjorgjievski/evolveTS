"""Exercise real agenda materialization, admission, and frozen RSI handoffs."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.autoresearch_seeder.investigations import Investigations
from scripts.autoresearch_seeder.knowledge import KnowledgeBase, check_findings
from scripts.autoresearch_seeder.research_runtime import run_materialized_investigation
from scripts.autoresearch_seeder.service import validate_service, wake
from scripts.autoresearch_seeder.testing import build_job, E2E_SCRIPT, FakeSearch, fake_fetcher


def config():
    return {'enabled': True, 'task': 'seed_demo', 'provider': {'backend': 'hermes'},
            'reproducer': {'backend': 'hermes'}, 'budgets': {'session_seconds': 30,
                'daily_model_seconds': 120, 'daily_sessions': 3, 'daily_reported_usd': 1},
            'service': {'enabled': True, 'min_free_gib': 0}, 'topics': ['external method X']}


def test_pause_and_daily_limit_do_not_start_model(tmp_path):
    root=tmp_path/'research';root.mkdir()
    forbidden=lambda *_: pytest.fail('Admission must prevent model starts')
    cfg=config();validate_service(cfg)
    (root/'PAUSE').touch()
    assert wake(root,cfg,{},runner=forbidden)['state']=='paused'
    (root/'PAUSE').unlink()
    import datetime
    day=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    ledger={day:{'sessions':3,'model_seconds':0,'usd':0}}
    assert wake(root,cfg,ledger,runner=forbidden)['state']=='daily_budget_wait'
    cfg['budgets']['daily_sessions']=float('inf')
    with pytest.raises(ValueError):validate_service(cfg)


def test_session_usage_persists_and_idle_does_not_spin(tmp_path):
    root=tmp_path/'research';root.mkdir();cfg=config();ledger={};calls=[]
    def run(runtime):
        calls.append(runtime)
        agenda=Investigations(root/'investigations.sqlite');item=agenda.next_eligible()
        agenda.record_session(item['id'],model_seconds=20,usd=.1,activity_digest='actual-test')
        agenda.shelve(item['id'],'test finished');agenda.close()
        return {'investigation_session':item['id']}
    assert wake(root,cfg,ledger,runner=run)['state']=='ready'
    assert wake(root,cfg,ledger,runner=run)['state']=='idle'
    assert len(calls)==1
    assert next(iter(ledger.values()))['model_seconds']==20
    assert json.loads((root/'service-ledger.json').read_text())==ledger


def test_materialized_agenda_uses_real_controller_and_idempotent_verified_publication(tmp_path):
    scaffold=build_job(tmp_path,E2E_SCRIPT)
    task_root=scaffold.adapter.root
    root=tmp_path/'research';root.mkdir()
    agenda=Investigations(root/'investigations.sqlite');knowledge=KnowledgeBase(root/'knowledge.sqlite')
    item=agenda.create('Test published mechanism',budgets={'max_model_seconds':60})
    provider={'name':'test','credential_file':str(tmp_path/'unused.env'),'requested_model':'FakeModel-1'}
    runtime={'root':str(root),'task':'seed_demo','task_root':str(task_root),'provider':provider,
             'reproducer':provider,'test_transport_factory':lambda _:scaffold.shared_transport,
             'test_search_service':FakeSearch()}
    from scripts.autoresearch_seeder.research_runtime import _create_job
    job=_create_job(root,item,runtime)
    runtime['test_fetcher']=fake_fetcher(job,scaffold.config)
    result=run_materialized_investigation(agenda,item,knowledge,runtime)
    assert result['status']=='active'
    assert result['checkpoint']['role']=='scout'
    result=run_materialized_investigation(agenda,agenda.get(item['id']),knowledge,runtime)
    assert result['checkpoint']['role']=='reproducer'
    result=run_materialized_investigation(agenda,agenda.get(item['id']),knowledge,runtime)
    assert result['status']=='completed'
    assert result['checkpoint']['job_stage']=='seed_ready'
    finding=knowledge.get(result['checkpoint']['finding_id'])
    assert finding['payload']['evidence']['level']=='verified_seed'
    assert len(finding['payload']['evidence']['receipt_ids'])==2
    # The source_urls tool field is optional. Certified immutable source
    # provenance must still reach the library when a model omits that field.
    from scripts.autoresearch_seeder.__main__ import _load_controller
    from scripts.autoresearch_seeder.research_runtime import _finding, _close
    controller, _, _ = _load_controller(job)
    for hypothesis in controller.store.list_hypotheses():
        hypothesis['source_urls']=[]
        controller.store.db.execute('UPDATE hypotheses SET payload=? WHERE id=?',
                                    (json.dumps(hypothesis),hypothesis['id']))
    controller.store.db.commit()
    recovered=_finding(controller,result,knowledge,[],job,'reproducer')
    assert recovered['id']==finding['id']
    _close(controller)
    out=check_findings(root,'new-branch',0,parent={'task':'seed_demo'},attempt_record=str(tmp_path/'attempt.json'))
    assert len(out['delivered'])==1
    again=run_materialized_investigation(agenda,agenda.get(item['id']),knowledge,runtime)
    assert again['checkpoint']['finding_id']==finding['id']
    assert len(knowledge.ready_findings('new-branch',0,{'task':'seed_demo'}))==1
    assert agenda.next_eligible() is None
    agenda.close();knowledge.close()


def test_bridge_delivers_scoped_sources_without_model_call_or_duplicate(tmp_path):
    from scripts.autoresearch_seeder.rsi_bridge import attach
    root=tmp_path/'research';base=KnowledgeBase(root/'knowledge.sqlite')
    run=tmp_path/'run';(run/'private').mkdir(parents=True)
    branch=run/'worker/explore_b0';(branch/'attempt_00/artifact').mkdir(parents=True)
    (branch/'attempt_00/artifact/program.py').write_text('print("parent")')
    sections={'mechanism':'Public direction','sources':['https://example.org/paper'],
              'compatibility':{'task':'dfthcsos','applies_to_parents':True},
              'evidence':{'level':'diagnostic_supported','receipt_ids':['actual-limited-test']},
              'opportunity':{'status':'prediction'},'first_experiment':'measure small shape'}
    private=base.add_finding({**sections,'mechanism':'Secret B'},branch='B',ready=True)
    public=base.add_finding(sections,ready=True)
    prompt=attach(run,branch,'original',knowledge_root=root,branch_id='A')
    assert 'EXTERNAL R&D HANDOFFS:' in prompt
    files=list((branch/'hermes-handoffs').glob('*.json'))
    assert len(files)==1
    text=files[0].read_text()
    assert 'Public direction' in text and 'Secret B' not in text
    assert attach(run,branch,prompt,knowledge_root=root,branch_id='A')==prompt
    assert len(base.deliveries())==1
    # Frozen bytes tampered with: refuse to advise from them.
    files[0].write_text('tampered')
    assert attach(run,branch,'fresh prompt',knowledge_root=root,branch_id='A')=='fresh prompt'
    base.close()


def test_released_package_delivers_only_after_boundary_and_missing_parent_fails_closed(tmp_path):
    root=tmp_path/'research';base=KnowledgeBase(root/'knowledge.sqlite')
    sections={'mechanism':'Private A method','sources':['public-url'],
              'compatibility':{'task':'dfthcsos','applies_to_parents':True,'parent_code_sha256':'known'},
              'evidence':{'level':'diagnostic_supported'},'opportunity':{},'first_experiment':'small check'}
    record=base.add_finding(sections,branch='A',ready=True)
    released=base.release(record['id'],at_level=1)
    assert base.ready_findings('B',0,{'task':'dfthcsos','code_sha256':'known'})==[]
    assert base.ready_findings('B',1,{'task':'dfthcsos'})==[]
    outcome=check_findings(root,'B',1,parent={'task':'dfthcsos','code_sha256':'known'},attempt_record=str(tmp_path/'attempt.json'))
    assert len(outcome['delivered'])==1
    base.close()


def test_own_branch_request_stays_private_and_is_idempotent(tmp_path):
    from scripts.autoresearch_seeder.rsi_bridge import branch_request
    root=tmp_path/'research';base=KnowledgeBase(root/'knowledge.sqlite')
    run=tmp_path/'run';branch=run/'worker/explore_b0';(branch/'attempt_00/artifact').mkdir(parents=True)
    (branch/'attempt_00/artifact/program.py').write_text('private_parent_source=42')
    (branch/'experimental-memory.md').write_text('Private experiment failed; try sparse rank test')
    branch_request(run,branch,root,'A',0,'dfthcsos')
    branch_request(run,branch,root,'A',0,'dfthcsos')
    private=base.eligible_records('A',0)
    assert len(private)==1 and 'private_parent_source' in private[0]['payload']['parent_code']
    assert 'Private experiment failed' in private[0]['payload']['own_experimental_memory']
    assert base.eligible_records('B',0)==[]
    agenda=Investigations(root/'investigations.sqlite')
    assert len(agenda.list())==1 and agenda.list()[0]['branch']=='A'
    agenda.close();base.close()


def test_deferred_validation_runs_after_model_session_and_exact_receipts_publish(tmp_path):
    executions=[]
    controller=build_job(tmp_path,E2E_SCRIPT,overrides={'validation':{'deferred_development':True}},
                         execution_observer=lambda kind,_:executions.append(kind))
    state=controller.run()
    assert state['stage']=='seed_ready'
    requests=controller.store.list_events('development_requested')
    assert len(requests)==1
    events=controller.store.list_events()
    request_index=next(i for i,e in enumerate(events) if e['kind']=='development_requested')
    ended=next(i for i,e in enumerate(events[request_index:],request_index) if e['kind']=='session_ended')
    # The tool only requested work while the agent was active. Trusted execution follows.
    assert ended>request_index
    assert executions.count('development_validation')==1
    assert len(controller.store.list_experiments('confirmation_validation'))==1


def test_install_host_preserves_existing_memory_and_is_repeatable(tmp_path):
    from scripts.autoresearch_seeder.install_host import install
    host=tmp_path/'host';module=host/'scripts/literature_acceptance/experimental_memory.py';module.parent.mkdir(parents=True)
    module.write_text('from pathlib import Path\nimport json\nROOT=Path(__file__).resolve().parents[2]\ndef attach(run,branch,prompt):\n    return prompt+"own memory"\n')
    campaign=host/'runs/campaign';campaign.mkdir(parents=True)
    (campaign/'campaign.json').write_text('{"task":"dfthcsos"}')
    install(host,tmp_path/'research',campaign)
    once=module.read_text();install(host,tmp_path/'research',campaign)
    assert module.read_text()==once
    assert once.count('def attach(')==1 and once.count('def _attach_own_memory(')==1
    namespace={'__file__':str(module)};exec(compile(once,str(module),'exec'),namespace)
    run=tmp_path/'run';(run/'private').mkdir(parents=True);(run/'pilot.json').write_text('{}')
    assert namespace['attach'](run,tmp_path/'branch','hello ')=='hello own memory'


def test_public_fetch_supports_anonymous_read_rpc_but_refuses_account_actions(tmp_path):
    from scripts.autoresearch_seeder.tools import SourceFetcher,AccessDenied
    fetcher=SourceFetcher(tmp_path/'sources',[])
    class Reply:
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def read(self,_):return b'{"public":"source"}'
    class Opener:
        def open(self,request,timeout):
            assert request.get_method()=='POST'
            assert json.loads(request.data)=={'competitionId':1}
            return Reply()
    fetcher._opener=Opener();fetcher._cookies=[]
    assert b'public' in fetcher._http_request('https://www.kaggle.com/api/i/kernels.KernelsService/ListKernels',method='POST',request_json={'competitionId':1})
    with pytest.raises(AccessDenied):fetcher._http_request('https://www.kaggle.com/api/i/CreateSubmission',method='POST')


def test_source_revisions_keep_earlier_exact_bytes(tmp_path):
    from scripts.autoresearch_seeder.tools import SourceFetcher
    fetcher=SourceFetcher(tmp_path/'sources',[],get=lambda _:b'first source')
    fetcher.check_url=lambda url:url
    first=fetcher.fetch('https://example.org/paper')
    fetcher._get=lambda _:b'updated source'
    second=fetcher.fetch('https://example.org/paper')
    assert first['local_path']!=second['local_path']
    assert Path(first['local_path']).read_bytes()==b'first source'
    assert Path(second['local_path']).read_bytes()==b'updated source'


def test_cold_acceptance_uses_only_frozen_public_input_and_no_library(tmp_path, monkeypatch):
    scaffold=build_job(tmp_path,E2E_SCRIPT)
    root=tmp_path/'research';root.mkdir()
    agenda=Investigations(root/'investigations.sqlite');knowledge=KnowledgeBase(root/'knowledge.sqlite')
    item=agenda.create('Cold discovered public source',budgets={'max_model_seconds':60})
    source=tmp_path/'public';source.mkdir();(source/'notebook.py').write_text('# public method only')
    item['checkpoint'].update(cold_acceptance=True,public_inputs=[{'path':str(source),
        'url':'https://example.org/new-notebook','attribution':'public author'}])
    provider={'name':'test','credential_file':str(tmp_path/'unused.env'),'requested_model':'FakeModel-1'}
    runtime={'root':str(root),'task':'seed_demo','task_root':str(scaffold.adapter.root),
             'provider':provider,'public_inputs':[{'path':str(tmp_path/'forbidden-old-bundle')}],
             'test_transport_factory':lambda _:scaffold.shared_transport,'test_search_service':FakeSearch()}
    from scripts.autoresearch_seeder.research_runtime import _create_job
    job=_create_job(root,item,runtime)
    assert (job/'sources/provided-0/notebook.py').read_text()=='# public method only'
    runtime['test_fetcher']=fake_fetcher(job,scaffold.config)
    def forbidden(*args):pytest.fail('Cold acceptance must not read library methods')
    monkeypatch.setattr('scripts.autoresearch_seeder.investigations.eligible_knowledge',forbidden)
    run_materialized_investigation(agenda,item,knowledge,runtime)
    assert json.loads((job/'worker/research-agenda.json').read_text())['eligible_knowledge']==[]
    agenda.close();knowledge.close()


def test_approved_agenda_budget_reload_keeps_consumption_and_artifact(tmp_path):
    scaffold=build_job(tmp_path,E2E_SCRIPT)
    root=tmp_path/'research';root.mkdir()
    agenda=Investigations(root/'investigations.sqlite')
    item=agenda.create('Approved finite budget migration',budgets={'max_model_seconds':60})
    provider={'name':'test','credential_file':str(tmp_path/'unused.env'),'requested_model':'FakeModel-1'}
    runtime={'task':'seed_demo','task_root':str(scaffold.adapter.root),'provider':provider}
    from scripts.autoresearch_seeder.research_runtime import _create_job
    job=_create_job(root,item,runtime)
    data=json.loads((job/'job.json').read_text());before=(job/'worker/attempt_00/artifact/program.py').read_bytes()
    from scripts.autoresearch_seeder.store import ResearchStore
    store=ResearchStore(job/'private/research.sqlite');store.charge('model',seconds=7);store.close()
    item['budgets']['max_model_seconds']=120
    _create_job(root,item,runtime)
    cfg=json.loads(Path(data['config_path']).read_text())
    assert cfg['budgets']['model_session_seconds']==120
    assert (job/'worker/attempt_00/artifact/program.py').read_bytes()==before
    store=ResearchStore(job/'private/research.sqlite')
    assert store.totals()['model']['seconds']==7
    store.close();agenda.close()


@pytest.mark.parametrize('previous_role,previous_sessions,origin,start_role',[
    ('scout',1,'agenda',None),('reproducer',1,'agenda',None),
    (None,0,'public_hypothesis_follow_up:parent:hypothesis','reproducer')])
def test_scout_window_hands_off_even_without_structured_hypothesis(
        tmp_path, monkeypatch, previous_role, previous_sessions, origin, start_role):
    scaffold=build_job(tmp_path,E2E_SCRIPT)
    root=tmp_path/'research';root.mkdir()
    agenda=Investigations(root/'investigations.sqlite');knowledge=KnowledgeBase(root/'knowledge.sqlite')
    monkeypatch.setattr('scripts.autoresearch_seeder.research_runtime._follow_up_requirements',lambda *args:({},None))
    item=agenda.create('Scout source research without structured metadata',origin=origin,budgets={'max_model_seconds':60})
    item['consumed']['sessions']=previous_sessions
    item['checkpoint'].update(role=previous_role,start_role=start_role)
    provider={'name':'test','credential_file':str(tmp_path/'unused.env'),'requested_model':'FakeModel-1'}
    runtime={'root':str(root),'task':'seed_demo','task_root':str(scaffold.adapter.root),
             'provider':provider,'reproducer':provider,
             'test_transport_factory':lambda _:scaffold.shared_transport,'test_search_service':FakeSearch()}
    from scripts.autoresearch_seeder.research_runtime import _create_job
    from scripts.autoresearch_seeder.__main__ import _load_controller
    from scripts.autoresearch_seeder.research_runtime import _close
    job=_create_job(root,item,runtime)
    controller,_,_=_load_controller(job)
    assert controller.store.list_hypotheses()==[]
    _close(controller)
    runtime['test_fetcher']=fake_fetcher(job,scaffold.config)
    result=run_materialized_investigation(agenda,item,knowledge,runtime)
    assert result['checkpoint']['role']=='reproducer'
    agenda.close();knowledge.close()


@pytest.mark.parametrize('branch,verified,parent_origin,should_queue',[
    (None,True,'agenda',True),('private-A',True,'agenda',False),
    (None,False,'agenda',False),(None,True,'public_hypothesis_follow_up:prior',False)])
def test_idle_agenda_advances_own_unselected_public_hypothesis_only(
        tmp_path,monkeypatch,branch,verified,parent_origin,should_queue):
    from scripts.autoresearch_seeder.service import enqueue_public_follow_up
    from scripts.autoresearch_seeder.store import ResearchStore
    root=tmp_path/'research';root.mkdir();cfg=config();cfg['service']['follow_up_hypotheses']=True
    agenda=Investigations(root/'investigations.sqlite')
    parent=agenda.create('Public research',branch=branch,origin=parent_origin)
    checkpoint={'job_stage':'seed_ready'}
    agenda.db.execute('UPDATE investigations SET status=?,checkpoint=? WHERE id=?',
                      ('completed',json.dumps(checkpoint),parent['id']));agenda.db.commit()
    job=root/'jobs/autoresearch-seeder/seed_demo'/parent['id']
    public=job/'sources/public.txt';public.parent.mkdir(parents=True);public.write_text('Public source')
    export=job/'exports/seed-demo';artifact=export/'source-bundle';artifact.mkdir(parents=True)
    (artifact/'program.py').write_text('# Certified parent, no candidate supplied by monitor')
    (export/'SOURCES.json').write_text(json.dumps({'sources':[{'url':'https://example.org/paper'}]}))
    store=ResearchStore(job/'private/research.sqlite')
    store.record_source({'url':'https://example.org/paper','status':'accessed','local_path':str(public)})
    for hid in ['selected','unimplemented','rejected']:
        store.record_hypothesis({'id':hid,'mechanism':'Model-authored '+hid,
            'source_urls':['https://example.org/paper'],'first_test':'Model-authored cheapest test'})
    store.record_decision({'action':'reject','hypothesis_id':'rejected'})
    store.record_decision({'action':'continue','hypothesis_id':'selected'})
    store.close()
    monkeypatch.setattr('scripts.autoresearch_seeder.publisher.verify_export',lambda p:{'ok':verified})
    result=enqueue_public_follow_up(root,cfg,agenda,agenda.list())
    if should_queue:
        assert result['checkpoint']['hypothesis_id']=='unimplemented'
        assert result['checkpoint']['start_role']=='reproducer'
        assert result['branch'] is None
        handoff=Path(result['checkpoint']['public_inputs'][0]['path'])
        assert (handoff/'parent-artifact/program.py').is_file()
        assert 'UNTESTED' in (handoff/'RESEARCH-HANDOFF.json').read_text()
        assert enqueue_public_follow_up(root,cfg,agenda,agenda.list()) is None
        # A restart never changes the parent's scientific artifacts or usage.
        assert agenda.get(parent['id'])['consumed']['sessions']==0
    else:
        assert result is None
    agenda.close()


def test_follow_up_same_parent_score_keeps_research_open_without_confirmation(tmp_path):
    c=build_job(tmp_path,[])
    c.config['validation'].update(research_parent_score=3.0,research_target_hypothesis='target')
    c.save_job(stage='implementing')
    e={'id':'same-parent','kind':'development_validation','status':'pass',
       'metrics':{'combined_score':3.0},'input_bundle_sha256':c._current_bundle()}
    c.store.record_experiment(e)
    c._resolve_development(e,6)
    assert c.job_state()['stage']=='implementing'
    assert c.store.list_experiments('confirmation_validation')==[]
    assert c.adapter.baseline_score()==1.0
    c.store.record_decision({'action':'reject','hypothesis_id':'target'})
    c._resolve_development(e,6)
    assert c.job_state()['stage']=='completed_no_improvement'
    assert c.store.totals()=={}


def test_publisher_refuses_unchanged_parent_follow_up_without_renormalizing(tmp_path):
    from scripts.autoresearch_seeder.publisher import evaluate_gates
    c=build_job(tmp_path,E2E_SCRIPT);c.run()
    assert c.job_state()['stage']=='seed_ready'
    old=evaluate_gates(c);score=old['evidence']['scores']['development']
    c.config['validation']['research_parent_score']=score
    gates=evaluate_gates(c)
    assert not gates['accepted']
    assert any('research parent' in x for x in gates['reasons'])
    assert gates['evidence']['baseline']==1.0
    assert gates['evidence']['scores']['development']==score


def test_follow_up_negative_target_closes_without_republishing_parent(tmp_path):
    c=build_job(tmp_path,[])
    c.config['validation'].update(research_parent_score=3.0,research_target_hypothesis='target')
    c.store.record_decision({'action':'reject','hypothesis_id':'target','notes':'Unsupported gate; see own source audit'})
    c._advance('queued')
    assert c.job_state()['stage']=='completed_no_improvement'
    assert not list((c.job_dir/'exports').glob('seed-*'))
    assert c.store.totals()=={}
