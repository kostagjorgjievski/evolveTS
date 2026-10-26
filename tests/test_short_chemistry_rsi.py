"""Bounded crossed-seed pilot configuration and deferred full grading."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from scripts import short_chemistry_rsi as pilot


def test_crossed_models_seed_families_and_memory_prompt(tmp_path, monkeypatch):
    import dfthcsos_opus_prepared as prepared
    def initialize(run):
        art=run/'worker/explore_b0/attempt_00/artifact';art.mkdir(parents=True)
        (run/'private').mkdir();return {}
    monkeypatch.setattr(prepared,'initialize',initialize)
    campaign=tmp_path/'campaign';campaign.mkdir()
    branches={}
    for name in pilot.NAMES:
        seed=tmp_path/name;source=seed/'source-bundle';source.mkdir(parents=True)
        (source/'program.py').write_text(name);(source/'helper.py').write_text('own helper')
        (seed/'MANIFEST.json').write_text(json.dumps({'development':{'score':4.146 if name.endswith('thc') else 3.57},'confirmation':{'score':4.146 if name.endswith('thc') else 3.57}}))
        branches[name]={'seed':str(seed)}
    pilot.save(campaign/'campaign.json',{'branches':branches})
    for name in pilot.NAMES:
        run=pilot.initialize_attempt(campaign,name,1);meta=pilot.read(run/'pilot.json')
        assert meta['max_session_seconds']==1200 and meta['conversation_memory'] is False
        assert meta['effort']==('max' if name.startswith('glm') else 'medium')
        assert (run/'worker/explore_b0/attempt_00/artifact/helper.py').exists()
        prompt=pilot.prepare(run)[2]
        assert 'experimental-memory.md' in prompt and 'Other branch live work' in prompt
        assert '20 minutes' in prompt and 'AFTER this model session' in prompt


def test_short_full_validation_tool_only_freezes_request(tmp_path,monkeypatch):
    from scripts import short_chemistry_tools as tools
    attempt=tmp_path/'attempt_00';artifact=attempt/'artifact';artifact.mkdir(parents=True)
    (artifact/'program.py').write_text('own source')
    monkeypatch.setattr(tools.server.task,'ATTEMPT',attempt)
    result=asyncio.run(tools.call(None,SimpleNamespace(name='validate_candidate',arguments={})))
    data=json.loads(result.content[0].text)
    assert data['status']=='requested' and 'program.py' in data['files']
    assert (attempt.parent/'full-validation-request.json').exists()
    assert not list(tmp_path.rglob('result.json'))


def test_authorized_extension_preserves_twelve_and_adds_exactly_thirty_two(tmp_path):
    from dream_rsi.env.trace_store import scaffold_grid_nodes
    campaign=tmp_path/'campaign';workspace=campaign/'workspace';workspace.mkdir(parents=True)
    nodes=[n.to_dict() for n in scaffold_grid_nodes(workspace,max_width=4,max_refine=2)]
    for n in nodes:n.update(status='done',raw={'evaluated':True,'combined_score':4.146})
    original=json.loads(json.dumps(nodes))
    pilot.save(workspace/'raw_scores.json',{'nodes':nodes,'baseline':{'combined_score':1.0}})
    pilot.save(campaign/'campaign.json',{'branches':dict.fromkeys(pilot.NAMES,{}),
        'attempts_per_branch':3,'development_seconds_per_attempt':1200})
    assert pilot.extend_completed_grid(campaign)=={'preserved':12,'appended':32,'total':44}
    actual=pilot.read(workspace/'raw_scores.json')['nodes']
    assert actual[:12]==original
    assert len({n['id'] for n in actual})==44
    assert all(n['status']=='pending' and not n['raw']['evaluated'] for n in actual[12:])
    assert all(sum(n['branch']==b for n in actual)==11 for b in range(4))
    assert pilot.read(campaign/'campaign.json')['development_seconds_per_attempt']==1200


def test_opus_branch_uses_native_oauth_medium_and_verified_seed(tmp_path,monkeypatch):
    import dfthcsos_opus_prepared as prepared
    def initialize(run):
        (run/'worker/explore_b0/attempt_00/artifact').mkdir(parents=True)
        (run/'private').mkdir();return {}
    monkeypatch.setattr(prepared,'initialize',initialize)
    seed=tmp_path/'seed';(seed/'source-bundle').mkdir(parents=True)
    (seed/'source-bundle/program.py').write_text('verified seed')
    pilot.save(seed/'MANIFEST.json',{'development':{'score':4.149479453986217},'confirmation':{'score':4.149479453986217}})
    campaign=tmp_path/'campaign';pilot.save(campaign/'campaign.json',{'branches':{'opus_best':{'seed':str(seed)}}})
    run=pilot.initialize_attempt(campaign,'opus_best',1);meta=pilot.read(run/'pilot.json')
    assert (meta['provider'],meta['worker_model'],meta['effort'])==('anthropic_oauth','claude-opus-5-5','medium')
    assert meta['max_session_seconds']==1200 and meta['experimental_memory']
    assert pilot.read(run/'worker/explore_b0/parent-result.json')['combined_score']==4.149479453986217


def test_upstream_exploration_instructions_reach_delivered_prompt(tmp_path):
    import hashlib
    campaign=tmp_path/'campaign';run=campaign/'branches/opus_best/attempt_01';branch=run/'worker/explore_b0'
    (branch/'attempt_00/artifact').mkdir(parents=True);(run/'private').mkdir()
    pilot.save(campaign/'campaign.json',{'experimental_memory':{'enabled':True},'initial_runs':{}})
    pilot.save(run/'pilot.json',{'campaign':str(campaign),'worker_model':'claude-opus-5-5','effort':'medium','max_session_seconds':1200})
    b,a,p=pilot.prepare(run);delivered=pilot.audited_own_context(run,b,p)
    upstream=(pilot.HOST/'upstream/dream-rsi/dream_rsi/prompts/explore.txt').read_text()
    for heading in ['## 2. Learn from both successes and failures',"## 3. Don't converge into a local optimum",'## 4. Propose and implement']:
        assert heading in delivered
    assert 'Deliberately favor a structurally different mechanism' in delivered
    assert 'Never read another branch or the archived previous campaign' in delivered
    assert 'experimental-history/' in delivered and '$node_dir' not in delivered
    audit=pilot.read(run/'private/prompt-integration.json')
    assert audit['upstream_sha256']==hashlib.sha256(upstream.encode()).hexdigest()
    assert audit['delivered_sha256']==hashlib.sha256(delivered.encode()).hexdigest()
    assert (run/'private/delivered-prompt.txt').read_text()==delivered


def test_provider_error_messages_cannot_be_counted_as_development():
    assert not pilot.productive_development([{'type':'AssistantMessage','data':{'content':[{'text':'API Error 503'}]}},
        {'type':'ResultMessage','data':{'is_error':True}}])
    assert not pilot.productive_development([{'type':'AssistantMessage','data':{'error':'api_error','content':[{'name':'mcp__acceptance__diagnose_candidate'}]}}])
    assert pilot.productive_development([{'type':'AssistantMessage','data':{'content':[{'name':'mcp__acceptance__diagnose_candidate'}]}}])


def test_provider_only_failure_never_reaches_grading(tmp_path):
    run=tmp_path/'run';(run/'private').mkdir(parents=True)
    pilot.save(run/'private/status.json',{'tools':['mcp__acceptance__diagnose_candidate']})
    (run/'private/sdk-events.jsonl').write_text(json.dumps({'type':'AssistantMessage','data':{'content':[{'text':'API Error: 503'}]}})+'\n')
    meta={'status':'grading','worker_error':'503'}
    pilot.finish_worker(run,meta,tmp_path/'nonexistent',tmp_path/'artifact',tmp_path/'branch','503')
    saved=pilot.read(run/'pilot.json')
    assert saved['status']=='infrastructure_blocked' and 'results' not in saved


def test_full_own_final_receipts_inherited_without_old_campaign(tmp_path):
    c=tmp_path/'campaign';parent=c/'branches/opus_best/attempt_01';run=c/'branches/opus_best/attempt_02'
    branch=run/'worker/explore_b0';(branch/'attempt_00/artifact').mkdir(parents=True);(run/'private').mkdir()
    pilot.save(c/'campaign.json',{'experimental_memory':{'enabled':True},'initial_runs':{'opus_best':str(parent)}})
    pilot.save(parent/'pilot.json',{'round':1,'status':'completed','results':[]})
    pilot.save(parent/'private/candidate-development/result.json',{'status':'PASS','combined_score':4.149})
    pilot.save(run/'pilot.json',{'campaign':str(c),'round':2,'worker_model':'claude-opus-5-5','effort':'medium','max_session_seconds':1200})
    b,a,p=pilot.prepare(run);pilot.audited_own_context(run,b,p)
    saved=branch/'experimental-history'/parent.name/'private/candidate-development/result.json'
    assert pilot.read(saved)['combined_score']==4.149
    manifest=pilot.read(run/'private/experimental-memory.json')
    assert manifest['source_runs']==[str(parent)]
    assert any(x.get('kind')=='full trusted own final receipt' for x in manifest['manifest'])
