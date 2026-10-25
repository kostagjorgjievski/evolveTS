"""Chemistry prepared-context workers inside the actual upstream DreamRSI engine."""
import json,os,shutil,sys,time
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'scripts/literature_acceptance'),str(Path(__file__).parent)]
import importlib.util
_spec=importlib.util.spec_from_file_location('chemistry_chain_helpers',Path(__file__).with_name('supervise.py'))
chem=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(chem)
NAMES=['opus','kimi','gpt','glm']

def learning(kwargs):
    from dream_rsi.agents.codex import CodexAgent
    import run_worker
    cfg=run_worker.environment(ROOT/'.credentials/kimi-proxy.env')
    os.environ['CHEMISTRY_DREAM_PROVIDER_KEY']=cfg['ANTHROPIC_AUTH_TOKEN']
    settings={'model_provider':'chemistry_dream','model_reasoning_effort':'medium','approval_policy':'never','model_providers.chemistry_dream.name':'Chemistry dreaming provider','model_providers.chemistry_dream.base_url':'https://yyt.s-flag.com/v1','model_providers.chemistry_dream.env_key':'CHEMISTRY_DREAM_PROVIDER_KEY','model_providers.chemistry_dream.wire_api':'responses'}
    class NativeLearning(CodexAgent):
        def _build_command(self,workspace,prompt,last_message):
            command=[str(Path.home()/'.local/bin/codex'),'exec','--ignore-user-config','--ephemeral','--skip-git-repo-check','--json','-s','workspace-write','-C',str(workspace),'-m','gpt-6.1-sol']
            for k,v in settings.items():command+=['-c',k+'='+json.dumps(v)]
            return command+['-o',str(last_message),prompt]
    kwargs['prompt']+='\nUse only this chemistry campaign replay and full framework at '+str(ROOT/'upstream/dream-rsi')+'. Evaluate policies with the unchanged replay objective. No candidate algorithm edits or other campaigns. This is medium-effort native Codex policy discovery.\n'
    return NativeLearning(model='gpt-6.1-sol',timeout_sec=3600).run(**kwargs)

def install(campaign):
    from dream_rsi.agents.claude import ClaudeAgent
    from dream_rsi.agents.base import AgentResult
    from dream_rsi.exploration import runner
    import independent_branches
    independent_branches.E0_ROOT=campaign/'workspace'
    cfg=chem.read(campaign/'campaign.json');original_eval=runner.evaluate_node
    def evaluate(node,conf):
        p=node/'controller-result.json'
        if not p.exists():return original_eval(node,conf)
        result=chem.read(p);chem.save(node/'eval/score.json',result);return result
    runner.evaluate_node=evaluate
    def agent_run(self,**kwargs):
        if kwargs.get('stage')!='explore':return learning(kwargs)
        node=Path(kwargs['node_dir']);branch=int(node.parent.name.removeprefix('explore_b'));index=int(node.name.split('_')[1]);name=NAMES[branch]
        if index==0:run=Path(cfg['initial_runs'][name])
        else:
            run=chem.worker_path(campaign,name,index+1)
            if not run.exists():
                run=chem.new_attempt(campaign,name,index+1)
                parent_id=chem.read(node/'meta.json')['parent_id'];parent=runner.NodeStore(kwargs['workspace']).get_node_dir(parent_id)
                artifact=run/'worker/explore_b0/attempt_00/artifact';shutil.rmtree(artifact);shutil.copytree(parent/'artifact',artifact)
                score=chem.read(parent/'eval/score.json');chem.save(run/'worker/explore_b0/parent-result.json',{'development':score,'confirmation':score.get('campaign_confirmation'),'parent':'own immediate RSI parent','parent_node':parent_id})
                m=chem.read(run/'pilot.json');m.update(parent_node=parent_id,parent_actual_reward=score['combined_score'],experiment='chemistry_RSI_E0_prepared');chem.save(run/'pilot.json',m)
        meta=chem.read(run/'pilot.json')
        if meta.get('requires_preflight'):
            while True:
                report=run/'private/codex-preflight.json'
                if report.exists() and chem.read(report).get('status')=='PASS':break
                chem.save(node/'worker.json',{'run':str(run),'context':'prepared_fresh','status':'waiting_for_real_diagnostic_preflight','model':meta['worker_model']})
                time.sleep(5)
        if chem.live(run,meta):
            chem.save(node/'worker.json',{'run':str(run),'pid':meta['pid'],'reattached':True,'context':'prepared_fresh','model':meta['worker_model']})
            while chem.live(run,chem.read(run/'pilot.json')):time.sleep(5)
        elif meta.get('status') not in ['completed','validation_failed']:
            while meta.get('status') not in ['prepared','starting','completed','validation_failed']:
                chem.save(node/'infrastructure-blocked.json',{'run':str(run),'status':meta.get('status'),'action':'Wait for recovery; do not count an infrastructure failure as a scored attempt'})
                time.sleep(10);meta=chem.read(run/'pilot.json')
            pid=chem.launch(run,name);chem.save(node/'worker.json',{'run':str(run),'pid':pid,'context':'prepared_fresh','model':meta['worker_model']})
            while chem.live(run,chem.read(run/'pilot.json')):time.sleep(5)
        meta=chem.read(run/'pilot.json')
        while meta.get('status') not in ['completed','validation_failed']:
            chem.save(node/'infrastructure-blocked.json',{'run':str(run),'status':meta.get('status'),'error':meta.get('worker_error'),'action':'Preserve this node; no scoring or advancement until runner recovery'})
            time.sleep(10);meta=chem.read(run/'pilot.json')
        results=meta.get('results',[])
        if len(results)==2 and all(x.get('status')=='PASS' for x in results):
            a=chem.read(results[0]['receipt']);b=chem.read(results[1]['receipt']);result=dict(a);result['campaign_confirmation']={'status':b['status'],'combined_score':b['combined_score'],'receipt':results[1]['receipt']}
        else:result={'combined_score':0,'status':'FAIL','error':'Worker did not pass both complete final checks','results':results}
        chem.save(node/'controller-result.json',result)
        shutil.copytree(run/'worker/explore_b0/attempt_00/artifact',node/'artifact',dirs_exist_ok=True)
        proposal=run/'worker/explore_b0/attempt_00/proposal.md';(node/'proposal.md').write_text(proposal.read_text() if proposal.exists() else 'Worker ended without proposal; full receipts in controller-result.json.')
        return AgentResult(message='Prepared chemistry node and unchanged full final grading complete')
    ClaudeAgent.run=agent_run

if __name__=='__main__':
    campaign=Path(sys.argv[1]).resolve();install(campaign)
    from dream_rsi.cli.main import main
    raise SystemExit(main(sys.argv[2:]))
