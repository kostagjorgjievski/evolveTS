"""New attempts preserve conversation and source, but receive fresh budgets."""
import json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/literature_acceptance'))
import dfthcsos_pilot as pilot

def test_next_attempt_preserves_parent_and_saved_conversation(tmp_path):
    run=tmp_path/'run';branch=run/'worker/explore_b0';old=branch/'attempt_00';(old/'artifact').mkdir(parents=True)
    (old/'artifact/program.py').write_text('PARENT=1\n');(old/'proposal.md').write_text('prior findings')
    private=run/'private';(private/'sdk').mkdir(parents=True)
    (private/'sdk/sdk-session.json').write_text('{"session_id":"parent-session"}')
    (run/'pilot.json').write_text(json.dumps({'status':'completed','session_seconds_used':855,'results':[{'reward':1.0}]}))
    pilot.advance(run)
    meta=json.loads((run/'pilot.json').read_text())
    assert meta['attempt_index']==1 and meta['session_seconds_used']==0 and meta['max_session_seconds']==12000
    assert (branch/'attempt_01/artifact/program.py').read_text()=='PARENT=1\n'
    assert (old/'artifact/program.py').read_text()=='PARENT=1\n'
    assert json.loads((private/'sdk/sdk-session.json').read_text())['session_id']=='parent-session'
    _,attempt,prompt=pilot.prepare(run)
    assert attempt.name=='attempt_01' and 'SAME saved' in prompt and 'FRESH 200-minute' in prompt
    with pytest.raises(RuntimeError):pilot.advance(run)
