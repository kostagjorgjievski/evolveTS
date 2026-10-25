"""Standalone MiniMax seeder acceptance test; no production campaign insertion."""
import datetime,json,sys
from pathlib import Path
import dfthcsos_pilot as pilot
import dfthcsos_opus_prepared as prepared
ROOT=pilot.ROOT
MODEL='MiniMax-M3.1-Flash[1m]'
SEEDER_PROMPT='''This is a SEEDER ACCEPTANCE TEST, not an existing production branch.
Starting from the official baseline and neutral task/API preparation, independently
find literature, assess compatibility, implement and fully validate a better common
starting program for a future chemistry RSI campaign. No improved private seed,
research handoff, advisor, library or other worker's findings are supplied.

Compare at least two genuinely different mechanisms using primary sources and
cheap compatibility tests before committing the bulk of development to one route.
If the evidence favors one, proceed; do not manufacture diversity or spend the
whole allowance reviewing papers. Record rejected mechanisms and concrete reasons.
Write your research assessment and reproduction evidence in proposal.md. Distinguish
published claims, estimates, diagnostics and full verified results. A useful seeder
output is runnable improved source with provenance and actual passing verification,
not a plausible literature summary. Preserve a valid baseline fallback. Leave the
best actually verified source in artifact/program.py. All original task constraints,
isolation and unchanged verifier/scoring apply. This is exactly one200-minute test;
no permission to launch other agents or modify a production campaign is given.

'''

def initialize(run):
    meta=prepared.initialize(run)
    meta.update(provider='minimax',worker_model=MODEL,effort='medium',experiment='standalone_seeder_acceptance',status='prepared',seeder_test=True,production_enabled=False,success_criterion='reproducible reward>1 on both full unchanged official checks',harness='claude_code',literature_hints=False,known_solution_supplied=False)
    (run/'pilot.json').write_text(json.dumps(meta,indent=2)+'\n')

def work(run):
    pilot.PROMPT=SEEDER_PROMPT+pilot.PROMPT
    pilot.work(run,config_override=pilot.runner.environment(ROOT/'.credentials/minimax.env'))
    meta=json.loads((run/'pilot.json').read_text());results=meta.get('results',[])
    assessment={'model_requested':MODEL,'effort_requested':'medium','status':meta['status'],'verified_improvement':bool(meta.get('improved')),'full_final_results':results,'development_seconds':meta.get('session_seconds_used'),'production_changed':False,'source_bundle':str(run/'worker/explore_b0/attempt_00/artifact'),'research_report':str(run/'worker/explore_b0/attempt_00/proposal.md'),'cost_note':'SDK reported cost is retained as reported, not independently reconciled with provider billing.'}
    p=run/'private/sdk-events.jsonl';served=set();usage=[]
    if p.exists():
        for line in p.read_text().splitlines():
            event=json.loads(line);data=event.get('data',{})
            if event.get('type')=='AssistantMessage' and data.get('model'):served.add(data['model'])
            if event.get('type')=='ResultMessage':usage.append({k:data.get(k) for k in ['total_cost_usd','usage','model_usage','num_turns','duration_ms','is_error']})
    assessment.update(served_models=sorted(served),sdk_usage=usage)
    (run/'seeder-assessment.json').write_text(json.dumps(assessment,indent=2)+'\n')

if __name__=='__main__':
    run=Path(sys.argv[1]).resolve()
    if not run.is_relative_to(ROOT/'runs/dfthcsos'):raise ValueError('Chemistry test directory required')
    work(run)
