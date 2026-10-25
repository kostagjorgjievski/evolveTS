"""Private acceptance validator: clean interpreter and public research cache only."""
import sys,json,shutil,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import candidate_validation as cv
cv.dqi.PYTHON=ROOT/'.dqi-acceptance-venv/bin/python'
original_profile=cv.dqi.candidate_profile
attempt=Path(sys.argv[1]);cache=attempt.parent/'research'
def profile(job,output,extra_reads=()):
    if (job/'program.py').exists() or (job/'diagnostic.py').exists():
        target=job/'research'
        if not target.exists():
            target.mkdir()
            for source in cache.glob('*'):
                if source.name.startswith('.'):continue
                if source.is_symlink():raise ValueError('Research links rejected')
                if source.is_dir():shutil.copytree(source,target/source.name,symlinks=False)
            entry=job/'run_candidate.py'
            if entry.exists():
                entry.write_text("import sys\nfrom pathlib import Path\nsys.path[:0]=[str(p) for p in (Path(__file__).parent/'research').iterdir() if p.is_dir() and p.name!='handed_public_sources']\n"+entry.read_text())
    return original_profile(job,output,extra_reads).replace(str((ROOT/'.dqi-venv').resolve()),str((ROOT/'.dqi-acceptance-venv').resolve()))
cv.dqi.candidate_profile=profile
if '--held-out' in sys.argv:
 original_evaluate=cv.dqi.evaluate_program
 def held_out(*a,**kw):
  kw['salt']='literature-reproduction-acceptance-held-out-v1'
  return original_evaluate(*a,**kw)
 cv.dqi.evaluate_program=held_out
print(json.dumps(cv.validate(attempt,diagnostic='--diagnostic' in sys.argv)))
