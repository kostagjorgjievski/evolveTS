import asyncio,importlib.util,json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('advisor',ROOT/'scripts/library_rsi/advisor.py')
advisor=importlib.util.module_from_spec(spec);spec.loader.exec_module(advisor)

@pytest.fixture
def run(tmp_path):
    lib=tmp_path/'library';lib.mkdir()
    (lib/'index.json').write_text(json.dumps({'methods':[{'id':'runtime-mask','revision':'abc','file':'runtime-mask.json'}]}))
    (lib/'runtime-mask.json').write_text(json.dumps({'id':'runtime-mask','mechanism':'runtime mask field transport'}))
    return tmp_path

def test_question_identity_cache_and_branch_isolation(run):
    first=advisor.submit(run,'branch-0','How do I map runtime masks?')
    assert advisor.submit(run,'branch-0',first['question'])['id']==first['id']
    assert advisor.submit(run,'branch-1',first['question'])['id']!=first['id']
    assert first['retrieved'][0]['revision']=='abc'
    assert first['retrieved'][0]['method']['id']=='runtime-mask'
    (run/'library/index.json').write_text(json.dumps({'methods':[]}))
    assert advisor.submit(run,'branch-0',first['question'])['id']!=first['id']

def test_pending_answer_then_cached_reply(run):
    async def check():
        pending=await advisor.ask(run,'branch-0','Field question',timeout=0)
        assert pending['status']=='pending' and pending['retrieved']
        answer=run/'advisor/questions'/(pending['question_id']+'.answer.json')
        answer.write_text(json.dumps({'question_id':pending['question_id'],'decision':'pivot','directions':[]}))
        result=await advisor.ask(run,'branch-0','Field question',timeout=1)
        assert result['status']=='answered' and result['advice']['decision']=='pivot'
    asyncio.run(check())

def test_rejects_invalid_questions(run):
    for question in ('',None,'a'*12001):
        with pytest.raises(ValueError):advisor.submit(run,'branch-0',question)

def test_wrong_answer_identity_is_not_returned(run):
    q=advisor.submit(run,'branch-0','A question')
    (run/'advisor/questions'/(q['id']+'.answer.json')).write_text(json.dumps({'question_id':'other'}))
    with pytest.raises(ValueError,match='identity'):asyncio.run(advisor.ask(run,'branch-0','A question',timeout=1))
