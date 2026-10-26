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
