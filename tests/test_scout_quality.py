import json
import hashlib
from types import SimpleNamespace
import pytest
from scripts.autoresearch_seeder import scout_quality as q
from scripts.autoresearch_seeder.store import ResearchStore
from scripts.autoresearch_seeder.tools import ToolDispatcher


def setup(tmp_path):
    job=tmp_path/'jobs/autoresearch-seeder/dqi/inv-one'
    store=ResearchStore(job/'private/research.sqlite')
    source=job/'sources/original.txt';source.parent.mkdir();source.write_text('The original decoder uses a continued fraction to decode the syndrome.')
    store.record_source({'url':'https://example.org/original','status':'accessed','content_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'local_path':str(source),'license':'unknown'})
    store.record_hypothesis({'id':'h1','mechanism':'J fraction','source_urls':['https://example.org/original']})
    args={k:'specific '+k for k in q.TEXT_FIELDS}
    args.update(evidence_spans=[{'source_url':'https://example.org/original','quote':'decoder uses a continued fraction to decode the syndrome','claim':'continued fraction decoder'}],hypothesis_id='h1',mechanism='J fraction',dependency_urls=[],resource_estimates=[
        {'source_url':'https://example.org/original','Q':1837,'T':442397,'R':1},
        {'source_url':'https://example.org/original','Q':883,'T':996048,'R':1}])
    return job,store,args


def test_receipt_pins_ranking_and_noncertification(tmp_path):
    job,s,a=setup(tmp_path);p=q.packet(s,a,'dqi')
    assert p['resource_estimates'][0]['Q']==883 # fewer Toffolis loses when Q is squared
    assert p['citations'][0]['content_sha256']==hashlib.sha256((job/'sources/original.txt').read_bytes()).hexdigest()
    assert p['science_status']=='requires independent reproduction' and p['certification'] is False
    c=q.checkpoint(s,job,'scout');assert c['handoff_complete']
    s.close()


def test_unfetched_claim_and_missing_test_refused(tmp_path):
    job,s,a=setup(tmp_path)
    s.record_hypothesis({'id':'h2','source_urls':['https://made-up.invalid']})
    with pytest.raises(ValueError,match='fetched'):q.packet(s,{**a,'hypothesis_id':'h2'},'dqi')
    with pytest.raises(ValueError,match='first_test'):q.packet(s,{**a,'first_test':''},'dqi')
    assert not s.list_events('scout_packet');s.close()


def test_unknown_dependency_is_unresolved_not_account_block(tmp_path):
    job,s,a=setup(tmp_path);p=q.packet(s,{**a,'dependency_urls':['https://example.org/dependency']},'dqi')
    assert p['handoff_status']=='needs_dependency_recovery'
    assert not q.checkpoint(s,job,'scout')['handoff_complete'];s.close()


def test_duplicates_advisory_and_new_revision_distinct(tmp_path):
    job,s,a=setup(tmp_path);known=[{'record_id':'r1','mechanism':'other method','source_urls':['https://example.org/original']}]
    p=q.packet(s,a,'dqi',known);assert p['duplicate_candidates'] and not p['duplicate_packet']
    assert q.packet(s,a,'dqi',known)['duplicate_packet']
    source=job/'sources/original.txt';source.write_text(source.read_text()+' New revision.')
    s.record_source({'url':'https://example.org/original','status':'accessed','content_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'local_path':str(source)})
    assert not q.packet(s,a,'dqi',known)['duplicate_packet'];s.close()


@pytest.mark.parametrize('value',[float('nan'),float('inf'),-1,True])
def test_invalid_resource_arithmetic_refused(tmp_path,value):
    job,s,a=setup(tmp_path);a['resource_estimates'][0]['Q']=value
    with pytest.raises(ValueError):q.packet(s,a,'dqi')
    s.close()


def test_other_task_does_not_inherit_dqi_formula(tmp_path):
    job,s,a=setup(tmp_path)
    with pytest.raises(ValueError,match='only for DQI'):q.packet(s,a,'dfthcsos')
    s.close()


def test_dispatcher_packet_and_quality_metrics(tmp_path):
    job,s,a=setup(tmp_path)
    d=ToolDispatcher(s,SimpleNamespace(task_id='dqi'),{},job)
    r=d.execute('record_scout_packet',a);assert r['status']=='ok'
    assert json.loads((job/'worker/scout-packet.json').read_text())['hypothesis_id']=='h1'
    (job/'job.json').write_text('{}');s.event('scout_policy',{'version':q.VERSION});s.charge('model',seconds=10)
    s.event('provider_error',{'detail':'503'})
    m=q.metrics(tmp_path)['cohorts']['scout-v2'];assert m['ready_packets']==1 and m['model_seconds']==10 and m['provider_errors']==1
    s.close()


def test_missing_packet_and_no_private_paths_in_index(tmp_path):
    job,s,a=setup(tmp_path);assert q.checkpoint(s,job,'scout')['missing_packet']
    facts=[{'id':'public1','payload':{'hypotheses':[{'mechanism':'method','source_urls':['https://public.example']}], 'private_path':'/secret'}}]
    index=q.known_methods(facts);assert '/secret' not in json.dumps(index)
    assert index[0]['record_id']=='public1';s.close()


def test_independent_review_requires_existing_packet_and_sources(tmp_path):
    job,s,a=setup(tmp_path);p=q.packet(s,a,'dqi')
    review={'fingerprint':p['fingerprint'],'outcome':'corrected','source_urls':['https://example.org/original'],
            'mistakes':['Q was transcribed incorrectly'],'first_test':'recount Q','next_action':'run diagnostic'}
    s.event('research_role',{'role':'reproducer'})
    assert q.review(s,review)['officially_validated'] is False
    with pytest.raises(ValueError,match='Unknown packet'):q.review(s,{**review,'fingerprint':'fabricated'})
    (job/'job.json').write_text('{}');s.event('scout_policy',{'version':q.VERSION})
    m=q.metrics(tmp_path)['cohorts']['scout-v2'];assert m['reviews']==1 and m['review_corrections']==1
    s.close()


def test_scout_cannot_review_own_packet(tmp_path):
    job,s,a=setup(tmp_path);s.event('research_role',{'role':'scout'});p=q.packet(s,a,'dqi')
    assert p['recorded_role']=='scout'
    with pytest.raises(ValueError,match='Independent reproducer'):
        q.review(s,{'fingerprint':p['fingerprint'],'outcome':'accepted_for_test','source_urls':['https://example.org/original'],
                   'mistakes':[],'first_test':'test','next_action':'continue'})
    s.close()


def test_known_packet_hashes_detect_rehosted_source_without_exposing_paths(tmp_path):
    job,s,a=setup(tmp_path)
    facts=[{'id':'public-record','payload':{'scout_packet':{'mechanism':'Different name',
        'citations':[{'url':'https://mirror.example/code','content_sha256':hashlib.sha256((job/'sources/original.txt').read_bytes()).hexdigest(),'local_path':'/private/other/run'}]}}}]
    index=q.known_methods(facts);assert '/private/other' not in json.dumps(index)
    p=q.packet(s,a,'dqi',index)
    assert p['duplicate_candidates'][0]['shared_content_hashes']==[hashlib.sha256((job/'sources/original.txt').read_bytes()).hexdigest()]
    assert p['handoff_status']=='ready_for_review' # duplicate is advisory, never auto rejection
    s.close()


def test_missing_citation_feedback_and_repair_are_auditable(tmp_path):
    job,s,a=setup(tmp_path)
    s.record_hypothesis({'id':'bad','status':'active','source_urls':['https://example.org/missing-README.md']})
    q.refresh_citation_issues(s)
    assert q.pending_issues(s)[0]['missing_urls']==['https://example.org/missing-README.md']
    d=ToolDispatcher(s,SimpleNamespace(task_id='dqi'),{},job)
    fail=d.execute('record_scout_packet',{**a,'hypothesis_id':'bad'})
    assert fail['status']=='error' and fail['scout_issue']['missing_urls']
    assert 'https://example.org/missing-README.md' in fail['error']
    fix=d.execute('repair_hypothesis_citations',{'hypothesis_id':'bad','source_urls':['https://example.org/original'],'reason':'Original exact source fetched under this URL; checked version'})
    assert fix['status']=='ok' and not q.pending_issues(s)
    assert s.list_events('hypothesis_citations_repaired')[0]['original_source_urls']==['https://example.org/missing-README.md']
    assert d.execute('record_scout_packet',{**a,'hypothesis_id':'bad'})['status']=='ok'
    s.close()
