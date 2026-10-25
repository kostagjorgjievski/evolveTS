"""Bounded scheduler: run eligible queued work once, never as a daemon.

Eligibility is a pure filesystem check (job.json stage + retry deadline +
config enabled) — waking costs zero model calls. Starting a job goes through
the controller's lease claim, so concurrent schedulers cannot double-start,
and terminal jobs (rejected, budget_exhausted, completed_no_improvement,
seed_ready, cancelled, infrastructure_blocked) are never picked up again.

Disabled by default: `scheduling.enabled` must be true in the job's config.
The default invocation is a single pass; `--loop` adds a bounded number of
passes with a sleep between them and exits as soon as no eligible work
remains. Nothing here installs seeds into campaigns or enables production.
"""
import json
import time
from pathlib import Path

from .models import JobBusy, utc

TERMINAL_STAGES = frozenset({
    'seed_ready', 'completed_no_improvement', 'rejected', 'cancelled',
    'budget_exhausted', 'infrastructure_blocked', 'needs_access'})

# Stages a scheduler may start. `queued` is a never-started job;
# `retry_wait` becomes eligible once its deadline passes.
STARTABLE_STAGES = frozenset({'queued', 'retry_wait'})


def discover_jobs(run_root) -> list:
    """All seeder job directories under a run root, oldest first."""
    root = Path(run_root) / 'autoresearch-seeder'
    if not root.is_dir():
        return []
    jobs = []
    for job_json in sorted(root.glob('*/*/job.json')):
        jobs.append(job_json.parent)
    return jobs


def job_eligibility(job_dir, now=None) -> dict:
    """Eligibility decision from durable state only — no model calls.

    A job is eligible when its stage is startable, its config is enabled for
    live runs, and any retry deadline has passed. Terminal and active stages
    (researching, implementing, ...) are never eligible: an active job belongs
    to its owning process, and a finished job must not be repeated.
    """
    job_dir = Path(job_dir)
    try:
        job = json.loads((job_dir / 'job.json').read_text())
    except (OSError, ValueError) as exc:
        return {'job': str(job_dir), 'eligible': False, 'reason': f'unreadable job.json: {exc}'}
    stage = job.get('stage')
    reason = ''
    if stage in TERMINAL_STAGES:
        reason = f'terminal stage {stage}'
    elif stage not in STARTABLE_STAGES:
        reason = f'stage {stage} not startable by scheduler'
    elif not job.get('enabled'):
        reason = 'config disabled (enabled=false)'
    elif stage == 'retry_wait':
        retry = job.get('retry') or {}
        deadline = retry.get('eligible_utc', '')
        if deadline and (now or utc()) < deadline:
            reason = f'retry deadline {deadline} not passed'
    if reason:
        return {'job': str(job_dir), 'eligible': False, 'reason': reason}
    return {'job': str(job_dir), 'eligible': True, 'reason': f'stage {stage}',
            'task': job.get('task')}


def eligible_jobs(run_root, now=None) -> list:
    return [entry for entry in (job_eligibility(job, now=now)
                                for job in discover_jobs(run_root))
            if entry['eligible']]


def run_once(run_root, now=None, transport_factory=None,
             search_service=None, fetcher=None, research=None) -> dict:
    """Start the single oldest eligible job; returns what happened.

    Duplicate starts are impossible: the controller's lease claim rejects a
    second owner while one is live, and JobBusy is reported as a skip, not an
    error, so a concurrent scheduler pass stays bounded. When no seeder job
    is eligible and a research agenda is enabled, one investigation session
    may run instead — the eligibility checks themselves stay pure storage
    reads either way. The injection parameters exist for deterministic tests;
    production passes none.
    """
    from .__main__ import _load_controller, _transport_factory_for
    candidates = eligible_jobs(run_root, now=now)
    if not candidates:
        outcome = _maybe_research_session(research)
        if outcome is not None:
            return outcome
        return {'started': None, 'eligible': 0,
                'reason': 'no eligible work (idle check made no model calls)'}
    entry = candidates[0]
    import argparse
    args = argparse.Namespace(job=entry['job'])
    factory = transport_factory or _transport_factory_for(args)
    controller, job, config = _load_controller(
        entry['job'], transport_factory=factory,
        search_service=search_service, fetcher=fetcher)
    if not config.get('enabled'):
        # The durable job record said enabled, but the config has since been
        # disabled — the live config wins; never start a disabled paid run.
        return {'started': None, 'eligible': len(candidates),
                'skipped_disabled': entry['job'],
                'reason': 'config disabled at start time (enabled=false)'}
    try:
        controller.resume()
        outcome = {'started': entry['job'], 'eligible': len(candidates),
                   'stage': controller.job_state().get('stage'),
                   'terminal': controller.job_state().get('terminal')}
    except JobBusy as busy:
        return {'started': None, 'eligible': len(candidates),
                'skipped_busy': entry['job'], 'reason': str(busy)}
    controller.finalize_segment()
    return outcome


def _maybe_research_session(research) -> dict:
    """Idle research path: agenda consulted first (no model calls), then at
    most one bounded investigation session. Returns None when research is
    disabled or nothing is eligible, so the plain idle outcome stands."""
    if not (research or {}).get('enabled'):
        return None
    from .investigations import Investigations, run_investigation_session
    from .knowledge import KnowledgeBase
    root = Path(research['root'])
    investigations = Investigations(root / 'investigations.sqlite')
    knowledge = KnowledgeBase(root / 'knowledge.sqlite')
    try:
        investigation = investigations.next_eligible()
        if investigation is None:
            return None   # agenda empty/spent: plain idle outcome
        session_budget = float((research.get('budgets') or {})
                               .get('session_seconds', 1200.0))
        transport = research['transport_factory'](research.get('provider', {}))
        updated = run_investigation_session(
            investigations, investigation['id'], transport, knowledge,
            budget_seconds=session_budget)
        return {'started': None, 'eligible': 0,
                'investigation_session': investigation['id'],
                'investigation_status': updated['status'],
                'reason': 'no eligible job; ran one investigation session'}
    finally:
        investigations.close()
        knowledge.close()


def schedule(run_root, *, loop_passes: int = 1, sleep_seconds: float = 300.0,
             now=None, research=None) -> list:
    """Bounded scheduling: at most `loop_passes` passes, stop when idle.

    Each pass starts at most one job. The loop exits early when a pass finds
    no eligible work — absence of eligible work is a stop condition, not a
    reason to spin. This is deliberately not a daemon.
    """
    outcomes = []
    for index in range(max(1, int(loop_passes))):
        outcome = run_once(run_root, now=now, research=research)
        outcomes.append(outcome)
        if not outcome.get('started') and not outcome.get('skipped_busy'):
            break   # no eligible work: stop instead of spinning
        if outcome.get('skipped_busy') and not outcome.get('started'):
            break   # the only candidate is owned by a live process; nothing to do
        if index + 1 < loop_passes:
            time.sleep(max(0.0, sleep_seconds))
    return outcomes
