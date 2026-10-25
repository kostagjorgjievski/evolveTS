"""Acceptance tests for the scoped research knowledge layer.

Each test maps to a required proof from the R&D requirements:
1. A child receives its own parent's failed experiments and next actions.
2. Another branch cannot retrieve those records or derived advice pre-release.
3. Adding private information to branch A does not alter branch B's eligible
   research-package set.
4. Properly released findings become available at the level boundary.
5. Infrastructure corrections distribute without scientific-result leakage.
6. Missing Hermes findings never block an RSI attempt.
7. Every delivered handoff is frozen and auditable.

Plus provenance tainting (private input caps a package's audience forever,
even with public support) and direction-assignment diversity (metadata only).
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.autoresearch_seeder.knowledge import (KnowledgeBase,
                                                   KnowledgeError,
                                                   check_findings)

BRANCH_A_CODE = 'aaa000parentcode'
BRANCH_B_CODE = 'bbb111parentcode'


def make_base(tmp_path):
    return KnowledgeBase(tmp_path / 'research' / 'knowledge.sqlite')


def parent_for(code):
    return {'code_sha256': code, 'task': 'dfthcsos',
            'verified_score': 1.0,
            'open_questions': ['reduce symmetry-shift cost']}


def finding_sections(parent_code, level='diagnostic_supported', **extra):
    sections = {
        'mechanism': 'Symmetry-shift elimination via public solver X',
        'sources': ['https://example.org/solver-x'],
        'compatibility': {'applies_to_parents': True,
                          'parent_code_sha256': parent_code,
                          'task': 'dfthcsos'},
        'evidence': {'level': level,
                     'receipt_ids': ['exp-1'] if level == 'verified_seed' else []},
        'opportunity': {'expected_gain': 0.1, 'uncertainty': 0.4,
                        'risks': ['numerical stability']},
        'first_experiment': 'diagnostic: swap shift loop for solver X call',
    }
    sections.update(extra)
    return sections


# ---------------------------------------------------------------------------
# Proof 1 + 2: own-parent inheritance vs cross-branch invisibility
# ---------------------------------------------------------------------------

def seed_branch_history(base, branch, code, failed_reason, next_actions):
    """A branch's private history: a failed experiment + next actions."""
    failed = base.add('branch_private', {
        'kind': 'failed_experiment', 'reason': failed_reason,
        'code_sha256': code, 'next_actions': next_actions}, branch=branch)
    nxt = base.add('branch_private', {
        'kind': 'next_actions', 'items': next_actions}, branch=branch)
    return failed, nxt


def test_child_receives_own_parent_failures_and_next_actions(tmp_path):
    base = make_base(tmp_path)
    failed, nxt = seed_branch_history(
        base, 'branchA', BRANCH_A_CODE, 'solver X diverges on circuit 7',
        ['cap iterations at 40', 'try sparse factorization'])
    eligible = base.eligible_records('branchA', level=0)
    ids = {record['id'] for record in eligible}
    assert failed['id'] in ids and nxt['id'] in ids
    payloads = {record['id']: record['payload'] for record in eligible}
    assert payloads[failed['id']]['reason'] == 'solver X diverges on circuit 7'
    assert 'try sparse factorization' in payloads[nxt['id']]['items']


def test_other_branch_cannot_retrieve_records_or_derived_advice(tmp_path):
    base = make_base(tmp_path)
    seed_branch_history(base, 'branchA', BRANCH_A_CODE, 'secret failure A',
                        ['private next action A'])
    # A package DERIVED from branch A's private history...
    private_records = base.eligible_records('branchA', level=0)
    derived = base.add_finding(
        finding_sections(BRANCH_A_CODE),
        branch='branchA', inputs=[record['id'] for record in private_records],
        ready=True)
    # ...is invisible to branch B, as are the raw records.
    branch_b = base.eligible_records('branchB', level=0)
    assert branch_b == []
    findings_b = base.ready_findings('branchB', level=0, parent=parent_for(BRANCH_B_CODE))
    assert findings_b == []
    assert base.get(derived['id'])['audience'] != base.get(
        private_records[0]['id'])['audience'] or json.loads(
        base.get(derived['id'])['audience'])['branches'] == ['branchA']


# ---------------------------------------------------------------------------
# Proof 3: branch B's eligible package set is invariant to A's private data
# ---------------------------------------------------------------------------

def test_private_additions_do_not_alter_other_branch_eligible_set(tmp_path):
    base = make_base(tmp_path)
    public_direction = base.add('external', {
        'kind': 'direction', 'topic': 'solver X integration'})
    base.add_finding(finding_sections(None), level=0,
                     inputs=[public_direction['id']], ready=True)
    before = base.eligible_records('branchB', level=0)
    digest_before = base.eligible_digest('branchB', level=0)
    # Branch A now gains private records AND a private-input package.
    seed_branch_history(base, 'branchA', BRANCH_A_CODE, 'secret failure A', [])
    base.add_finding(finding_sections(BRANCH_A_CODE), branch='branchA',
                     inputs=[public_direction['id'],
                             base.eligible_records('branchA', 0)[0]['id']],
                     ready=True)
    assert base.eligible_records('branchB', level=0) == before
    assert base.eligible_digest('branchB', level=0) == digest_before


# ---------------------------------------------------------------------------
# Proof 4: release at the level boundary makes findings available
# ---------------------------------------------------------------------------

def test_released_findings_available_at_level_boundary(tmp_path):
    base = make_base(tmp_path)
    failed, _ = seed_branch_history(base, 'branchA', BRANCH_A_CODE,
                                    'documented failure A', [])
    finding = base.add_finding(finding_sections(BRANCH_A_CODE),
                               branch='branchA', inputs=[failed['id']],
                               ready=True)
    assert base.eligible_records('branchB', level=5) == []   # same level: private

    released = base.release(finding['id'], at_level=3)
    visible_b = base.ready_findings(
        'branchB', level=3, parent=parent_for(BRANCH_A_CODE))
    # The visible record is the level-scoped RELEASE copy; the original
    # package (and the raw failure it derived from) stay branch-A-private.
    assert [record['id'] for record in visible_b] == [released['id']]
    assert visible_b[0]['payload'] == finding['payload']
    # Below the boundary it stays invisible; the raw failure stays private.
    assert base.eligible_records('branchB', level=2) == []
    assert all(record['kind'] != 'branch_private'
               for record in base.eligible_records('branchB', level=9))
    assert all(record['id'] != finding['id']
               for record in base.eligible_records('branchB', level=9))


# ---------------------------------------------------------------------------
# Proof 5: infrastructure corrections distribute without science leakage
# ---------------------------------------------------------------------------

def test_infrastructure_correction_distribution(tmp_path):
    base = make_base(tmp_path)
    correction = base.add('infrastructure', {
        'component': 'dfthcsos evaluator', 'error_class': 'runtime_missing',
        'detail': 'venv python absent at .dfthcsos-venv — validation cannot start',
        'affected_versions': '>=0.1', 'workaround': 'run setup.sh',
        'confirmed_by': 'controller', 'confirmed_utc': '2026-10-25T00:00:00Z'})
    # Before controller review: invisible everywhere.
    assert base.eligible_records('branchB', level=0) == []
    base.review_infrastructure(correction['id'], reviewer='codex-controller')
    visible = base.eligible_records('branchB', level=0)
    assert [record['id'] for record in visible] == [correction['id']]
    # And the payload physically cannot carry scientific results:
    with pytest.raises(KnowledgeError, match='scientific'):
        base.add('infrastructure', {
            'component': 'evaluator', 'detail': 'fine',
            'confirmed_by': 'c', 'score': 4.2, 'method': 'solver X'})


def test_algorithmic_conclusion_is_not_an_api_correction(tmp_path):
    """An algorithm-specific conclusion cannot POSE as a neutral correction.

    The schema enforces the structural part: an infrastructure record has no
    field that can carry scores, methods, evidence or receipts, and any
    attempt to attach them is rejected. Prose-only conclusions ("solver X
    diverges") cannot be judged by a schema — that is exactly why
    distribution additionally requires explicit controller review
    (research-review), and a reviewer who approves science-laden prose as a
    'correction' is visible in the audit trail.
    """
    base = make_base(tmp_path)
    with pytest.raises(KnowledgeError, match='scientific'):
        base.add('infrastructure', {
            'component': 'evaluator', 'error_class': 'api',
            'detail': 'diverges', 'confirmed_by': 'c',
            'evidence': {'receipt': 'exp-9'}})
    with pytest.raises(KnowledgeError, match='scientific'):
        base.add('infrastructure', {
            'component': 'evaluator', 'detail': 'fine', 'confirmed_by': 'c',
            'scores': [1.2, 4.0]})
    with pytest.raises(KnowledgeError, match='confirmed_by'):
        base.add('infrastructure', {
            'component': 'evaluator', 'error_class': 'runtime_missing',
            'detail': 'venv missing'})   # unconfirmed fault: not even submittable
    clean = base.add('infrastructure', {
        'component': 'evaluator', 'error_class': 'runtime_missing',
        'detail': 'venv python absent', 'confirmed_by': 'controller'})
    assert set(clean['payload']) <= {
        'component', 'error_class', 'detail', 'affected_versions',
        'workaround', 'confirmed_utc', 'confirmed_by'}


# ---------------------------------------------------------------------------
# Proof 6: missing findings never block an attempt
# ---------------------------------------------------------------------------

def test_missing_knowledge_base_never_blocks(tmp_path):
    outcome = check_findings(tmp_path / 'does-not-exist', 'branchA', 0)
    assert outcome['blocked'] is False and outcome['findings'] == []
    # A corrupt base is equally nonblocking.
    broken = tmp_path / 'broken' / 'knowledge.sqlite'
    broken.parent.mkdir(parents=True)
    broken.write_text('not a database')
    outcome = check_findings(tmp_path / 'broken', 'branchA', 0)
    assert outcome['blocked'] is False and outcome['findings'] == []


def test_check_findings_returns_ready_findings_immediately(tmp_path):
    base = make_base(tmp_path)
    seed_branch_history(base, 'branchA', BRANCH_A_CODE, 'failure A', ['act'])
    finding = base.add_finding(finding_sections(BRANCH_A_CODE),
                               branch='branchA', ready=True)
    base.mark_ready(finding['id'])
    outcome = check_findings(tmp_path / 'research', 'branchA', 0,
                             parent=parent_for(BRANCH_A_CODE))
    assert outcome['blocked'] is False
    assert [record['id'] for record in outcome['findings']] == [finding['id']]
    sections = outcome['findings'][0]['payload']
    for required in ('mechanism', 'sources', 'compatibility', 'evidence',
                     'opportunity', 'first_experiment'):
        assert required in sections


def test_unscoped_or_foreign_findings_are_not_delivered(tmp_path):
    base = make_base(tmp_path)
    foreign = base.add_finding(finding_sections(BRANCH_B_CODE), level=0,
                               ready=True)   # different parent lineage
    unscoped = base.add('package', {'mechanism': 'x', 'sources': [],
                                    'compatibility': {}, 'evidence':
                                        {'level': 'diagnostic_supported',
                                         'receipt_ids': []},
                                    'opportunity': {}, 'first_experiment': 'y',
                                    'ready': True}, level=0)
    outcome = check_findings(tmp_path / 'research', 'branchA', 0,
                             parent=parent_for(BRANCH_A_CODE))
    ids = [record['id'] for record in outcome['findings']]
    assert foreign['id'] not in ids and unscoped['id'] not in ids


# ---------------------------------------------------------------------------
# Proof 7: delivered handoffs are frozen and auditable
# ---------------------------------------------------------------------------

def test_delivered_handoff_frozen_and_auditable(tmp_path):
    base = make_base(tmp_path)
    failed, _ = seed_branch_history(base, 'branchA', BRANCH_A_CODE,
                                    'failure A', ['next'])
    finding = base.add_finding(finding_sections(BRANCH_A_CODE),
                               branch='branchA', inputs=[failed['id']],
                               ready=True)
    attempt = tmp_path / 'attempts' / 'attempt_00' / 'record.json'
    attempt.parent.mkdir(parents=True)
    attempt.write_text('{}')
    delivery = base.deliver(finding['id'], str(attempt))
    assert delivery['delivered'] and not delivery['already_delivered']
    snapshot = Path(delivery['snapshot_path'])
    first_bytes = snapshot.read_bytes()
    again = base.deliver(finding['id'], str(attempt))
    assert again['already_delivered'] and again['snapshot_sha256'] \
        == delivery['snapshot_sha256']
    assert snapshot.read_bytes() == first_bytes   # frozen, not rewritten

    audit = base.deliveries(finding['id'])
    assert len(audit) == 1
    assert audit[0]['attempt_record'] == str(attempt)
    snapshot_json = json.loads(first_bytes)
    assert snapshot_json['record']['content_sha256'] == finding['content_sha256']
    assert finding['id'] in snapshot_json['record']['inputs'] or \
        failed['id'] in snapshot_json['record']['inputs']  # provenance chain
    # Not-ready findings cannot be delivered at all.
    draft = base.add_finding(finding_sections(BRANCH_A_CODE), branch='branchA')
    with pytest.raises(KnowledgeError, match='ready'):
        base.deliver(draft['id'], str(attempt))


# ---------------------------------------------------------------------------
# Provenance taint: public support never launders private inputs
# ---------------------------------------------------------------------------

def test_private_input_taints_package_forever(tmp_path):
    base = make_base(tmp_path)
    failed, _ = seed_branch_history(base, 'branchA', BRANCH_A_CODE,
                                    'private failure A', [])
    public_paper = base.add('external', {'kind': 'paper',
                                         'url': 'https://example.org/paper'})
    laundered = base.add_finding(
        finding_sections(BRANCH_A_CODE), branch='branchA',
        inputs=[failed['id'], public_paper['id']], ready=True)
    audience = json.loads(base.get(laundered['id'])['audience'])
    assert audience['branches'] == ['branchA'] and audience['tainted'] is True
    assert base.ready_findings('branchB', 9, parent=parent_for(BRANCH_A_CODE)) \
        == []   # even at a deep level, pre-release
    # The honest route is release at the boundary:
    base.release(laundered['id'], at_level=2)
    assert base.ready_findings('branchB', 2, parent=parent_for(BRANCH_A_CODE))


# ---------------------------------------------------------------------------
# Diversity: direction assignments are metadata-only
# ---------------------------------------------------------------------------

def test_direction_assignments_carry_no_outcomes(tmp_path):
    base = make_base(tmp_path)
    base.assign_direction('solver X integration', 'branchA', origin_record=None)
    base.assign_direction('solver X integration', 'branchB')  # repetition OK
    assignments = base.direction_assignments('solver X integration')
    assert {entry['branch'] for entry in assignments} == {'branchA', 'branchB'}
    for entry in assignments:
        assert set(entry) == {'direction', 'branch', 'assigned_utc',
                              'origin_record'}   # nowhere to hide outcomes
    # Assignments never change the eligible research-package set.
    digest_before = base.eligible_digest('branchB', 0)
    base.assign_direction('another direction', 'branchA')
    assert base.eligible_digest('branchB', 0) == digest_before


# ---------------------------------------------------------------------------
# Validation gates retained: claims are not measurements
# ---------------------------------------------------------------------------

def test_supported_direction_and_verified_seed_are_different_outputs(tmp_path):
    base = make_base(tmp_path)
    with pytest.raises(KnowledgeError, match='different outputs'):
        base.add_finding({'mechanism': 'x', 'sources': [],
                          'compatibility': {'applies_to_parents': True},
                          'evidence': {'level': 'hunch'},   # invalid class
                          'opportunity': {}, 'first_experiment': 'y'})
    with pytest.raises(KnowledgeError, match='receipt IDs'):
        base.add_finding(finding_sections(
            None, evidence={'level': 'verified_seed', 'receipt_ids': []}))
    verified = base.add_finding(
        finding_sections(None, level='verified_seed'), level=0)
    assert verified['payload']['evidence']['level'] == 'verified_seed'


def test_shared_scope_excludes_private_and_tainted(tmp_path):
    from scripts.autoresearch_seeder.investigations import eligible_knowledge
    base = make_base(tmp_path)
    seed_branch_history(base, 'branchA', BRANCH_A_CODE, 'private A', [])
    public = base.add('external', {'kind': 'paper'})
    shared_investigation = {'branch': None, 'level': 0}
    records = eligible_knowledge(base, shared_investigation)
    kinds = {record['id']: record['kind'] for record in records}
    assert public['id'] in kinds
    assert all(kind in ('external', 'released', 'infrastructure')
               for kind in kinds.values())   # no branch-private, no tainted
    branch_investigation = {'branch': 'branchA', 'level': 0}
    branch_records = eligible_knowledge(base, branch_investigation)
    assert any(record['kind'] == 'branch_private'
               for record in branch_records)   # own history included
