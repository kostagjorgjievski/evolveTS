"""Pinned public source retrieval without downloading benchmark binaries."""
import concurrent.futures,hashlib,json,re,shutil,tempfile,urllib.parse
from pathlib import Path,PurePosixPath

def retrieve(url,ref,cache,get,paths=None):
    match=re.fullmatch(r'https://github.com/([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/tree/([\w.-]+))?/?',url)
    if not match:raise ValueError('Public GitHub repository URL required')
    owner,name,urlref=match.groups();ref=ref or urlref or 'HEAD'
    if not re.fullmatch(r'[\w.-]+',ref):raise ValueError('A commit SHA, tag or simple branch name is required')
    meta=json.loads(get(f'https://api.github.com/repos/{owner}/{name}/commits/{ref}'))
    sha=meta['sha']
    if not re.fullmatch('[0-9a-f]{40}',sha):raise ValueError('Invalid resolved commit')
    if paths is not None:
        if not isinstance(paths,list) or not paths or len(paths)>200 or any(not isinstance(p,str) or not p or PurePosixPath(p).is_absolute() or '..' in PurePosixPath(p).parts for p in paths):
            raise ValueError('paths must contain 1..200 exact safe repository file paths')
        paths=sorted(set(paths))
    selection='-'+hashlib.sha256(json.dumps(paths).encode()).hexdigest()[:12] if paths else ''
    target=Path(cache)/f'{owner}__{name}__{sha[:12]}{selection}'
    if not target.exists():
        tree=json.loads(get(f'https://api.github.com/repos/{owner}/{name}/git/trees/{sha}?recursive=1',12*2**20))
        if tree.get('truncated'):raise ValueError('Repository source index is truncated')
        selected=[]
        for item in tree['tree']:
            p=PurePosixPath(item['path'])
            if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe repository path')
            if paths and item['path'] not in paths:continue
            if item.get('type')!='blob' or item.get('mode') not in ('100644','100755'):continue
            if p.suffix not in ('.py','.json','.md','.toml','.txt','.c','.h','.cpp','.hpp') and p.name not in ('LICENSE','COPYING','Makefile'):continue
            if item.get('size',0)>4*2**20:continue
            selected.append(item)
        if paths and set(paths)!={x['path'] for x in selected}:raise ValueError('Selected paths missing, too large or not supported source files; inspect the pinned tree')
        if len(selected)>2000 or sum(x.get('size',0) for x in selected)>50*2**20:raise ValueError('Source exceeds 2000 files / 50 MiB')
        temp=Path(tempfile.mkdtemp(dir=cache,prefix='.source-'))
        try:
            def download(item):
                path=item['path'];data=get(f'https://raw.githubusercontent.com/{owner}/{name}/{sha}/'+urllib.parse.quote(path,safe='/'))
                blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
                if blob!=item['sha']:raise ValueError('Public source blob hash mismatch: '+path)
                dest=temp/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
                return {'path':path,'git_blob':blob,'sha256':hashlib.sha256(data).hexdigest()}
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:manifest=list(pool.map(download,selected))
            (temp/'SOURCE_MANIFEST.json').write_text(json.dumps({'repository':url,'commit':sha,'files':manifest},indent=2))
            temp.rename(target)
        finally:
            if temp.exists():shutil.rmtree(temp)
    files=sorted(str(p.relative_to(target)) for p in target.rglob('*') if p.is_file())
    return {'url':url,'repository':url,'commit':sha,'directory':str(target),'files':files[:250],'file_count':len(files),'complete_index':str(target/'SOURCE_MANIFEST.json')}
