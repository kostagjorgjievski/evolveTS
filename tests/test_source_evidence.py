import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.autoresearch_seeder.store import ResearchStore
from scripts.autoresearch_seeder import scout_quality as q
from scripts.autoresearch_seeder.source_evidence import assess,verify_spans,require_review
from scripts.autoresearch_seeder.tools import ToolDispatcher


def make(tmp_path,body=b'def decode(syndrome):\n    return continued_fraction(syndrome)\n'):
    job=tmp_path/'job';store=ResearchStore(job/'private/research.sqlite');cache=job/'sources';cache.mkdir()
    p=cache/'source.bin';p.write_bytes(body);url='https://example.org/original'
    store.record_source({'url':url,'local_path':str(p),'status':'accessed','content_sha256':hashlib.sha256(body).hexdigest()})
    store.record_hypothesis({'id':'h','source_urls':[url]})
    args={k:'explicit '+k for k in q.TEXT_FIELDS};args.update(hypothesis_id='h',mechanism='continued fraction decoder',
        evidence_spans=[{'source_url':url,'quote':'def decode(syndrome): return continued_fraction(syndrome)','claim':'decoder uses continued fractions'}])
    return job,store,args,p,url


def review(s,p,url,outcome='accepted_for_test'):
    s.event('research_role',{'role':'reproducer'})
    return q.review(s,{'fingerprint':p['fingerprint'],'outcome':outcome,'source_urls':[url],
        'mistakes':[],'first_test':'compare against reference','next_action':'implement'})


def test_fabricated_quote_and_tampered_cache_refused(tmp_path):
    job,s,a,p,url=make(tmp_path)
    with pytest.raises(ValueError,match='not found'):q.packet(s,{**a,'evidence_spans':[{'source_url':url,'quote':'fabricated source says this is dramatically faster','claim':'faster'}]},'dqi')
    p.write_text('tampered bytes')
    with pytest.raises(ValueError,match='hash mismatch'):q.packet(s,a,'dqi')
    s.close()


def test_javascript_shell_is_retrieval_failure_not_host_block(tmp_path):
    body=b'<!doctype html><html><body><div id="root"></div><script src="app.js"></script></body></html>'
    job,s,a,p,url=make(tmp_path,body)
    a['evidence_spans'][0]['quote']='<div id="root"></div><script src="app.js">'
    with pytest.raises(ValueError,match='Unusable research'):q.packet(s,a,'dqi')
    assert s.get_source(url)['status']=='accessed' # Raw receipt preserved; no host/auth inference.
    assert assess(b'Brief but legitimate README.')['status']=='reviewable'
    s.close()


def test_notebook_source_is_decoded_before_matching(tmp_path):
    body=json.dumps({'cells':[{'cell_type':'code','source':['def decode(syndrome):\n','    return continued_fraction(syndrome)']}]}).encode()
    job,s,a,p,url=make(tmp_path,body)
    assert q.packet(s,a,'dqi')['verified_spans'][0]['file_sha256']==hashlib.sha256(body).hexdigest();s.close()


def test_role_missing_fails_closed_and_review_is_mandatory(tmp_path):
    job,s,a,p,url=make(tmp_path);packet=q.packet(s,a,'dqi')
    with pytest.raises(ValueError,match='Independent reproducer'):q.review(s,{'fingerprint':packet['fingerprint']})
    d=ToolDispatcher(s,SimpleNamespace(task_id='dqi'),{'research':{'require_evidence_review':True}},job)
    before=d.execute('write_candidate_file',{'path':'worker/attempt_00/artifact/program.py','content':'implementation'})
    assert before['status']=='error'
    assert d.execute('write_candidate_file',{'path':'worker/attempt_00/artifact/diagnostic.py','content':'print(1)'})['status']=='ok'
    s.event('research_role',{'role':'reproducer'})
    assert d.execute('run_development_validation',{})['status']=='error'
    review(s,packet,url);require_review(s)
    assert d.execute('write_candidate_file',{'path':'worker/attempt_00/artifact/program.py','content':'implementation'})['status']=='ok'
    s.close()


def test_changed_packet_or_source_invalidates_review(tmp_path):
    job,s,a,p,url=make(tmp_path);packet=q.packet(s,a,'dqi');review(s,packet,url)
    q.packet(s,{**a,'first_test':'different first experiment'},'dqi')
    with pytest.raises(ValueError,match='this exact packet'):require_review(s)
    p.write_text('different source')
    with pytest.raises(ValueError,match='hash mismatch'):require_review(s)
    s.close()


def test_repository_member_pinned_to_manifest(tmp_path):
    job,s,a,p,url=make(tmp_path);repo=job/'sources/repo';repo.mkdir();code=repo/'decoder.py';code.write_bytes(p.read_bytes())
    manifest={'commit':'a'*40,'files':[{'path':'decoder.py','sha256':hashlib.sha256(code.read_bytes()).hexdigest()}]}
    index=repo/'SOURCE_MANIFEST.json';index.write_text(json.dumps(manifest))
    s.record_source({'url':url,'local_path':str(repo),'status':'accessed','content_sha256':hashlib.sha256(index.read_bytes()).hexdigest()})
    a['evidence_spans'][0]['relative_path']='decoder.py'
    assert q.packet(s,a,'dqi')['verified_spans']
    code.write_text('changed')
    with pytest.raises(ValueError,match='hash mismatch'):q.packet(s,a,'dqi')
    s.close()


def test_outside_cache_and_unlisted_repo_path_refused(tmp_path):
    job,s,a,p,url=make(tmp_path);outside=tmp_path/'outside';outside.write_bytes(p.read_bytes())
    s.record_source({'url':url,'local_path':str(outside),'status':'accessed','content_sha256':hashlib.sha256(outside.read_bytes()).hexdigest()})
    with pytest.raises(ValueError,match='fetched cache'):q.packet(s,a,'dqi')
    s.close()


def test_legacy_deferred_request_cannot_bypass_review_gate(tmp_path):
    from scripts.autoresearch_seeder.testing import build_job
    from scripts.autoresearch_seeder.models import bundle_hash
    from scripts.autoresearch_seeder.publisher import evaluate_gates
    c=build_job(tmp_path,[],overrides={'research':{'require_evidence_review':True},'validation':{'deferred_development':True}})
    c.store.event('development_requested',{'input_bundle_sha256':bundle_hash(c.dispatcher.artifact)})
    c.save_job(stage='implementing');c._post_session()
    assert c.job_state()['stage']=='compatibility_test'
    c._post_session() # Remains parked rather than cycling states or consuming full grading.
    assert not c.store.list_experiments('development_validation')
    assert any('Evidence review required' in reason for reason in evaluate_gates(c)['reasons'])
    c.store.close()


def test_packet_precheck_reports_exact_field_without_advancing(tmp_path):
    job,s,a,p,url=make(tmp_path)
    broken={**a,'evidence_spans':[{**a['evidence_spans'][0],'relative_path':'source.py'}]}
    checked=q.check_packet(s,broken,'dqi')
    assert not checked['ok']
    assert checked['issues'][0]['field']=='evidence_spans[0]'
    assert checked['issues'][0]['cached_path']==str(p)
    assert 'omit relative_path' in checked['issues'][0]['citation_format']
    assert not s.list_events('scout_packet')
    assert q.check_packet(s,a,'dqi')['ok']
    assert not s.list_events('scout_packet')
    s.close()


def test_draft_survives_reopen_but_does_not_qualify_for_review(tmp_path):
    job,s,a,p,url=make(tmp_path)
    dispatcher=ToolDispatcher(s,SimpleNamespace(task_id='dqi'),{},job)
    assert dispatcher.execute('save_scout_draft',{'draft':a})['result']['eligible'] is False
    s.close();s=ResearchStore(job/'private/research.sqlite')
    assert json.loads((job/'worker/scout-draft.json').read_text())==a
    assert s.list_events('scout_draft') and not s.list_events('scout_packet')
    s.event('research_role',{'role':'reproducer'})
    with pytest.raises(ValueError,match='scout packet'):require_review(s)
    s.close()


def test_packet_error_feedback_persists_and_repair_still_needs_review(tmp_path):
    job,s,a,p,url=make(tmp_path)
    d=ToolDispatcher(s,SimpleNamespace(task_id='dqi'),{},job)
    bad={**a,'evidence_spans':[{**a['evidence_spans'][0],'quote':'a fabricated quotation that is not present'}]}
    result=d.execute('record_scout_packet',bad)
    assert result['status']=='error' and result['scout_issue']['issues']
    assert q.pending_issues(s)
    assert d.execute('record_scout_packet',a)['status']=='ok'
    assert not q.pending_issues(s)
    s.event('research_role',{'role':'reproducer'})
    with pytest.raises(ValueError,match='Independent reproducer review'):require_review(s)
    s.close()
