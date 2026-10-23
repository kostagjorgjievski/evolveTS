"""Seatbelt profile for Mac candidates, inherited by their subprocesses."""
import json
from pathlib import Path


def profile(candidate, output):
    candidate, output = Path(candidate).resolve(), Path(output).resolve()
    # Include the base Python installation used by this isolated venv.
    import sys
    reads = ["/System", "/usr", "/bin", "/sbin", "/Library", "/dev",
             "/private/etc", "/private/var/db", "/opt/homebrew",
             str(Path(sys.base_prefix).resolve()), str(Path(sys.prefix).resolve()),
             str(Path(__file__).resolve().parent), str(candidate.parent)]
    entries = "\n".join(f"(allow file-read* (subpath {json.dumps(p)}))" for p in reads)
    return ("(version 1)\n(allow default)\n(deny network*)\n"
            "(deny file-read* file-write*)\n(allow file-read-metadata)\n"
            '(allow file-read* (literal "/"))\n' + entries + "\n"
            f"(allow file-write* (subpath {json.dumps(str(output))}))\n"
            '(allow file-write* (literal "/dev/null"))\n')
