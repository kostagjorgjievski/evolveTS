"""Opt-in DQI E0 scheduling: refill a worker when its branch finishes evaluation."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path
import os
import threading

from dream_rsi.policy.baseline import ParallelRefineMethod
from dream_rsi.policy.api import SimResult, _record_curve, finalize_result
from dream_rsi.exploration import runner

E0_ROOT=Path(__file__).resolve().parents[1]/"runs/dqi/e0"
original_solve=ParallelRefineMethod.solve
metadata_lock=threading.RLock()


def drive(ready, execute, completed, *, workers, budget=None, started=lambda cell:None):
    """Only the controller mutates search state; workers execute isolated nodes."""
    pending={};submitted=0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while True:
            for cell in ready(set(pending.values())):
                if len(pending)>=workers or (budget is not None and submitted>=budget):break
                started(cell)
                pending[pool.submit(execute,cell)]=cell;submitted+=1
            if not pending:break
            finished,_=wait(pending,return_when=FIRST_COMPLETED)
            for future in finished:
                cell=pending.pop(future)
                completed(cell,future)


def solve(self,q,budget=None):
    root=E0_ROOT
    if not (os.environ.get('DQI_INDEPENDENT_BRANCHES')=='1' and q.mode=='live'
            and q.workspace and q.workspace.is_relative_to(root)):
        return original_solve(self,q,budget)
    q.reset();result=SimResult();store=runner.NodeStore(q.workspace)
    events={}
    def ready(inflight):
        busy={q.meta(c).branch for c in inflight}
        candidates=sorted((c for c in q.legal_actions() if c not in inflight
            and q.meta(c).branch not in busy and q.meta(c).attempt<=self.max_refine
            and (self.max_width is None or q.meta(c).branch<self.max_width)),
            key=lambda c:(q.meta(c).attempt,q.meta(c).branch))
        return candidates
    def started(cell):
        events[cell]=q._begin_execution_event([cell]);q._record_batch([cell])
    def execute(cell):
        if q.live_executor is not None:q.live_executor(q,cell)
        else:q._run_one_cell(store,cell)
    def completed(cell,future):
        try:future.result()
        except Exception as exc:
            store.mark_failed(cell,str(exc))
        with metadata_lock:
            runner.sync(q.workspace)
            q.store.refresh_from_workspace(q.workspace);q.store.flush();q._reload_trace()
        event=events.pop(cell)
        observation=q._reveal(cell)
        q._finish_execution_event(event,[q._execution_outcome(observation)])
        _record_curve(result,q)
        print(f'[independent-branches] completed {cell}; score={observation.score}; refilling available worker',flush=True)
    print('[independent-branches] enabled; each branch advances after its own evaluation; final cycle barrier retained',flush=True)
    drive(ready,execute,completed,workers=max(1,q.max_workers or q.max_parallelism),budget=budget,started=started)
    return finalize_result(q,result)


# Sync scans metadata while other nodes finish. Serialize its short reads with
# upstream metadata writes and restoration; never hold this lock during an agent/eval.
original_write=runner.NodeStore._write_meta
original_restore=runner._restore_meta_if_tampered

def write_meta(self,*args,**kwargs):
    with metadata_lock:return original_write(self,*args,**kwargs)

def restore(*args,**kwargs):
    with metadata_lock:return original_restore(*args,**kwargs)

runner.NodeStore._write_meta=write_meta
runner._restore_meta_if_tampered=restore
ParallelRefineMethod.solve=solve
