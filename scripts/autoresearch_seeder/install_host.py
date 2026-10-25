"""Install the opt-in, fail-open preparation hook without replacing host code."""
import argparse
import hashlib
import json
from pathlib import Path

from . import ROOT
from .models import atomic_write, utc

WRAPPER = '''

# Hermes R&D integration: future prepared attempts only; no model call here.
def attach(run, branch, prompt):
    prompt = _attach_own_memory(run, branch, prompt)
    config_path = ROOT / 'configs/hosts/hermes_bridge.json'
    if not config_path.is_file(): return prompt
    try:
        import importlib.util, sys
        cfg = json.loads(config_path.read_text())
        if not cfg.get('enabled'): return prompt
        package = Path(cfg['package_root']) / 'scripts/autoresearch_seeder'
        name = '_hermes_research_live'
        if name not in sys.modules:
            spec = importlib.util.spec_from_file_location(name, package / '__init__.py', submodule_search_locations=[str(package)])
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        from _hermes_research_live.host_hook import prepare
        return prepare(run, branch, prompt, config_path)
    except Exception as error:
        private = Path(run) / 'private'
        private.mkdir(exist_ok=True)
        (private / 'hermes-hook-error.json').write_text(json.dumps({'class': type(error).__name__, 'action':'attempt proceeds without research advice'}))
        return prompt
'''


def install(host_root, research_root, campaign, package_root=ROOT):
    host_root=Path(host_root).resolve()
    module=host_root/'scripts/literature_acceptance/experimental_memory.py'
    original=module.read_text()
    if 'def _attach_own_memory(' not in original:
        if original.count('def attach(run,branch,prompt):') != 1:
            raise ValueError('Unexpected host memory hook; refusing automatic edit')
        updated=original.replace('def attach(run,branch,prompt):','def _attach_own_memory(run,branch,prompt):',1)+WRAPPER
        compile(updated,str(module),'exec')
        backup=host_root/'work/hermes-install/experimental_memory.before.py'
        backup.parent.mkdir(parents=True,exist_ok=True)
        if not backup.exists():backup.write_text(original)
        atomic_write(module,updated)
    else:updated=original
    campaign=Path(campaign).resolve()
    task=json.loads((campaign/'campaign.json').read_text())['task']
    config={'enabled':True,'package_root':str(Path(package_root).resolve()),
            'knowledge_roots':{task:str(Path(research_root).resolve())},
            'campaigns':[str(campaign)],'enabled_utc':utc(),
            'mode':'frozen advice at future attempt boundaries; no automatic parent replacement'}
    path=host_root/'configs/hosts/hermes_bridge.json';path.parent.mkdir(parents=True,exist_ok=True)
    atomic_write(path,json.dumps(config,indent=2))
    audit=host_root/'work/hermes-install/receipt.json'
    atomic_write(audit,json.dumps({'utc':utc(),'host_module':str(module),
        'before_sha256':hashlib.sha256(original.encode()).hexdigest(),
        'after_sha256':hashlib.sha256(updated.encode()).hexdigest(),
        'configuration':str(path),'active_attempts_changed':False},indent=2))
    return {'installed':True,'receipt':str(audit),'config':str(path)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--host-root',required=True)
    parser.add_argument('--research-root',required=True)
    parser.add_argument('--campaign',required=True)
    args=parser.parse_args()
    print(json.dumps(install(args.host_root,args.research_root,args.campaign),indent=2))


if __name__=='__main__':main()
