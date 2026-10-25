import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('chemistry_supervise',ROOT/'scripts/chemistry_campaign/supervise.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def test_only_two_passing_checks_can_become_parent():
    assert module.candidate_reward({'results':[{'status':'PASS','reward':2},{'status':'PASS','reward':1.8}]})==1.8
    assert module.candidate_reward({'results':[{'status':'PASS','reward':2},{'status':'ERROR'}]}) is None
    assert module.candidate_reward({'results':[{'status':'PASS','reward':2}]}) is None

def test_new_round_has_own_best_source_fresh_context_and_reset_budget(tmp_path):
    c=tmp_path/'campaign';branch=c/'branches/gpt';source=tmp_path/'frozen';source.mkdir();(source/'program.py').write_text('OWN_VERIFIED_PARENT=1\n')
    module.save(branch/'best.json',{'artifact':str(source),'reward':1.2,'results':[{'status':'PASS','reward':1.2},{'status':'PASS','reward':1.3}]})
    run=module.new_attempt(c,'gpt',2);m=module.read(run/'pilot.json')
    assert (run/'worker/explore_b0/attempt_00/artifact/program.py').read_text()=='OWN_VERIFIED_PARENT=1\n'
    assert m['effort']=='medium' and m['harness']=='codex'
    assert m['max_session_seconds']==12000 and m['session_seconds_used']==0
    assert m['prepared_parent_context'] and not m['conversation_memory']
    assert m['parent_best_reward']==1.2 and not (run/'private/sdk').exists()
    assert (run/'worker/explore_b0/preparation-guide.md').exists()

def test_actual_rsi_engine_records_three_independent_chains_and_replays(tmp_path,monkeypatch):
    import sys
    sys.path.insert(0,str(ROOT/'scripts/chemistry_campaign'))
    import rsi_controller as rc
    from dream_rsi.agents.claude import ClaudeAgent
    from dream_rsi.exploration import runner
    from dream_rsi.cli.main import main
    monkeypatch.setattr(rc,'NAMES',['opus','kimi','gpt'])
    c=tmp_path/'campaign';c.mkdir();initial={}
    def finish(run,name,reward):
        a=run/'worker/explore_b0/attempt_00';(a/'proposal.md').write_text('Measured synthetic checkpoint')
        results=[]
        for label in ['development','confirmation']:
            path=run/'private'/f'{label}.json';rc.chem.save(path,{'status':'PASS','combined_score':reward,'official':{'score':100/reward}});results.append({'status':'PASS','reward':reward,'receipt':str(path)})
        m=rc.chem.read(run/'pilot.json');m.update(status='completed',results=results);rc.chem.save(run/'pilot.json',m)
    for name in rc.NAMES:
        run=tmp_path/f'initial-{name}';rc.chem.prepared.initialize(run);finish(run,name,2);initial[name]=str(run)
    rc.chem.save(c/'campaign.json',{'initial_runs':initial})
    monkeypatch.setattr(rc.chem,'live',lambda run,meta:False)
    def launch(run,name):finish(run,name,3);return 123
    monkeypatch.setattr(rc.chem,'launch',launch);monkeypatch.setenv('DQI_INDEPENDENT_BRANCHES','1')
    old_eval=runner.evaluate_node;old_run=ClaudeAgent.run
    problem=tmp_path/'problem.txt';problem.write_text('Synthetic chemistry task');ev=tmp_path/'evaluate.py';ev.write_text('def evaluate(path):return {"combined_score":1}\n');program=tmp_path/'program.py';program.write_text('VALUE=1\n')
    try:
        rc.install(c)
        result=main(['explore','run','-w',str(c/'workspace'),'-a','claude','--policy-source','baseline','--branches','3','--refine','1','--max-workers','3','--problem',str(problem),'--evaluator',str(ev),'--init-program',str(program),'--eval-program','artifact/program.py'])
        assert result==0
        nodes=rc.chem.read(c/'workspace/raw_scores.json')['nodes'];assert len(nodes)==6
        assert sorted(n['raw']['combined_score'] for n in nodes)==[2,2,2,3,3,3]
        for name in rc.NAMES:
            run=c/'branches'/name/f'{name}_round_0002';m=rc.chem.read(run/'pilot.json');assert m['parent_actual_reward']==2 and not m['conversation_memory']
        from dream_rsi.learning.pipeline import run_learning
        assert run_learning(c/'workspace').parallel_refine.ok
    finally:runner.evaluate_node=old_eval;ClaudeAgent.run=old_run
