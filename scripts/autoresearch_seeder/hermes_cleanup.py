"""Stop only a job-local Hermes owner, guarded by home and process birth.

Executed with Hermes's interpreter so its own process-identity implementation
is used. A timed-out chat client does not otherwise stop its detached owner.
"""
import json
import sys
from pathlib import Path


def main(home):
    import psutil
    from gateway.status import get_process_start_time
    home = Path(home).resolve()
    record_path = home / 'gateway.pid'
    if not record_path.is_file():
        return
    record = json.loads(record_path.read_text())
    if record.get('kind') != 'hermes-gateway' or Path(record.get('hermes_home', '/')).resolve() != home:
        raise RuntimeError('Refusing cleanup of a different Hermes home')
    pid, birth = record['pid'], record.get('start_time')
    if birth is None or get_process_start_time(pid) != birth:
        return
    parent = psutil.Process(pid)
    processes = parent.children(recursive=True) + [parent]
    identities = [(p, p.create_time()) for p in processes]
    for process, created in reversed(identities):
        try:
            if process.create_time() == created:
                process.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(processes, timeout=5)
    for process in alive:
        try:
            expected = next(b for p, b in identities if p.pid == process.pid)
            if process.create_time() == expected:
                process.kill()
        except psutil.NoSuchProcess:
            pass


if __name__ == '__main__':
    main(sys.argv[1])
