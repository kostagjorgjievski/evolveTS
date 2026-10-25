"""Persist asynchronous test status and stop the researcher when worker work ends."""
import sys,time,json,datetime
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parents[2];run=Path(sys.argv[1]);pid=int(sys.argv[2]);private=run/'private'
while True:
    status_path=private/'status.json';status=json.loads(status_path.read_text()) if status_path.exists() else {}
    gate_path=private/'gate.json';gate=json.loads(gate_path.read_text()) if gate_path.exists() else None
    error_path=private/'controller-error.txt'
    alive=psutil.pid_exists(pid)
    if alive:
        try:alive=psutil.Process(pid).status()!=psutil.STATUS_ZOMBIE
        except psutil.Error:alive=False
    if status.get('status')=='worker_finished' or error_path.exists() or not alive:
        marker=private/'research-stop.json'
        if not marker.exists():marker.write_text(json.dumps({'stop':True,'reason':'worker session finished','utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}))
    state='grading' if status.get('status')=='worker_finished' else status.get('status','worker_starting')
    if gate:state=gate['status']
    elif error_path.exists() or not alive:state='infrastructure_error'
    active={'run':str(run),'pid':pid,'status':state,'worker_model':status.get('model'),'production_enabled':False,'log':str(private/'worker-controller.log'),'updated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    (run/'active.json').write_text(json.dumps(active,indent=2))
    default=ROOT/'runs/dqi-acceptance/active.json'
    try:current=json.loads(default.read_text())
    except (OSError,ValueError):current={}
    if current.get('run')==str(run):default.write_text(json.dumps(active,indent=2))
    if gate or error_path.exists() or not alive:
        active['gate']=gate
        if error_path.exists():active['error']=error_path.read_text()[-3000:]
        (run/'report.json').write_text(json.dumps(active,indent=2));break
    time.sleep(5)
