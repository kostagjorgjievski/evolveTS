"""Build the pinned lab fork without bundled datasets, tests or agent skills."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PIN = "904bb75717d5f83e9d8177affae2113c9ee3f6b3"
URL = f"https://codeload.github.com/NetManAIOps/sktime/tar.gz/{PIN}"
TASK = ROOT / "tasks/tsb_ad_u"
ARCHIVE = ROOT / "work/libraryts-install/libraryts.tar.gz"
VENDOR = TASK / "vendor"


def main():
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    VENDOR.mkdir(exist_ok=True)
    if not ARCHIVE.exists():
        urllib.request.urlretrieve(URL, ARCHIVE)
    archive_sha = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    if archive_sha != "67f0a923227789df233d96e37854c004c6005110d1efc6432d6939bf953718b3":
        raise RuntimeError("LibraryTS source archive checksum mismatch")
    with tempfile.TemporaryDirectory(prefix="libraryts-build-") as temporary:
        source = Path(temporary) / "source"
        source.mkdir()
        with tarfile.open(ARCHIVE) as archive:
            for item in archive:
                path = Path(*Path(item.name).parts[1:])
                if not item.isfile() or path.is_absolute() or ".." in path.parts:
                    continue
                if not path.parts:
                    continue
                keep = path.parts[0] == "sktime" or str(path) in {
                    "pyproject.toml", "setup.cfg", "setup.py", "MANIFEST.in",
                    "README.md", "LICENSE", "AUTHORS.rst", "LICENSE.md"}
                if not keep or any(part in {"tests", "data", "__pycache__"} for part in path.parts):
                    continue
                target = source / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(item).read())
        subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps",
                        "--wheel-dir", str(VENDOR), str(source)], check=True)
    wheel = VENDOR / "sktime-0.40.1-py3-none-any.whl"
    manifest = {"repository": "https://github.com/NetManAIOps/sktime", "commit": PIN,
                "archive_sha256": archive_sha, "wheel": wheel.name,
                "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                "exclusions": "bundled data directories, tests and all non-package workflows/skills; runtime source unchanged"}
    (TASK / "libraryts.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    main()
