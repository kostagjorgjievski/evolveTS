"""Pin the RCAEval RE1 data revision, verify checksums, define the frozen split."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROTOCOL = json.loads((HERE / "protocol.json").read_text())
DATA = ROOT / "data/rcaeval"
REPO = ROOT / "upstream/rcaeval"


def sha256(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def verify_source():
    if not (REPO / ".git").exists():
        raise RuntimeError("missing upstream/rcaeval; run scripts/bootstrap.sh")
    actual = subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip()
    if actual != PROTOCOL["benchmark_commit"]:
        raise RuntimeError("RCAEval source differs from protocol pin")
    if subprocess.check_output(["git", "-C", str(REPO), "status", "--porcelain"], text=True).strip():
        raise RuntimeError("RCAEval source must remain clean")


def cases_frame():
    import pandas as pd
    path = DATA / PROTOCOL["cases_file"]
    if not path.exists():
        raise FileNotFoundError(f"missing {path}; run tasks/rca_re1/setup.sh")
    if sha256(path) != PROTOCOL["cases_sha256"]:
        raise RuntimeError("cases.parquet differs from protocol pin")
    frame = pd.read_parquet(path)
    frame = frame[frame["suite"] == PROTOCOL["suite"]].copy()
    if len(frame) != PROTOCOL["full_evaluation_cases"]:
        raise RuntimeError("RE1 case count changed")
    return frame.sort_values("case").reset_index(drop=True)


def split_rule(kind):
    if kind == "development":
        return lambda frame: frame[frame["repetition"] == 1]
    if kind == "evaluation":
        return lambda frame: frame[frame["repetition"] != 1]
    if kind == "full":
        return lambda frame: frame
    raise ValueError("unknown split: " + kind)


def split_cases(kind):
    return split_rule(kind)(cases_frame()).sort_values("case").reset_index(drop=True)


def manifest():
    path = HERE / PROTOCOL["data_manifest"]
    return json.loads(path.read_text())


def verify_case_files(kind, frame=None):
    """Check every file the split will read against the committed manifest."""
    frame = cases_frame() if frame is None else frame
    expected = manifest()["files"]
    missing = []
    for case in frame["case"]:
        metrics = DATA / case / "metrics.parquet"
        digest = expected.get(case)
        if digest is None:
            raise RuntimeError("case missing from data manifest: " + case)
        if not metrics.exists():
            missing.append(case)
        elif sha256(metrics) != digest:
            raise RuntimeError("metrics checksum mismatch: " + case)
        inject = DATA / case / "inject_time.txt"
        if inject.exists():
            declared = int(frame.loc[frame["case"] == case, "inject_time"].iloc[0])
            if int(inject.read_text().strip()) != declared:
                raise RuntimeError("inject_time.txt disagrees with cases.parquet: " + case)
    if missing:
        raise FileNotFoundError("missing metrics for %d cases (first: %s)" % (len(missing), missing[0]))


def download():
    """Fetch the pinned revision. Direct resolve URLs avoid Hub API rate limits."""
    import concurrent.futures
    import time
    import urllib.request

    DATA.mkdir(parents=True, exist_ok=True)
    endpoint = os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
    base = f"{endpoint}/datasets/{PROTOCOL['data_repo']}/resolve/{PROTOCOL['data_revision']}"

    def fetch(relative):
        target = DATA / relative
        if target.exists() and target.stat().st_size > 0:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".partial")
        for attempt in range(8):
            try:
                request = urllib.request.Request(base + "/" + relative,
                                                 headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(request, timeout=120) as response, \
                        temporary.open("wb") as handle:
                    while chunk := response.read(1 << 20):
                        handle.write(chunk)
                if temporary.stat().st_size == 0:
                    raise RuntimeError("empty download")
                temporary.replace(target)
                time.sleep(0.3)
                return
            except Exception:
                temporary.unlink(missing_ok=True)
                if attempt == 7:
                    raise
                time.sleep(min(60, 5 * 2 ** attempt))
        raise RuntimeError("unreachable")

    fetch(PROTOCOL["cases_file"])
    if sha256(DATA / PROTOCOL["cases_file"]) != PROTOCOL["cases_sha256"]:
        raise RuntimeError("downloaded cases.parquet differs from protocol pin")
    names = []
    for case in cases_frame()["case"]:
        names += [case + "/metrics.parquet", case + "/inject_time.txt"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        list(pool.map(fetch, names))
    (DATA / "REVISION").write_text(PROTOCOL["data_revision"] + "\n")



def write_manifest():
    frame = cases_frame()
    files = {}
    for case in frame["case"]:
        path = DATA / case / "metrics.parquet"
        if not path.exists():
            raise FileNotFoundError(f"missing {path}")
        files[case] = sha256(path)
    payload = {"data_revision": PROTOCOL["data_revision"], "cases_sha256": PROTOCOL["cases_sha256"],
               "files": dict(sorted(files.items()))}
    (HERE / PROTOCOL["data_manifest"]).write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def prepare(write=False):
    verify_source()
    download()
    if write:
        write_manifest()
    frame = cases_frame()
    for kind in ("development", "evaluation", "full"):
        cases = split_cases(kind)
        verify_case_files(kind, cases)
        expected = {"development": PROTOCOL["development_cases"],
                    "evaluation": PROTOCOL["evaluation_cases"],
                    "full": PROTOCOL["full_evaluation_cases"]}[kind]
        if len(cases) != expected:
            raise RuntimeError(f"{kind} split has {len(cases)} cases, expected {expected}")
    development = split_cases("development")
    payload = {
        "data_revision": PROTOCOL["data_revision"],
        "cases_sha256": PROTOCOL["cases_sha256"],
        "development_rule": PROTOCOL["development_rule"],
        "development_cases": development["case"].tolist(),
        "development_strata": int(development[["system", "root_cause_service", "fault"]]
                                  .drop_duplicates().shape[0]),
        "evaluation_cases": int(len(split_cases("evaluation"))),
        "full_cases": int(len(cases_frame())),
    }
    (DATA / "prepared-development.json").write_text(json.dumps(payload, indent=2) + "\n")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-manifest", action="store_true",
                        help="authoring only: regenerate the committed per-case checksums")
    args = parser.parse_args()
    summary = prepare(write=args.write_manifest)
    print(json.dumps({key: summary[key] for key in
                      ("development_cases", "evaluation_cases", "full_cases", "development_strata")}))
