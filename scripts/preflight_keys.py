"""Send one-token requests with the backend key (and every key-pool key) before a start.

Keys the provider accepts are made usable again in key-pool.json; refused keys
are marked refused. Exits non-zero when no key works, so a run never starts
only to record refusals. Keys are reported by index, never printed.
"""
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

from key_pool import KeyPool, load_keys


def check(key):
    """None when the key is usable; otherwise why the provider refused it.

    Only 400-403 refuse a key. A rate limit (429) or server error means the key
    was accepted but the provider is busy, so the key stays usable.
    """
    body = json.dumps({"model": os.environ["ANTHROPIC_MODEL"].removesuffix("[1m]"), "max_tokens": 8,
                       "messages": [{"role": "user", "content": "ping"}]}).encode()
    request = urllib.request.Request(os.environ["ANTHROPIC_BASE_URL"].rstrip("/") + "/v1/messages", body, {
        "content-type": "application/json", "anthropic-version": "2023-06-01",
        "x-api-key": key, "authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(request, timeout=120):
            return None
    except urllib.error.HTTPError as error:
        if error.code in (400, 401, 402, 403):
            return f"HTTP {error.code}: {error.read()[:300].decode(errors='replace')}"
        print(f"[preflight] HTTP {error.code} (provider busy); the key itself was accepted", flush=True)
    except OSError as error:
        print(f"[preflight] {type(error).__name__}: {error}; treated as a transient failure", flush=True)
    return None


def main():
    keys = load_keys() or [os.environ["ANTHROPIC_AUTH_TOKEN"]]
    results = [check(key) for key in keys]
    for index, error in enumerate(results):
        print(f"[preflight] key {index}: {'ok' if error is None else 'refused, ' + error}", flush=True)
    if load_keys():
        pool = KeyPool(keys, Path(os.environ.get("DRSI_KEY_POOL_STATE")
                                     or Path(os.environ["DRSI_AGENT_BUDGET_FILE"]).parent / "key-pool.json"), 1)
        pool.reset_refused([i for i, error in enumerate(results) if error is None])
        for index, error in enumerate(results):
            if error is not None:
                pool.refuse(index, "preflight: " + error)
    working = sum(error is None for error in results)
    print(f"[preflight] {working} of {len(keys)} key(s) usable", flush=True)
    return 0 if working else 2


if __name__ == "__main__":
    sys.exit(main())
