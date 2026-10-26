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
