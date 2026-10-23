"""Pin the source/archive and prepare only the official tuning split by default."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROTOCOL = json.loads((HERE / "protocol.json").read_text())
DATA = ROOT / "data/tsb-ad-u"
REPO = ROOT / "upstream/tsb-ad"


def sha256(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def verify_source():
    actual = subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip()
    if actual != PROTOCOL["benchmark_commit"]:
        raise RuntimeError("TSB-AD source differs from protocol pin")
    if subprocess.check_output(["git", "-C", str(REPO), "status", "--porcelain"], text=True).strip():
        raise RuntimeError("TSB-AD source must remain clean")


def file_list(kind):
    names = {"tuning": "development_list", "evaluation": "evaluation_list", "full": "full_evaluation_list"}
    with (REPO / "Datasets/File_List" / PROTOCOL[names[kind]]).open() as handle:
        result = [row["file_name"] for row in csv.DictReader(handle)]
    if len(result) != len(set(result)) or any(Path(name).name != name for name in result):
        raise RuntimeError("Invalid benchmark file list")
    return result


def verify_splits():
    tuning, evaluation, full = (set(file_list(k)) for k in ("tuning", "evaluation", "full"))
    expected = (PROTOCOL["development_series"], PROTOCOL["evaluation_series"], PROTOCOL["full_evaluation_series"])
    if tuple(map(len, (tuning, evaluation, full))) != expected:
        raise RuntimeError("Official split counts changed")
    if tuning & full or not evaluation <= full:
        raise RuntimeError("Official tuning/evaluation split is inconsistent")
    return expected


def prepare(archive=None):
    verify_source()
    verify_splits()
    DATA.mkdir(parents=True, exist_ok=True)
    target = DATA / "TSB-AD-U.zip"
    if not target.exists():
        temporary = DATA / "TSB-AD-U.zip.partial"
        if archive:
            import shutil
            shutil.copyfile(archive, temporary)
        else:
            request = urllib.request.Request(PROTOCOL["data_url"], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as out:
                import shutil
                shutil.copyfileobj(response, out)
        if sha256(temporary) != PROTOCOL["data_sha256"]:
            raise RuntimeError("Downloaded archive checksum differs from pinned data")
        temporary.replace(target)
    if sha256(target) != PROTOCOL["data_sha256"]:
        raise RuntimeError("Archive checksum differs from protocol pin")
    records = {}
    with zipfile.ZipFile(target) as zipped:
        for name in file_list("tuning"):
            payload = zipped.read("TSB-AD-U/" + name)
            path = DATA / "tuning" / name
            path.parent.mkdir(exist_ok=True)
            if path.exists() and path.read_bytes() != payload:
                raise RuntimeError("Existing tuning file differs from archive: " + name)
            path.write_bytes(payload)
            records[name] = hashlib.sha256(payload).hexdigest()
    manifest = {"benchmark_commit": PROTOCOL["benchmark_commit"], "archive_sha256": sha256(target),
                "tuning_files": records, "evaluation_extracted": False}
    (DATA / "prepared-development.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    manifest = prepare(args.archive)
    print(json.dumps({"tuning_series": len(manifest["tuning_files"]),
                      "archive_sha256": manifest["archive_sha256"], "evaluation_extracted": False}))
