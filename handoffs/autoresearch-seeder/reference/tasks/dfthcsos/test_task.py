"""Reward boundaries, Kaggle preflight parity, and real Mac sandbox isolation."""
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('dfthcsos_task_adapter',HERE/'evaluator.py')
adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
spec=importlib.util.spec_from_file_location('dfthcsos_metric_preflight',HERE/'metric_preflight.py')
preflight=importlib.util.module_from_spec(spec);spec.loader.exec_module(preflight)


def test_reward_requires_full_official_workload(monkeypatch):
    monkeypatch.setitem(adapter.PROTOCOL,'reference_cost',100.)
    good={'official':{'status':'PASS','score':50.,'verified_shots':254464},
          'validation':{'shots_per_address':64,'expected_shots':254464,'metric_preflight':True}}
    assert adapter.score_result(good)['combined_score']==2
    for mutate in [lambda d:d['official'].update(score=float('nan')),
                   lambda d:d['official'].update(verified_shots=1),
                   lambda d:d['validation'].update(shots_per_address=1),
                   lambda d:d['validation'].update(metric_preflight=False)]:
        bad=json.loads(json.dumps(good));mutate(bad)
        with pytest.raises(ValueError):adapter.score_result(bad)
    smoke={'official':{'status':'PASS','score':50.,'verified_shots':3976},
           'validation':{'shots_per_address':1,'expected_shots':3976,'metric_preflight':True}}
    assert 'combined_score' not in adapter.score_result(smoke,smoke=True)


def test_original_metric_reader_rejects_object_and_wrong_dimensions(tmp_path):
    _,reader=preflight.readers(adapter.METRIC)
    file=tmp_path/'submission.npz'
    np.savez(file,x=np.array([{'bad':'object'}],dtype=object))
    with pytest.raises(ValueError,match='dtype'):reader(file,{'x':('f',('R',))})
    np.savez(file,x=np.zeros((2,3)),y=np.zeros((4,)))
    with pytest.raises(ValueError,match='shape'):reader(file,{'x':('f',('R',3)),'y':('f',('R',))})
    np.savez(file,x=np.zeros((2,3)),y=np.zeros((2,)))
    assert reader(file,{'x':('f',('R',3)),'y':('f',('R',))})['x'].shape==(2,3)


def test_submission_freeze_rejects_links(tmp_path):
    source=tmp_path/'source';source.mkdir();(source/'submission.npz').write_bytes(b'npz')
    outside=tmp_path/'outside';outside.write_bytes(b'circuit');(source/'angle_k_0.kmb').symlink_to(outside)
    with pytest.raises(ValueError,match='links'):adapter.copy_submission(source,tmp_path/'frozen')


@pytest.mark.skipif(sys.platform!='darwin',reason='Mac isolation')
def test_sandbox_has_helpers_without_secrets_network_or_source_writes(tmp_path):
    job=tmp_path/'job';job.mkdir();out=job/'output';out.mkdir();secret=tmp_path/'secret';secret.write_text('private')
    protected=job/'protected';protected.write_text('intact')
    program=job/'probe.py'
    program.write_text(f'''import os,socket
import dfthcsos,kickmix,numpy,scipy
assert 'ANTHROPIC_AUTH_TOKEN' not in os.environ
for path,mode in [({str(secret)!r},'r'),({str(protected)!r},'w')]:
    try:open(path,mode)
    except PermissionError:pass
    else:raise AssertionError('sandbox file access unexpectedly allowed')
try:socket.create_connection(('1.1.1.1',443),timeout=1)
except PermissionError:pass
else:raise AssertionError('network unexpectedly allowed')
open({str(out/'ok.txt')!r},'w').write('ok')
print('sandbox passed')
''')
    profile=job/'sandbox.sb';profile.write_text(adapter.profile(job,out))
    text=adapter.run_process(['/usr/bin/sandbox-exec','-f',str(profile),str(adapter.PYTHON),'-I',str(program)],job,adapter.clean_environment(out),30,memory_gib=2)
    assert 'sandbox passed' in text and protected.read_text()=='intact' and (out/'ok.txt').read_text()=='ok'
