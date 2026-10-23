"""Spread agent sessions over several provider keys, at most N sessions per key.

Provider rate limits apply per account, so keys from separate accounts add
capacity. Keys are referred to by index only: index 0 is the backend's main
key, then the lines of DRSI_KEY_POOL_FILE. Leases and refused keys are kept in
key-pool.json next to the accounting file, guarded by a file lock, so every
process sharing the accounting sees the same state. Leases of dead processes
are dropped automatically.
"""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import threading
import time


def load_keys():
    """The main key plus the pool file's keys, or None when no pool is configured."""
    pool_file = os.environ.get("DRSI_KEY_POOL_FILE")
    if not pool_file:
        return None
    keys = [os.environ["ANTHROPIC_AUTH_TOKEN"]]
    for line in Path(pool_file).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and line not in keys:
            keys.append(line)
    return keys


class KeyPool:
    def __init__(self, keys, state_path, per_key):
        self.keys, self.state_path, self.per_key = keys, Path(state_path), per_key

    @contextmanager
    def _state(self):
        with self.state_path.open("a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            handle.seek(0)
            state = json.loads(handle.read() or "{}")
            state.setdefault("leases", {})
            state.setdefault("refused", {})
            yield state
            handle.seek(0)
            handle.truncate()
            json.dump(state, handle, indent=2)

    @staticmethod
    def _alive(lease):
        try:
            os.kill(lease[0], 0)
            return True
        except ProcessLookupError:
            return False

    def live(self, state):
        return [i for i in range(len(self.keys)) if str(i) not in state["refused"]]

    def acquire(self):
        """Block until a non-refused key has a free session slot; None if every key was refused."""
        me = [os.getpid(), threading.get_ident()]
        while True:
            with self._state() as state:
                for index, leases in list(state["leases"].items()):
                    state["leases"][index] = [lease for lease in leases if self._alive(lease)]
                live = self.live(state)
                if not live:
                    return None
                index = min(live, key=lambda i: len(state["leases"].get(str(i), [])))
                if len(state["leases"].get(str(index), [])) < self.per_key:
                    state["leases"].setdefault(str(index), []).append(me)
                    return index
            time.sleep(5)

    def release(self, index):
        me = [os.getpid(), threading.get_ident()]
        with self._state() as state:
            leases = state["leases"].get(str(index), [])
            if me in leases:
                leases.remove(me)

    def refuse(self, index, reason):
        """Stop using a key; returns how many keys remain usable."""
        with self._state() as state:
            state["refused"][str(index)] = {"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                            "reason": reason[:500]}
            return len(self.live(state))

    def reset_refused(self, indices):
        """A launcher whose preflight accepted these keys makes them usable again."""
        with self._state() as state:
            for index in indices:
                state["refused"].pop(str(index), None)
