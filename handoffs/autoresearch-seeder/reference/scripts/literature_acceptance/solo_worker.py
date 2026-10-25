"""Isolated single-pilot validator with read-only own-artifact imports."""
import functools,hashlib,json,shutil,sys,tempfile,shlex
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(Path(__file__).parent))
import candidate_validation as cv
import artifact_bundle

if __name__=='__main__':
    attempt=Path(sys.argv[1]).absolute();cache=attempt.parent/'research'
    cv.dqi.PYTHON=ROOT/'.dqi-acceptance-venv/bin/python';original=cv.dqi.candidate_profile
    with tempfile.TemporaryDirectory(prefix='solo-artifact-') as temp:
        bundle=Path(temp);manifest=artifact_bundle.snapshot(attempt,bundle)
        def profile(job,output,extra_reads=()):
            if (job/'program.py').exists() or (job/'diagnostic.py').exists():
                shutil.copytree(bundle,job/'candidate',dirs_exist_ok=True)
                research=job/'research';research.mkdir(exist_ok=True)
                for source in cache.glob('*'):
                    if source.is_symlink():raise ValueError('Research links rejected')
                    if source.is_dir() and not source.name.startswith('.'):
                        if any(p.is_symlink() for p in source.rglob('*')):raise ValueError('Research links rejected')
                        shutil.copytree(source,research/source.name,dirs_exist_ok=True)
                entry=job/'run_candidate.py'
                paths="import sys\nfrom pathlib import Path\np=Path(__file__).parent\nsys.path[:0]=[str(p/'candidate')]+[str(x) for x in (p/'research').iterdir() if x.is_dir()]\n"
                if integration:paths+='sys.path.insert(1,'+repr(str(attempt.parent/'dependencies'))+')\n'
                entry.write_text(paths+entry.read_text())
            return original(job,output,extra_reads).replace(str((ROOT/'.dqi-venv').resolve()),str((ROOT/'.dqi-acceptance-venv').resolve()))
        cv.dqi.candidate_profile=profile
        if '--held-out' in sys.argv:
            evaluate=cv.dqi.evaluate_program
            def held(*args,**kwargs):kwargs['salt']='solo-literature-held-out-v1';return evaluate(*args,**kwargs)
            cv.dqi.evaluate_program=held
        integration='--integration' in sys.argv
        if integration:
            original_diagnose=cv.diagnose
            metadata=attempt.parents[2]/'pilot.json'
            meta=json.loads(metadata.read_text()) if metadata.exists() else {}
            provider=meta.get('provider','glm');values={}
            for line in (ROOT/'.credentials'/{'glm':'glm.env','minimax':'minimax.env','kimi_proxy':'kimi-proxy.env','luna_proxy':'kimi-proxy.env'}[provider]).read_text().splitlines():
                line=line.removeprefix('export ').strip()
                if '=' in line and not line.startswith('#'):
                    key,value=line.split('=',1);parts=shlex.split(value)
                    if len(parts)==1:values[key]=parts[0]
            token=values.get('ANTHROPIC_AUTH_TOKEN','')
            if provider=='glm':
                keys=[token]+[v.strip() for v in (ROOT/'.credentials/glm-keys.txt').read_text().splitlines() if v.strip() and not v.startswith('#')]
                keys=list(dict.fromkeys(keys));token=keys[meta.get('key_slot',0)]
            credentials={'ANTHROPIC_AUTH_TOKEN':token,'ANTHROPIC_BASE_URL':values['ANTHROPIC_BASE_URL'],'ANTHROPIC_MODEL':meta.get('worker_model',values['ANTHROPIC_MODEL']),'PIP_TARGET':str(attempt.parent/'dependencies'),'PIP_DISABLE_PIP_VERSION_CHECK':'1'}
            def long_test(source,output):
                destination=attempt.parent/'test-results'/output.parent.name
                return original_diagnose(source,output,timeout=600,memory_gib=10,persist_directory=destination,workspace=attempt.parent,allow_network=True,extra_env=credentials)
            cv.diagnose=long_test
        result=cv.validate(attempt,diagnostic=integration or '--diagnostic' in sys.argv)
        result['test_mode']='integration' if integration else ('quick' if '--diagnostic' in sys.argv else 'official_validation')
        result['artifact_bundle']=manifest
        result['artifact_bundle_sha256']=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
        print(json.dumps(result))
