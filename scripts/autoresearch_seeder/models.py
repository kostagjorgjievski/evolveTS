"""Stable entities, canonical JSON, and immutable artifact freezing."""
from dataclasses import dataclass, field, asdict
import datetime
import hashlib
import json
import os
import stat
from pathlib import Path
import uuid

# An artifact bundle stays small enough to hash and freeze in one pass.
BUNDLE_MAX_FILES = 4096
BUNDLE_MAX_BYTES = 128 * 2**20


def utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_digest(path) -> str:
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def new_id(prefix: str) -> str:
    return f'{prefix}-{uuid.uuid4().hex[:16]}'


def atomic_write(path, text: str) -> None:
    """Crash-safe write: a reader never observes a partial file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '.tmp')
    with temporary.open('w') as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def bundle_hash(directory) -> str:
    """Deterministic hash over every regular file under directory.

    Ordinary nested helper directories are allowed — a candidate may package
    vendored modules in subfolders. Symlinks (including directory symlinks),
    hard-linked files and special files are rejected exactly like the task
    sandboxes reject them, so a frozen bundle cannot silently change meaning.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError('Bundle directory required')
    if directory.is_symlink():
        raise ValueError('Bundle root may not be a symlink')
    entries = []
    total = 0
    for path in sorted(directory.rglob('*')):
        relative = path.relative_to(directory).as_posix()
        info = path.lstat()
        if path.is_symlink():
            raise ValueError('Bundle symlinks forbidden: ' + relative)
        if stat.S_ISDIR(info.st_mode):
            continue          # ordinary directory: descend into it
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('Bundle hard links/special files forbidden: ' + relative)
        total += info.st_size
        if total > BUNDLE_MAX_BYTES:
            raise ValueError('Bundle exceeds 128 MiB')
        if len(entries) >= BUNDLE_MAX_FILES:
            raise ValueError('Bundle exceeds 4096 files')
        entries.append([relative, info.st_size, file_digest(path)])
    if not entries:
        raise ValueError('Empty bundle')
    return digest(entries)


class ToolInfrastructureError(RuntimeError):
    """Sandbox/queue/system fault. Never a scored candidate failure."""


class ProviderRateLimit(RuntimeError):
    """Provider throttling or transient 5xx; retry after a bounded wait."""


class ProviderRefused(RuntimeError):
    """Credentials/quota/model access refusal; not retryable in-place."""


class BudgetExhausted(RuntimeError):
    """A configured finite budget was consumed."""


class JobBusy(RuntimeError):
    """Another live owner holds the job lease."""


@dataclass
class Source:
    url: str
    kind: str                      # paper | code | notebook | search | other
    content_sha256: str = ''
    revision: str = ''             # commit/tag when the host provides one
    status: str = 'pending'        # pending | accessed | blocked | vanished
    license: str = 'unknown'
    attribution: str = ''
    relevance: str = ''
    access_limitation: str = ''
    local_path: str = ''
    bytes: int = 0
    retrieved_utc: str = ''
    provenance: dict = field(default_factory=dict)

    def record(self) -> dict:
        return asdict(self)


@dataclass
class Hypothesis:
    mechanism: str
    family: str = ''
    source_ids: list = field(default_factory=list)
    affected_cost_terms: list = field(default_factory=list)
    compatibility_assumptions: str = ''
    expected_opportunity: dict = field(default_factory=dict)   # must carry label 'prediction'
    first_test: str = ''
    rejection_conditions: str = ''
    may_replace_inherited_architecture: bool = False
    status: str = 'active'         # active | testing | rejected | superseded
    created_utc: str = field(default_factory=utc)
    id: str = field(default_factory=lambda: new_id('hyp'))

    def record(self) -> dict:
        data = asdict(self)
        return data


@dataclass
class Experiment:
    kind: str                      # diagnostic | development_validation | confirmation_validation
    hypothesis_id: str = ''
    requested_action: str = ''
    tool_invocation: dict = field(default_factory=dict)
    input_bundle_sha256: str = ''
    params: dict = field(default_factory=dict)   # salt/scope/shots...
    status: str = 'pending'        # pending | pass | fail | error | infra_blocked
    exit_status: str = ''
    receipt: dict = field(default_factory=dict)
    receipt_sha256: str = ''
    metrics: dict = field(default_factory=dict)
    conclusion: str = ''
    log_excerpt: str = ''
    log_path: str = ''
    started_utc: str = ''
    finished_utc: str = ''
    wall_seconds: float = 0.0
    engine_seconds: float = 0.0
    queue_wait_seconds: float = 0.0
    id: str = ''

    def record(self) -> dict:
        return asdict(self)


@dataclass
class Decision:
    action: str                    # continue | refine | pivot | reject
    experiment_ids: list = field(default_factory=list)
    next_action: str = ''
    notes: str = ''
    created_utc: str = field(default_factory=utc)
    id: str = field(default_factory=lambda: new_id('dec'))

    def record(self) -> dict:
        return asdict(self)


def experiment_id(kind: str, task_protocol_sha256: str, bundle_sha256: str, params: dict) -> str:
    """Idempotency key: identical frozen inputs and settings reuse the result."""
    return digest({'kind': kind, 'protocol': task_protocol_sha256,
                   'bundle': bundle_sha256, 'params': canonical(params)})
