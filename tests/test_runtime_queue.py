import fcntl
import multiprocessing
from pathlib import Path
import queue
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from runtime_queue import diagnostic_slot


def acquire(root, timeout, memory, entered, release):
    with diagnostic_slot(root, timeout, memory):
        entered.put(True)
        release.wait(10)


class RuntimeQueueTests(unittest.TestCase):
    def test_two_quick_slots_work_while_heavy_is_locked(self):
        ctx = multiprocessing.get_context('spawn')
        with tempfile.TemporaryDirectory() as root:
            locks = Path(root) / 'work/runtime-locks'
            locks.mkdir(parents=True)
            with (locks / 'dqi-cpu.lock').open('a') as heavy:
                fcntl.flock(heavy, fcntl.LOCK_EX)
                entered, release = ctx.Queue(), ctx.Event()
                processes = [ctx.Process(target=acquire, args=(root, 60, 2, entered, release)) for _ in range(3)]
                try:
                    for process in processes:
                        process.start()
                    entered.get(timeout=5)
                    entered.get(timeout=5)
                    with self.assertRaises(queue.Empty):
                        entered.get(timeout=0.4)
                    release.set()
                    entered.get(timeout=5)
                finally:
                    release.set()
                    for process in processes:
                        process.join(5)
                        if process.is_alive():
                            process.terminate()
                    self.assertTrue(all(p.exitcode == 0 for p in processes))

    def test_long_or_large_diagnostic_keeps_heavy_lock(self):
        with tempfile.TemporaryDirectory() as root:
            for timeout, memory in [(600, 2), (60, 8)]:
                with diagnostic_slot(root, timeout, memory):
                    with (Path(root) / 'work/runtime-locks/dqi-cpu.lock').open('a') as other:
                        with self.assertRaises(BlockingIOError):
                            fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)


if __name__ == '__main__':
    unittest.main()
