"""Autonomous research agenda tests: durable investigations, checkpoints,
finite budgets, auto-shelving, scoped session prompts, and the scheduler's
idle research path (eligibility without model calls).
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.autoresearch_seeder.investigations import (Investigations,
                                                        eligible_knowledge,
                                                        investigation_prompt,
                                                        run_investigation_session)
from scripts.autoresearch_seeder.knowledge import KnowledgeBase
from scripts.autoresearch_seeder.scheduler import run_once, schedule
from scripts.autoresearch_seeder.transport import FakeTransport


def make_stack(tmp_path):
    root = tmp_path / 'research'
    return root, KnowledgeBase(root / 'knowledge.sqlite'), \
        Investigations(root / 'investigations.sqlite')


def test_agenda_next_eligible_is_pure_storage(tmp_path):
    root, base, agenda = make_stack(tmp_path)
    assert agenda.next_eligible() is None   # empty agenda: no model calls
    low = agenda.create('survey symmetry shifts', priority=1)
    high = agenda.create('investigate solver X', priority=5)
    assert agenda.next_eligible()['id'] == high['id']
    agenda.shelve(high['id'], 'test')
    assert agenda.next_eligible()['id'] == low['id']


def test_budget_exhaustion_auto_shelves(tmp_path):
    root, base, agenda = make_stack(tmp_path)
    investigation = agenda.create('bounded topic',
                                  budgets={'max_sessions': 1,
                                           'max_model_seconds': 600,
                                           'max_usd': 5.0})
    updated = agenda.record_session(investigation['id'], model_seconds=120.0,
                                    usd=0.5)
    assert updated['status'] == 'shelved'
    assert updated['shelve_reason'] == 'session budget exhausted'
    assert updated['consumed'] == {'sessions': 1, 'model_seconds': 120.0,
                                   'usd': 0.5}
    assert agenda.next_eligible() is None   # spent investigations never spin


def test_stale_checkpoint_auto_shelves(tmp_path):
    root, base, agenda = make_stack(tmp_path)
    investigation = agenda.create('repeated topic')
    first = agenda.record_session(investigation['id'], model_seconds=10.0,
                                  activity_digest='same-activity')
    assert first['status'] == 'active'
    second = agenda.record_session(investigation['id'], model_seconds=10.0,
                                   activity_digest='same-activity')
    assert second['status'] == 'active'   # one repeat is not yet unproductive
    third = agenda.record_session(investigation['id'], model_seconds=10.0,
                                  activity_digest='same-activity')
    assert third['status'] == 'shelved'
    assert 'no new activity' in third['shelve_reason']
    # New activity earlier would have reset the counter:
    other = agenda.create('productive topic')
    agenda.record_session(other['id'], model_seconds=10.0,
                          activity_digest='digest-1')
    productive = agenda.record_session(other['id'], model_seconds=10.0,
                                       activity_digest='digest-2')
    assert productive['status'] == 'active'


def test_checkpoints_survive_across_sessions(tmp_path):
    root, base, agenda = make_stack(tmp_path)
    investigation = agenda.create('multi-session topic')
    agenda.record_session(investigation['id'], model_seconds=10.0,
                          checkpoint_update={'notes': 'found solver X paper',
                                             'next_actions': ['reproduce fig 3']})
    resumed = agenda.get(investigation['id'])
    assert resumed['checkpoint']['notes'] == 'found solver X paper'
    assert resumed['checkpoint']['next_actions'] == ['reproduce fig 3']
    prompt = investigation_prompt(resumed, [])
    assert 'found solver X paper' in prompt
    assert 'reproduce fig 3' in prompt


def test_shared_prompt_excludes_branch_private(tmp_path):
    root, base, agenda = make_stack(tmp_path)
    base.add('branch_private', {'kind': 'failed_experiment',
                                'reason': 'branch A secret'}, branch='branchA')
    public = base.add('external', {'kind': 'paper',
                                   'url': 'https://example.org/p'})
    shared = agenda.create('shared topic')
    records = eligible_knowledge(base, agenda.get(shared['id']))
    ids = {record['id'] for record in records}
    assert public['id'] in ids
    assert all('branch A secret' not in json.dumps(record['payload'])
               for record in records)
    prompt = investigation_prompt(agenda.get(shared['id']), records)
    assert 'branch A secret' not in prompt
    assert 'shared external context' in prompt


def test_branch_prompt_includes_own_private_only(tmp_path):
    root, base, agenda = make_stack(tmp_path)
    base.add('branch_private', {'kind': 'failed_experiment',
                                'reason': 'branch A secret'}, branch='branchA')
    base.add('branch_private', {'kind': 'failed_experiment',
                                'reason': 'branch B secret'}, branch='branchB')
    scoped = agenda.create('branch topic', branch='branchB')
    prompt = investigation_prompt(agenda.get(scoped['id']),
                                  eligible_knowledge(base, agenda.get(scoped['id'])))
    assert 'branch B secret' in prompt
    assert 'branch A secret' not in prompt


def test_run_investigation_session_accounts_and_checkpoints(tmp_path):
    root, base, agenda = make_stack(tmp_path)
    investigation = agenda.create('driver topic')
    transport = FakeTransport([{'finish': 'done'}])
    updated = run_investigation_session(agenda, investigation['id'],
                                        transport, base)
    assert updated['consumed']['sessions'] == 1
    assert updated['consumed']['model_seconds'] > 0
    assert updated['checkpoint']['last_finished_reason'] == 'done'
    assert (root / 'investigations' / investigation['id'] / 'private'
            / 'prompt.txt').is_file()


def test_scheduler_idle_research_path(tmp_path):
    root, base, agenda = make_stack(tmp_path)
    runs = tmp_path / 'runs'
    runs.mkdir()

    # Idle with research disabled: plain idle outcome, transport untouched.
    def forbidden(provider):
        raise AssertionError('disabled research must not build a transport')
    outcome = run_once(runs, research={'enabled': False,
                                       'root': str(root),
                                       'transport_factory': forbidden})
    assert outcome['started'] is None and 'no model calls' in outcome['reason']

    # Idle with an empty enabled agenda: still no model calls.
    outcome = run_once(runs, research={'enabled': True, 'root': str(root),
                                       'transport_factory': forbidden})
    assert outcome['started'] is None and 'no model calls' in outcome['reason']

    # Eligible investigation: exactly one bounded session runs.
    investigation = agenda.create('scheduled topic')
    transport = FakeTransport([{'finish': 'done'}])
    outcome = run_once(runs, research={
        'enabled': True, 'root': str(root),
        'transport_factory': lambda provider: transport,
        'budgets': {'session_seconds': 60}})
    assert outcome['investigation_session'] == investigation['id']
    assert outcome['investigation_status'] == 'active'
    assert agenda.get(investigation['id'])['consumed']['sessions'] == 1

    # The bounded loop stops on idle rather than spinning.
    outcomes = schedule(runs, loop_passes=4, sleep_seconds=0.0,
                        research={'enabled': True, 'root': str(root),
                                  'transport_factory': lambda p: FakeTransport([])})
    assert len(outcomes) == 1


def test_shipped_research_example_config_is_disabled_and_loadable():
    from scripts.autoresearch_seeder.__main__ import _load_research_config
    config = _load_research_config(
        REPO / 'configs' / 'hermes_research.example.json')
    assert config['enabled'] is False   # ships disabled, like every arm
    assert config['provider']['backend'] in ('claude_code', 'hermes')
    assert config['budgets']['session_seconds'] > 0


def test_jobs_take_priority_over_research(tmp_path):
    from scripts.autoresearch_seeder.testing import E2E_SCRIPT, build_job
    controller = build_job(tmp_path, E2E_SCRIPT)
    run_root = controller.job_dir.parents[2]
    root, base, agenda = make_stack(tmp_path)
    investigation = agenda.create('background topic')
    transport = controller.shared_transport
    from scripts.autoresearch_seeder.testing import FakeSearch, fake_fetcher
    outcome = run_once(run_root,
                       transport_factory=lambda cfg: transport,
                       search_service=FakeSearch(),
                       fetcher=fake_fetcher(controller.job_dir, controller.config),
                       research={'enabled': True, 'root': str(root),
                                 'transport_factory': lambda p: pytest.fail(
                                     'job path must take priority')})
    assert outcome['started'] == str(controller.job_dir)
    assert agenda.get(investigation['id'])['consumed']['sessions'] == 0
