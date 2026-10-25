"""Explicit task contracts; model providers and credentials are not task metadata."""
import argparse,hashlib,importlib.util,json,re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
TASK_ID=re.compile(r'[a-z][a-z0-9_]*')

def load(task_id,root=ROOT):
    if not isinstance(task_id,str) or not TASK_ID.fullmatch(task_id):raise ValueError('Invalid task id')
    root=Path(root).resolve();folder=root/'tasks'/task_id;path=folder/'library.json'
    manifest=json.loads(path.read_text())
    if manifest.get('schema_version')!=1 or manifest.get('task_id')!=task_id:raise ValueError('Task manifest identity/version mismatch')
    paths={}
    for field in ('description','seed','protocol','validation_entrypoint','receipt_adapter'):
        value=manifest.get(field)
        if not isinstance(value,str):raise ValueError('Missing task path: '+field)
        resolved=(root/value).resolve()
        if not resolved.is_relative_to(folder.resolve()) or not folder.resolve().is_relative_to(root/'tasks'):
            raise ValueError('Task path must stay inside its task folder: '+field)
        if not resolved.is_file():raise ValueError('Missing task file: '+field)
        paths[field]=resolved
    return {'task_id':task_id,'manifest':manifest,'paths':paths,
            'manifest_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'protocol_sha256':hashlib.sha256(paths['protocol'].read_bytes()).hexdigest(),
            'library_directory':root/'library'/task_id,'runs_directory':root/'runs/library-rsi'/task_id}

def validate_receipt(task_id,receipt,level,root=ROOT):
    try:task=load(task_id,root=root)
    except FileNotFoundError as exc:raise ValueError('No registered receipt adapter for task '+task_id) from exc
    path=task['paths']['receipt_adapter']
    spec=importlib.util.spec_from_file_location('library_receipt_'+task_id,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.validate_receipt(receipt,level)

def main():
    p=argparse.ArgumentParser();p.add_argument('task_id');a=p.parse_args();t=load(a.task_id)
    print(json.dumps(t,indent=2,default=str))

if __name__=='__main__':main()
