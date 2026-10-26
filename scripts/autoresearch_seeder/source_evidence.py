"""Bind research quotations to own fetched bytes; this does not prove inference."""
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from .models import file_digest


class Visible(HTMLParser):
    def __init__(self):super().__init__();self.skip=0;self.text=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.skip+=1
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.skip=max(0,self.skip-1)
    def handle_data(self,data):
        if not self.skip:self.text.append(data)


def normalized(text):return ' '.join(text.split())


def assess(raw):
    """Flag retrieval problems, never block a hostname or infer authentication."""
    if not raw:return {'status':'unusable','reason':'empty response'}
    text=raw.decode('utf-8',errors='replace')
    if re.search(r'<(?:!doctype html|html|body)\b',text,re.I):
        parser=Visible();parser.feed(text);visible=normalized(' '.join(parser.text))
        wall=any(x in visible.lower() for x in ('verify you are human','enable javascript','sign in to continue','access denied'))
        if len(visible)<500 and wall:return {'status':'unusable','reason':'challenge/login/shell text; retrieve original source or public API'}
        if len(visible)<80 and re.search('<script',text,re.I):return {'status':'unusable','reason':'JavaScript shell without substantive visible content'}
        return {'status':'reviewable','reason':'visible HTML text; quoted content still needs matching'}
    return {'status':'reviewable','reason':'retrieved bytes; scientific content unverified'}


def _text(raw,path):
    if raw.startswith(b'%PDF-'):
        converter=shutil.which('pdftotext')
        if not converter:raise ValueError('PDF evidence needs pdftotext; no citation acceptance without extraction')
        with tempfile.TemporaryFile() as out:
            result=subprocess.run([converter,'-f','1','-l','100','-layout',str(path),'-'],stdout=out,stderr=subprocess.PIPE,timeout=20)
            out.seek(0);text=out.read(16*2**20+1)
        if result.returncode or len(text)>16*2**20:raise ValueError('PDF evidence extraction failed or exceeded limit')
        return text.decode(errors='replace')
    if b'\0' in raw:return ''
    text=raw.decode('utf-8',errors='replace')
    if re.search(r'<(?:!doctype html|html|body)\b',text,re.I):
        parser=Visible();parser.feed(text);return ' '.join(parser.text)
    try:value=json.loads(text)
    except (ValueError,RecursionError):return text
    parts=[]
    def walk(x):
        if isinstance(x,str):parts.append(x)
        elif isinstance(x,list):
            for v in x:walk(v)
        elif isinstance(x,dict):
            for v in x.values():walk(v)
    walk(value)
    return text+'\n'+'\n'.join(parts)


def verify_spans(store,spans,citation_urls):
    if not isinstance(spans,list) or not 1<=len(spans)<=32:raise ValueError('Supply 1..32 evidence_spans linking claims to exact source quotations')
    root=store.path.parent.parent/'sources';verified=[]
    for span in spans:
        if not isinstance(span,dict) or set(span)-{'source_url','quote','claim','relative_path'} or not all(isinstance(span.get(k),str) and span[k].strip() for k in ('source_url','quote','claim')):
            raise ValueError('Each span requires source_url, quote and claim; optional repository relative_path')
        if len(normalized(span['quote']))<24:raise ValueError('Use a substantive quotation of at least24 characters')
        if span['source_url'] not in citation_urls:raise ValueError('Evidence must cite this packet original sources')
        source=store.get_source(span['source_url'])
        if not source or source.get('status')!='accessed':raise ValueError('Fetch and hash this exact source URL before citing it: '+span['source_url'])
        path=Path(source.get('local_path',''))
        if not path.is_absolute() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):raise ValueError('Evidence must use this job fetched cache, without links')
        if path.is_dir():
            index=path/'SOURCE_MANIFEST.json'
            if index.is_symlink() or file_digest(index)!=source['content_sha256']:raise ValueError('Repository manifest hash mismatch; refetch pinned source')
            rel=span.get('relative_path');entry=next((e for e in json.loads(index.read_text())['files'] if e['path']==rel),None)
            if not entry:raise ValueError('Repository span must name a manifest-listed relative_path')
            path=path/rel
            if '..' in Path(rel).parts or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):raise ValueError('Unsafe repository evidence path')
            expected=entry['sha256']
        else:
            if span.get('relative_path'):raise ValueError('relative_path is for repository citations only')
            expected=source['content_sha256']
        if not path.is_file() or path.stat().st_size>16*2**20:raise ValueError('Evidence file unavailable or too large')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('Cached source hash mismatch; refetch')
        assessment=assess(raw)
        if assessment['status']=='unusable':raise ValueError('Unusable research evidence: '+assessment['reason'])
        text=normalized(_text(raw,path));quote=normalized(span['quote'])
        if quote not in text:raise ValueError('Quoted evidence not found in cached source: '+span['source_url'])
        verified.append({**span,'file_sha256':expected,'match':'whitespace-normalized exact substring',
            'label':'quotation exists; claim interpretation requires independent review'})
    return verified


def require_review(store):
    roles=store.list_events('research_role')
    if not roles or roles[-1].get('role')!='reproducer':raise ValueError('Implementation requires an explicit reproducer role and evidence review')
    packets=store.list_events('scout_packet')
    if not packets:raise ValueError('Record an evidence-backed scout packet before implementation')
    packet=packets[-1]['packet']
    if packet.get('handoff_status')!='ready_for_review' or not packet.get('verified_spans'):raise ValueError('Packet needs matched source evidence and complete dependencies before implementation')
    # Recheck bytes: neither a changed source nor a different packet inherits approval.
    verify_spans(store,[{k:v for k,v in s.items() if k in ('source_url','quote','claim','relative_path')} for s in packet['verified_spans']],{s['url'] for s in packet['citations']})
    reviews=store.list_events('scout_review')
    matching=[r for r in reviews if r['fingerprint']==packet['fingerprint']]
    if not matching or matching[-1]['outcome'] not in ('accepted_for_test','corrected'):
        raise ValueError('Independent reproducer review must approve this exact packet before implementation')
