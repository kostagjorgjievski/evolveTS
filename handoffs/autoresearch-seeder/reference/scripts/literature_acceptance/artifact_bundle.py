"""Snapshot only a bound attempt's regular source/data files using directory FDs."""
import hashlib,os,stat
from pathlib import Path

def snapshot(attempt,target):
    attempt=Path(os.path.abspath(attempt));target=Path(target);target.mkdir(exist_ok=True)
    if not attempt.name.startswith('attempt_') or not attempt.parent.name.startswith('explore_b'):raise ValueError('Attempt binding required')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY);manifest=[];total=0
    try:
        for part in attempt.parts[1:]+('artifact',):
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=child
        def walk(directory,relative,depth):
            nonlocal total
            if depth>8:raise ValueError('Artifact nesting exceeds 8 levels')
            for name in sorted(os.listdir(directory)):
                info=os.stat(name,dir_fd=directory,follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):raise ValueError('Artifact links rejected')
                path=relative/name
                if stat.S_ISDIR(info.st_mode):
                    sub=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
                    try:walk(sub,path,depth+1)
                    finally:os.close(sub)
                    continue
                if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise ValueError('Artifact must contain regular unlinked files')
                if path.suffix not in ('.py','.json','.toml','.txt','.md'):continue
                source=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
                try:
                    before=os.fstat(source)
                    if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_size>4*2**20:raise ValueError('Invalid artifact file')
                    with os.fdopen(os.dup(source),'rb') as handle:data=handle.read(4*2**20+1)
                    after=os.fstat(source)
                    if len(data)>4*2**20 or (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):raise ValueError('Artifact changed while snapshotting')
                finally:os.close(source)
                total+=len(data)
                if total>32*2**20 or len(manifest)>=512:raise ValueError('Artifact bundle limit exceeded')
                dest=target/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
                manifest.append({'path':str(path),'sha256':hashlib.sha256(data).hexdigest()})
        walk(fd,Path(),0)
    finally:os.close(fd)
    return manifest
