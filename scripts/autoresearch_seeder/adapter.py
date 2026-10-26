"""Task adapter: task contract, frozen artifact, diagnostics, official checks.

A task is described by tasks/<id>/library.json (the existing library_rsi
registry contract) plus a runnable pair used unchanged:

  * diagnostics:  <validation_entrypoint> ATTEMPT --diagnostic
                  -> JSON receipt on stdout (status PASS/FAIL, logs, no score)
  * validation:   <task>/evaluator.py --program P --output D [--smoke] [--salt S]
                  -> the unchanged official development/full verification receipt

Salts come from the task protocol (development_salt / final_salt by default,
configurable through the seeder config). The adapter never modifies official
scoring, limits or verifier files; it only labels the receipt envelope the
way the task's own library_validate.py does (scope/held_out).
"""
import importlib.util
import json
import sys
from pathlib import Path

from .models import ToolInfrastructureError, file_digest

DEVELOPMENT = 'development'
CONFIRMATION = 'confirmation'


class TaskAdapter:
    """Loads one registered task through the library.json contract."""

    def __init__(self, task_id: str, root):
        root = Path(root).resolve()
        # library_rsi is code that ships with this checkout, independent of the
        # task root (which may be a fixture tree).
        library_rsi = Path(__file__).resolve().parents[1] / 'library_rsi'
        sys.path.insert(0, str(library_rsi))
        import registry as task_registry
        self.registry = task_registry
        info = task_registry.load(task_id, root=root)
        self.task_id = task_id
        self.root = root
        self.info = info
        self.manifest = info['manifest']
        self.paths = info['paths']
        self.manifest_sha256 = info['manifest_sha256']
        self.protocol_sha256 = info['protocol_sha256']
        self.protocol = json.loads(self.paths['protocol'].read_text())
        self.objective = self.manifest.get('objective', '')
        self.candidate_file = self.manifest.get('candidate_file', 'artifact/program.py')
        self.diagnostic_file = 'artifact/diagnostic.py'
        self.seed_program = self.paths['seed']
        runtime = self.manifest.get('runtime', '')
        self.python = Path(sys.executable) if runtime in ('', 'inherit') else (root / runtime)

    # -- identity -------------------------------------------------------------
    def identity(self) -> dict:
        return {
            'task_id': self.task_id,
            'manifest_sha256': self.manifest_sha256,
            'protocol_sha256': self.protocol_sha256,
            'objective': self.objective,
            'seed_program_sha256': file_digest(self.seed_program),
        }

    def salt(self, which: str, config: dict) -> str:
        if self.task_id == 'dqi' and which == CONFIRMATION:
            # Same independent salt as the task-owned literature acceptance
            # entry point; no official protocol/scoring changes.
            from .dqi_adapter import FINAL_SALT
            return FINAL_SALT
        key = (config.get('validation', {}).get(
            'development_salt_key' if which == DEVELOPMENT else 'final_salt_key'))
        value = self.protocol.get(key if key else ('development_salt' if which == DEVELOPMENT else 'final_salt'))
        if not value:
            raise ToolInfrastructureError(f'Task protocol has no salt for {which}')
        return value

    def baseline_score(self) -> float:
        """Normalized baseline; the official calibration normalizes to 1.0."""
        return 1.0

    def attempt_artifact(self, attempt_dir):
        return Path(attempt_dir) / self.candidate_file

    # -- trusted execution wrappers -------------------------------------------
    def _task_module(self, name: str):
        """Import a task-side module once (its folder goes on sys.path first,
        because tasks like dfthcsos use plain `import evaluator`; the checkout's
        scripts/ is importable too, for shared utilities like runtime_queue)."""
        key = f'seeder_task_{self.task_id}_{name}'
        module = sys.modules.get(key)
        if module is not None:
            return module
        from . import ROOT
        scripts = ROOT / 'scripts'
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        task_dir = self.paths['protocol'].parent
        if str(task_dir) not in sys.path:
            sys.path.insert(0, str(task_dir))
        spec = importlib.util.spec_from_file_location(key, task_dir / (name + '.py'))
        if spec is None or spec.loader is None:
            raise ToolInfrastructureError(f'Task module missing: {name}')
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
        return module

    def _classify(self, exc: Exception):
        """Official-source corruption is infrastructure; a candidate that
        crashes, times out or exceeds memory is an experiment failure."""
        if isinstance(exc, ValueError) and ('Official source mismatch' in str(exc)
                                            or 'pinned' in str(exc)):
            raise ToolInfrastructureError(str(exc)) from exc
        return {'status': 'FAIL',
                'error': f'{type(exc).__name__}: {str(exc)[:4000]}',
                'official': {'status': 'FAIL'}}

    def run_diagnostic(self, attempt_dir, timeout_seconds: int = 300) -> dict:
        """Sandboxed own-code diagnostic. FAIL is an experiment outcome,
        not a job failure; infrastructure faults raise ToolInfrastructureError."""
        attempt = Path(attempt_dir).resolve()
        if self.task_id == 'dqi':
            from .dqi_adapter import diagnostic
            return diagnostic(self, attempt)
        diagnose = self._task_module('diagnose')
        try:
            receipt = diagnose.diagnose(attempt)
        except Exception as exc:
            receipt = self._classify(exc)
        if receipt.get('status') not in ('PASS', 'FAIL'):
            receipt['status'] = 'FAIL' if receipt.get('error') else 'PASS'
        receipt['diagnostic_only'] = True
        return receipt

    def run_validation(self, attempt_dir, output_dir, which: str, config: dict,
                       timeout_seconds: int = 4 * 3600,
                       submission_dir=None) -> dict:
        """Unchanged official verification of the attempt's frozen candidate.

        For confirmation, `submission_dir` must point at the exact frozen
        development submission: the independent check re-verifies those saved
        bytes under the final salt WITHOUT regenerating from source, because a
        real numerical refit can produce different bytes from identical
        source. Both receipts are preserved by the caller.
        """
        attempt = Path(attempt_dir).resolve()
        if self.task_id == 'dqi':
            from .dqi_adapter import validate
            return validate(self, attempt, output_dir, which, config, submission_dir)
        program = attempt / self.candidate_file
        output = Path(output_dir).resolve()
        if output.exists():
            raise ToolInfrastructureError(f'Validation output already exists: {output}')
        submission = Path(submission_dir).resolve() if submission_dir else None
        if which == CONFIRMATION:
            if submission is None or not submission.is_dir():
                raise ToolInfrastructureError(
                    'Confirmation requires the frozen development submission '
                    'directory; it must not regenerate from source')
        salt = self.salt(which, config)
        evaluator = self._task_module('evaluator')
        try:
            receipt = evaluator.evaluate_program(program, output, smoke=False,
                                                 salt=salt, submission=submission)
        except Exception as exc:
            receipt = self._classify(exc)
        if which == CONFIRMATION:
            # Envelope labels exactly as the task's library_validate --held-out uses.
            receipt['held_out'] = True
            receipt['scope'] = 'full-local-final'
            if submission is not None and receipt.get('status') == 'PASS':
                receipt['submission_reused'] = True
        else:
            receipt['scope'] = 'full-development'
        receipt['salt'] = salt
        return receipt

    # -- receipt trust -----------------------------------------------------------
    def validate_receipt(self, receipt: dict, level: str) -> None:
        self.registry.validate_receipt(self.task_id, receipt, level, root=self.root)

    def receipt_score(self, receipt: dict):
        """Normalized improvement ratio (baseline = 1.0) or None."""
        score = receipt.get('combined_score')
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            return None
        return float(score)

    def load_receipt(self, path):
        return json.loads(Path(path).read_text())


def load_adapter(task_id: str, root) -> TaskAdapter:
    return TaskAdapter(task_id, root)
