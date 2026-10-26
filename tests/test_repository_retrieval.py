import hashlib
import json
from types import SimpleNamespace
import pytest
from scripts.autoresearch_seeder.tools import SourceFetcher,ToolDispatcher
from scripts.autoresearch_seeder.store import ResearchStore


def fixture_get(url,limit=None):
    body=b'# Public original source\n'
    if '/commits/' in url:return json.dumps({'sha':'a'*40}).encode()
    if '/git/trees/' in url:
        def entry(path,size):
            return {'path':path,'type':'blob','mode':'100644','size':size,
                    'sha':hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()}
        return json.dumps({'tree':[entry('README.md',len(body))]+[entry(f'other{i}.py',30000) for i in range(2001)]}).encode()
    assert '/'+('a'*40)+'/README.md' in url
    return body


def test_selected_files_from_large_repo_record_url_and_pinned_citations(tmp_path):
    job=tmp_path/'job';store=ResearchStore(job/'private/research.sqlite')
    fetcher=SourceFetcher(job/'sources',[],get=fixture_get)
    d=ToolDispatcher(store,SimpleNamespace(task_id='dqi'),{},job,fetcher=fetcher)
    url='https://github.com/example/research'
    result=d.execute('fetch_repository',{'url':url,'paths':['README.md']})
    assert result['status']=='ok',result
    assert result['result']['commit']=='a'*40
    source=store.get_source(url)
    assert source['status']=='accessed' and source['content_sha256']
    assert json.loads((__import__('pathlib').Path(source['local_path'])/'SOURCE_MANIFEST.json').read_text())['files'][0]['path']=='README.md'
    with pytest.raises(ValueError,match='2000 files'):fetcher.repository(url)
    with pytest.raises(ValueError,match='safe repository'):fetcher.repository(url,paths=['../private.py'])
    with pytest.raises(ValueError,match='missing'):fetcher.repository(url,paths=['missing.py'])
    store.close()
