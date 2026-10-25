"""Dream-RSI adapter for the unchanged official dqi verifier.

Candidate generators run without network or access to credentials on macOS.
Only the trusted verifier's output determines the reward.
"""
import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import stat
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OFFICIAL = ROOT / "data/quantum-compilation/official"
PYTHON = ROOT / ".dqi-venv/bin/python"
PROTOCOL = json.loads((HERE / "protocol.json").read_text())


def digest(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def verify_sources():
    for name, expected in PROTOCOL["official_sha256"].items():
        if digest(OFFICIAL / name) != expected:
            raise ValueError(f"Official file differs from pinned download: {name}")


def candidate_profile(job, output, extra_reads=()):
    """The generator can read its isolated interpreter and job; write output only."""
    reads = ["/System", "/usr", "/bin", "/sbin", "/Library", "/dev",
             "/private/etc", "/private/var/db", str(Path(sys.base_prefix).resolve()),
             str((ROOT / ".dqi-venv").resolve()), str(job.resolve())]
    reads += [str(Path(path).resolve()) for path in extra_reads]
    return ('(version 1)\n(allow default)\n(deny network*)\n'
            '(deny file-read* file-write*)\n(allow file-read-metadata)\n'
            '(allow file-read* (literal "/"))\n'
            + ''.join(f'(allow file-read* (subpath {json.dumps(p)}))\n' for p in reads)
            + f'(allow file-write* (subpath {json.dumps(str(output.resolve()))}))\n'
            + '(allow file-write* (literal "/dev/null"))\n')


def run_process(command, directory, env, timeout, memory_gib=10, scratch_directory=None, scratch_limit_bytes=2*2**30):
    """Bound the entire subprocess tree; never trust candidate stdout as a score."""
    import psutil
    with tempfile.TemporaryFile(mode="w+") as log:
        proc = subprocess.Popen(command, cwd=directory, env=env, stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True)
        started = time.monotonic()
        try:
            while proc.poll() is None:
                if time.monotonic() - started > timeout:
                    raise TimeoutError(f"Process exceeded {timeout} seconds")
                if os.fstat(log.fileno()).st_size > 4 * 2**20:
                    raise ValueError("Process log exceeded 4 MiB")
                if scratch_directory is not None:
                    if shutil.disk_usage(ROOT).free < 3*2**30:
                        raise ValueError('Execution needs at least 3 GiB free scratch space')
                    size=0;files=0
                    directories=scratch_directory if isinstance(scratch_directory,(list,tuple)) else [scratch_directory]
                    for folder in directories:
                        for path in Path(folder).rglob('*'):
                            try:info=path.stat(follow_symlinks=False)
                            except FileNotFoundError:continue
                            if stat.S_ISREG(info.st_mode):
                                size+=info.st_size;files+=1
                                if size>scratch_limit_bytes or files>20000:raise ValueError('Test workspace exceeded 2 GiB or 20000 files')
                try:
                    parent = psutil.Process(proc.pid)
                    processes = [parent] + parent.children(recursive=True)
                    rss = sum(p.memory_info().rss for p in processes if p.is_running())
                    if rss > memory_gib * 2**30:
                        raise MemoryError(f"Process tree exceeded {memory_gib} GiB RSS")
                except psutil.NoSuchProcess:
                    pass
                time.sleep(0.1)
            log.seek(0)
            text = log.read()
            if proc.returncode:
                raise RuntimeError(text[-4000:])
            return text
        finally:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()


def score_result(result, smoke=False):
    if result.get("status") != "PASS":
        raise ValueError("Official verification did not pass")
    expected = 2048 if smoke else PROTOCOL["num_shots"]
    if result.get("verified_shots") != expected:
        raise ValueError("Incomplete official verification")
    for key in ('m', 'n', 'degree', 'r', 'log2_delta'):
        if result.get(key) != PROTOCOL[key]:
            raise ValueError(f"Wrong DQI verification parameter: {key}")
    error_rate = result.get('effective_error_rate')
    if not isinstance(error_rate, (int, float)) or not 0 <= error_rate < 1/16:
        raise ValueError('DQI statistical error bound failed')
    cost = result.get("score")
    if isinstance(cost, bool) or not isinstance(cost, (float, int)) or not math.isfinite(cost) or cost <= 0:
        raise ValueError("Invalid official cost")
    summary = {"official": result, "scope": "smoke" if smoke else "full-development"}
    if not smoke and PROTOCOL['reference_cost'] is not None:
        summary["combined_score"] = PROTOCOL["reference_cost"] / cost
    return summary


def evaluate_program(program, output, smoke=False, salt=None, preflight=False, isolate_verifier=False):
    verify_sources()
    if sys.platform != "darwin":
        raise RuntimeError("Generator isolation is currently implemented for macOS only")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    program = Path(program).resolve()
    started = time.monotonic()
    locks = ROOT / "work/runtime-locks"
    locks.mkdir(parents=True, exist_ok=True)
    with (locks / "dqi-cpu.lock").open("a") as lock:
        # Coding agents may overlap; DQI verification uses one memory-bounded CPU slot.
        fcntl.flock(lock, fcntl.LOCK_EX)
        if shutil.disk_usage(ROOT).free < 3 * 2**30:
            raise RuntimeError('DQI evaluation needs at least 3 GiB free scratch space')
        with tempfile.TemporaryDirectory(prefix="dqi-generator-") as temp:
            job = Path(temp)
            generated = job / "output"
            generated.mkdir()
            (job / "program.py").write_bytes(program.read_bytes())
            shutil.copytree(OFFICIAL/"verifiers/dqi",job/"dqi")
            (job/"run_candidate.py").write_bytes((HERE/"run_candidate.py").read_bytes())
            sb = job / "generator.sb"
            sb.write_text(candidate_profile(job, generated))
            env = {"PATH": "/usr/bin:/bin", "HOME": str(generated), "TMPDIR": str(generated),
                   "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0",
                   **{key: "1" for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                       "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS")}}
            if preflight:
                (output/'phase.json').write_text(json.dumps({'stage':'syntax_imports'}))
                checker = job/'check_candidate.py'
                checker.write_bytes((HERE/'check_candidate.py').read_bytes())
                checked = run_process(['/usr/bin/sandbox-exec','-f',str(sb),str(PYTHON),'-I',
                                       str(job/"run_candidate.py"),str(checker),str(job/'program.py')],job,env,60)
                (output/'preflight.log').write_text(checked)
            (output/'phase.json').write_text(json.dumps({'stage':'generation'}))
            circuit = generated / "dqi.kmb"
            log = run_process(["/usr/bin/sandbox-exec", "-f", str(sb), str(PYTHON), "-I",
                               str(job/"run_candidate.py"), str(job / "program.py"), str(circuit)], job, env,
                              PROTOCOL["generator_timeout_seconds"])
            (output / "generator.log").write_text(log)
            if circuit.is_symlink() or not circuit.is_file() or not 0 < circuit.stat().st_size <= 2 * 2**30:
                raise ValueError("Generator must write a regular .kmb file, at most 2 GiB")
            frozen = output / "dqi.kmb"
            shutil.copyfile(circuit, frozen)
        verifier = OFFICIAL / "verifiers/dqi/verify_submission_dqi.py"
        command = [str(PYTHON), "-I", str(verifier), str(frozen)]
        for key in ('m', 'n', 'degree', 'r', 'batch_size', 'log2_delta', 'max_workers'):
            command += ['--'+key.replace('_', '-'), str(PROTOCOL[key])]
        command += ['--num-shots', str(2048 if smoke else PROTOCOL['num_shots']),
                    '--salt', salt or PROTOCOL['development_salt']]
        env.update(HOME=str(output), TMPDIR=str(output))
        (output/'phase.json').write_text(json.dumps({'stage':'verification'}))
        if isolate_verifier:
            profile = output/'verifier.sb'
            profile.write_text(candidate_profile(output,output,[verifier.parent]))
            command = ['/usr/bin/sandbox-exec','-f',str(profile)] + command
        # Verifier runs separately from the candidate, with no provider/Kaggle credentials.
        log = run_process(command, output, env, PROTOCOL["verifier_timeout_seconds"])
        (output / "verifier.json").write_text(log)
        result = score_result(json.loads(log), smoke)
    result.update(program_sha256=digest(program), circuit_file_sha256=digest(frozen),
                  output_directory=str(output),
                  validation_workers=PROTOCOL['max_workers'],
                  protocol_sha256=digest(HERE / "protocol.json"),
                  salt=salt or PROTOCOL["development_salt"], seconds=time.monotonic()-started)
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def evaluate(program_path):
    """Upstream task API; full official workload, larger reward is better."""
    folder = None
    try:
        verify_sources()
        receipt = ROOT / 'outputs/dqi-calibration/result.json'
        if (digest(program_path) == PROTOCOL.get('reference_program_sha256')
                and receipt.exists()
                and digest(receipt) == PROTOCOL.get('reference_result_sha256')):
            # Reuse only the fully verified, hash-pinned seed calibration.
            cached = json.loads(receipt.read_text())
            cached.update(score_result(cached['official']))
            cached.update(cached_baseline=True, seconds=0.0)
            cached['protocol_sha256'] = digest(HERE/'protocol.json')
            return cached
        if PROTOCOL['reference_cost'] is None:
            raise RuntimeError('Run start_e0.py to complete full reference calibration first')
        base = ROOT / "outputs/dqi"
        base.mkdir(parents=True, exist_ok=True)
        folder = base / f"evaluation-{uuid.uuid4().hex}"
        result = evaluate_program(program_path, folder)
        # A reference-size binary is ~0.9 GB. Retain source/hash/metrics for every
        # attempt, and only the best validated binary; this Mac has limited disk.
        circuit = folder / 'dqi.kmb'
        best = base / 'best'
        best.mkdir(exist_ok=True)
        with (base/'best.lock').open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            previous = json.loads((best/'result.json').read_text()) if (best/'result.json').exists() else {}
            if result['combined_score'] > previous.get('combined_score', 0):
                circuit.replace(best/'dqi.kmb')
                (best/'result.json').write_text(json.dumps(result, indent=2)+'\n')
            else:
                circuit.unlink()
        return result
    except Exception as exc:
        return {"combined_score": 0.0, "error": str(exc)}
    finally:
        if folder is not None:
            (folder/'dqi.kmb').unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--program", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true", help="2048 shots; no search reward")
    parser.add_argument("--final", action="store_true", help="Full run with a separate local salt")
    parser.add_argument("--frozen-sha256")
    args = parser.parse_args()
    if args.final:
        if args.smoke or not args.frozen_sha256 or digest(args.program) != args.frozen_sha256:
            parser.error("--final requires the matching --frozen-sha256 and disallows --smoke")
    result = evaluate_program(args.program, args.output, args.smoke,
                              "evolvets-dqi-final-v1" if args.final else None)
    if args.final:
        result.pop("combined_score", None)
        result["scope"] = "full-local-final"
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
