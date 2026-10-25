"""Run only the owning attempt's diagnostic.py in the task sandbox."""
import fcntl
import json
from pathlib import Path
import shutil
import tempfile
import time
import sys
import evaluator
sys.path.insert(0, str(evaluator.ROOT/'scripts'))
from runtime_queue import diagnostic_slot


def diagnose(attempt, timeout=60, memory_gib=2):
    attempt=Path(attempt).resolve();artifact=attempt/'artifact';started=time.monotonic()
    if not artifact.is_dir() or (artifact/'diagnostic.py').is_symlink():raise ValueError('Regular diagnostic.py required')
    evaluator.verify_sources();locks=evaluator.ROOT/'work/runtime-locks';locks.mkdir(parents=True,exist_ok=True)
    with diagnostic_slot(evaluator.ROOT, timeout, memory_gib):
        with tempfile.TemporaryDirectory(prefix='dfthcsos-diagnostic-') as temporary:
            job=Path(temporary);out=job/'output';out.mkdir();total=0;count=0
            for source in artifact.rglob('*'):
                if source.is_symlink():raise ValueError('Artifact links forbidden')
                if source.is_dir():continue
                if not source.is_file() or source.stat().st_nlink!=1:raise ValueError('Regular artifact files required')
                total+=source.stat().st_size;count+=1
                if total>128*2**20 or count>4096:raise ValueError('Artifact bundle too large')
                target=job/source.relative_to(artifact);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
            wrapper=job/'run_diagnostic.py'
            wrapper.write_text("import runpy,sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path(__file__).parent))\nrunpy.run_path(str(Path(__file__).parent/'diagnostic.py'),run_name='__main__')\n")
            sandbox=job/'diagnostic.sb';sandbox.write_text(evaluator.profile(job,out));env=evaluator.clean_environment(out);env['TEST_OUTPUT_DIR']=str(out)
            text=evaluator.run_process(['/usr/bin/sandbox-exec','-f',str(sandbox),str(evaluator.PYTHON),'-I',str(wrapper)],job,env,timeout,memory_gib=memory_gib,scratch_directory=out)
            return {'status':'PASS','diagnostic_only':True,'verified_score':None,'logs':{'diagnostic.log':text[-16000:]},'seconds':time.monotonic()-started,'development_cost':True}
