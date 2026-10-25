"""Shared diagnostic slots; large jobs retain the existing exclusive heavy lock."""
from contextlib import contextmanager
import fcntl
from pathlib import Path
import time


@contextmanager
def diagnostic_slot(root, timeout, memory_gib):
    locks = Path(root) / 'work/runtime-locks'
    locks.mkdir(parents=True, exist_ok=True)
    if timeout > 60 or memory_gib > 2:
        with (locks / 'dqi-cpu.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield
        return
    # One shared pair across both benchmarks, independent of the heavy lane.
    while True:
        for index in range(2):
            lock = (locks / f'quick-diagnostic-{index}.lock').open('a')
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                lock.close()
                continue
            try:
                yield
            finally:
                lock.close()
            return
        time.sleep(0.1)
