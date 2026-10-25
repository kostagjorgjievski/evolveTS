"""Scoped research knowledge base: provenance-enforced, branch-private by
construction.

Three information compartments, separated by storage and retrieval — never
by prompt instructions:

1. EXTERNAL research (public sources) — audience: everyone.
2. BRANCH-PRIVATE research context (code, discoveries, failed hypotheses,
   scores, summaries of one RSI branch within a level) — audience: that
   branch only, until explicitly released at a level/dreaming boundary.
3. RELEASED evidence — branch-private records promoted by an explicit
   controller release action at a level boundary; audience: every branch at
   that level or deeper.

Derived packages carry their input provenance: a package built from branch
A's private result stays branch-A-scoped FOREVER, even if the same mechanism
is later supported by a public paper (the private input taints the audience).
Infrastructure faults and neutral API corrections form a fourth, reviewable
category that can be distributed immediately AFTER controller review — their
payload schema physically cannot carry scientific results (no scores, no
methods), so distributing one leaks nothing scientific.

The MCP tool surface never bypasses this module: investigation and branch
sessions receive exactly what eligible_for() returns for their scope.
"""
import hashlib
import json
import sqlite3
from pathlib import Path

from .models import new_id, utc

SCHEMA = '''
CREATE TABLE IF NOT EXISTS records(
  id TEXT PRIMARY KEY, created_utc TEXT NOT NULL, kind TEXT NOT NULL,
  branch TEXT, level INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active', audience TEXT NOT NULL,
  payload TEXT NOT NULL, inputs TEXT NOT NULL DEFAULT '[]',
  content_sha256 TEXT NOT NULL, released_at_level INTEGER,
  review TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS deliveries(
  id INTEGER PRIMARY KEY, record_id TEXT NOT NULL, delivered_utc TEXT NOT NULL,
  attempt_record TEXT NOT NULL, snapshot_path TEXT NOT NULL,
  snapshot_sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS direction_assignments(
  direction TEXT NOT NULL, branch TEXT NOT NULL, assigned_utc TEXT NOT NULL,
  origin_record TEXT, PRIMARY KEY (direction, branch));
CREATE INDEX IF NOT EXISTS records_kind ON records(kind);
CREATE INDEX IF NOT EXISTS records_branch ON records(branch);
'''

# Payload fields an infrastructure correction may carry. Anything scientific
# (scores, methods, experiment outcomes) is rejected at write time, so a
# distributed correction cannot leak another branch's science.
INFRASTRUCTURE_FIELDS = frozenset(
    {'component', 'error_class', 'detail', 'affected_versions', 'workaround',
     'confirmed_utc', 'confirmed_by'})

# A ready finding/handoff package must state all five required sections.
FINDING_REQUIRED_FIELDS = ('mechanism', 'sources', 'compatibility',
                           'evidence', 'opportunity', 'first_experiment')


class KnowledgeError(ValueError):
    pass


def _content_digest(record: dict) -> str:
    canonical = json.dumps(
        {key: record.get(key) for key in
         ('kind', 'branch', 'level', 'payload', 'inputs')},
        sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


class KnowledgeBase:
    """Durable, scope-enforcing store; the ONLY path research records flow
    through. Default location is machine-local under the run root (never
    committed); `check_findings` treats a missing base as empty rather than
    blocking an attempt."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=30)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    # -- writes -------------------------------------------------------------

    def add(self, kind: str, payload: dict, *, branch: str = None, level: int = 0,
            inputs: list = None) -> dict:
        """Append a record; audience is COMPUTED, never caller-claimed.

        - external / released: level-scoped public.
        - branch_private: the named branch only (at this level and deeper).
        - infrastructure: public only after controller review.
        - package (finding/handoff): intersection of input audiences — any
          private input taints the package to that branch forever.
        """
        if kind not in ('external', 'branch_private', 'released',
                        'infrastructure', 'package'):
            raise KnowledgeError(f'unknown record kind {kind!r}')
        if kind == 'branch_private' and not branch:
            raise KnowledgeError('branch_private records require a branch')
        if kind == 'infrastructure':
            offending = sorted(set(payload or {}) - INFRASTRUCTURE_FIELDS)
            if offending:
                raise KnowledgeError(
                    'infrastructure corrections may not carry scientific '
                    'fields (found: ' + ', '.join(offending) + '); a fault '
                    'report with scores or methods is branch-private science')
            if not (payload or {}).get('confirmed_by'):
                raise KnowledgeError(
                    'infrastructure corrections require confirmed_by '
                    '(controller confirmation) before review')
        inputs = list(inputs or [])
        audience = self._computed_audience(kind, branch, level, inputs)
        record = {'id': new_id('kr'), 'kind': kind, 'branch': branch,
                  'level': int(level), 'status':
                      'pending_review' if kind == 'infrastructure' else 'active',
                  'audience': audience, 'payload': payload or {},
                  'inputs': inputs, 'created_utc': utc(),
                  'content_sha256': _content_digest(
                      {'kind': kind, 'branch': branch, 'level': level,
                       'payload': payload or {}, 'inputs': inputs})}
        self.db.execute(
            'INSERT INTO records(id, created_utc, kind, branch, level, status,'
            ' audience, payload, inputs, content_sha256, released_at_level,'
            ' review) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (record['id'], record['created_utc'], kind, branch, record['level'],
             record['status'], audience, json.dumps(record['payload']),
             json.dumps(inputs), record['content_sha256'], None, ''))
        self.db.commit()
        return record

    def _computed_audience(self, kind, branch, level, inputs) -> str:
        if kind == 'branch_private':
            return json.dumps({'branches': [branch], 'min_level': level,
                               'tainted': True})
        if kind == 'package':
            audiences = []
            for record_id in inputs:
                parent = self.get(record_id)
                if parent is None:
                    raise KnowledgeError(f'unknown input record {record_id}')
                audiences.append(json.loads(parent['audience']))
            if branch:
                # A package authored inside a branch's private session is
                # branch-scoped from birth, inputs or not.
                audiences.append({'branches': [branch], 'min_level': level,
                                  'tainted': True})
            if not audiences:
                return json.dumps({'branches': [], 'min_level': level,
                                   'tainted': False})   # public inputs only
            tainted_branches = sorted({branch_name for audience in audiences
                                       for branch_name in audience['branches']})
            if tainted_branches:
                # ANY private input (or origin) taints: the package stays
                # scoped to those branches even when public sources support
                # the same mechanism.
                return json.dumps({'branches': tainted_branches,
                                   'min_level': max(a['min_level'] for a
                                                    in audiences),
                                   'tainted': True})
            return json.dumps({'branches': [], 'min_level':
                                   max(a['min_level'] for a in audiences),
                               'tainted': False})
        # external / released / infrastructure: level-scoped public
        return json.dumps({'branches': [], 'min_level': level, 'tainted': False})

    def release(self, record_id: str, at_level: int) -> dict:
        """Controller-only promotion at a level/dreaming boundary.

        The original record stays untouched (audit); release appends a new
        level-scoped-public record whose inputs cite the original.
        """
        record = self.get(record_id)
        if record is None:
            raise KnowledgeError(f'unknown record {record_id}')
        if record['kind'] not in ('branch_private', 'package'):
            raise KnowledgeError('only branch_private records and derived '
                                 'packages are released')
        released = self.add('released', record['payload'],
                            level=int(at_level), inputs=[record_id])
        self.db.execute('UPDATE records SET status=? WHERE id=?',
                        (f'released_at_{int(at_level)}', record_id))
        self.db.commit()
        return released

    def review_infrastructure(self, record_id: str, reviewer: str) -> dict:
        """Controller review gate: a confirmed fault becomes distributable."""
        record = self.get(record_id)
        if record is None or record['kind'] != 'infrastructure':
            raise KnowledgeError('infrastructure record required')
        review = json.dumps({'reviewed_by': reviewer, 'reviewed_utc': utc()})
        self.db.execute('UPDATE records SET status=?, review=? WHERE id=?',
                        ('reviewed', review, record_id))
        self.db.commit()
        return dict(self.get(record_id), review=review)

    # -- reads --------------------------------------------------------------

    def get(self, record_id: str):
        row = self.db.execute(
            'SELECT id, created_utc, kind, branch, level, status, audience,'
            ' payload, inputs, content_sha256, released_at_level, review'
            ' FROM records WHERE id=?', (record_id,)).fetchone()
        if row is None:
            return None
        keys = ('id', 'created_utc', 'kind', 'branch', 'level', 'status',
                'audience', 'payload', 'inputs', 'content_sha256',
                'released_at_level', 'review')
        record = dict(zip(keys, row))
        record['payload'] = json.loads(record['payload'])
        record['inputs'] = json.loads(record['inputs'])
        record['level'] = int(record['level'])
        if record['released_at_level'] is not None:
            record['released_at_level'] = int(record['released_at_level'])
        return record

    def _eligible_where(self, branch: str, level: int):
        """Records a branch may see at a level.

        visible := external (level<=L)
                OR reviewed infrastructure
                OR released (level<=L)
                OR audience covers (branch in branches AND level>=min_level)
        branch_private records of OTHER branches are absent from the query
        result itself — separation is in storage/retrieval, not prompting.
        """
        rows = self.db.execute(
            'SELECT id, audience, level, status, kind, branch FROM records'
            ' WHERE status != "pending_review"').fetchall()
        eligible = []
        for record_id, audience_json, record_level, status, kind, branch_id in rows:
            audience = json.loads(audience_json)
            if kind == 'external' and record_level <= level:
                eligible.append(record_id)
            elif kind == 'infrastructure' and status == 'reviewed':
                eligible.append(record_id)
            elif kind == 'released' and record_level <= level:
                eligible.append(record_id)
            elif audience.get('tainted') or audience.get('branches'):
                if branch in audience.get('branches', []) \
                        and level >= audience.get('min_level', 0) \
                        and status.startswith(('active', 'released')):
                    eligible.append(record_id)
        return set(eligible)

    def eligible_records(self, branch: str, level: int) -> list:
        return [self.get(record_id)
                for record_id in sorted(self._eligible_where(branch, level))]

    def eligible_digest(self, branch: str, level: int) -> str:
        record_ids = sorted(self._eligible_where(branch, level))
        return hashlib.sha256('\n'.join(record_ids).encode()).hexdigest()

    # -- direction assignments (diversity without outcome leakage) ----------

    def assign_direction(self, direction: str, branch: str,
                         origin_record: str = None) -> dict:
        """Metadata-only distribution of externally sourced directions.

        Records WHICH branch was assigned a direction to reduce accidental
        duplication. It never carries outcomes, scores or method results —
        by schema there is nowhere to put them.
        """
        entry = {'direction': direction, 'branch': branch,
                 'assigned_utc': utc(), 'origin_record': origin_record}
        self.db.execute(
            'INSERT OR REPLACE INTO direction_assignments'
            '(direction, branch, assigned_utc, origin_record)'
            ' VALUES (?,?,?,?)',
            (direction, branch, entry['assigned_utc'], origin_record))
        self.db.commit()
        return entry

    def direction_assignments(self, direction: str = None) -> list:
        if direction:
            rows = self.db.execute(
                'SELECT direction, branch, assigned_utc, origin_record FROM'
                ' direction_assignments WHERE direction=? ORDER BY assigned_utc',
                (direction,)).fetchall()
        else:
            rows = self.db.execute(
                'SELECT direction, branch, assigned_utc, origin_record FROM'
                ' direction_assignments ORDER BY assigned_utc').fetchall()
        return [dict(zip(('direction', 'branch', 'assigned_utc',
                          'origin_record'), row)) for row in rows]

    # -- findings (handoff packages) ----------------------------------------

    def add_finding(self, sections: dict, *, branch: str = None, level: int = 0,
                    inputs: list = None, ready: bool = False) -> dict:
        """A handoff package; every required section must be present.

        Evidence sections must reference receipt IDs for anything presented
        as a measurement — model claims are not measurements, and a
        supported direction (diagnostic-level evidence) is a different
        output class than a fully verified seed (official receipts under
        both salts). The package records which class it is via
        payload.evidence.level: 'diagnostic_supported' | 'verified_seed'.
        """
        missing = [field for field in FINDING_REQUIRED_FIELDS
                   if field not in (sections or {})]
        if missing:
            raise KnowledgeError('finding missing sections: '
                                 + ', '.join(missing))
        evidence = sections.get('evidence') or {}
        if evidence.get('level') not in ('diagnostic_supported', 'verified_seed'):
            raise KnowledgeError(
                "evidence.level must be 'diagnostic_supported' or "
                "'verified_seed'; supported directions and verified seeds "
                "are different outputs")
        if evidence.get('level') == 'verified_seed' \
                and not evidence.get('receipt_ids'):
            raise KnowledgeError('a verified-seed finding must cite receipt IDs')
        payload = dict(sections)
        payload['ready'] = bool(ready)
        return self.add('package', payload, branch=branch, level=level,
                        inputs=inputs)

    def mark_ready(self, record_id: str) -> dict:
        record = self.get(record_id)
        if record is None or record['kind'] != 'package':
            raise KnowledgeError('finding record required')
        payload = dict(record['payload'], ready=True)
        self.db.execute('UPDATE records SET payload=? WHERE id=?',
                        (json.dumps(payload), record_id))
        self.db.commit()
        return self.get(record_id)

    def ready_findings(self, branch: str, level: int,
                       parent: dict = None) -> list:
        """Ready, eligible packages compatible with a parent attempt context.

        Compatibility filtering uses the package's own compatibility section
        against the parent's code hash, task, verified score and open
        questions — a package for a different lineage is not handed over.
        """
        results = []
        for record in self.eligible_records(branch, level):
            # A released copy of a finding keeps its payload (with ready=True)
            # under kind 'released' — both shapes are deliverable.
            if record['kind'] not in ('package', 'released') \
                    or not record['payload'].get('ready'):
                continue
            if not self._compatible(record['payload'].get('compatibility'),
                                    parent or {}):
                continue
            results.append(record)
        return results

    @staticmethod
    def _compatible(compatibility: dict, parent: dict) -> bool:
        if not compatibility:
            return False   # an unscoped package is never auto-delivered
        if not compatibility.get('applies_to_parents'):
            return False
        code_hash = compatibility.get('parent_code_sha256')
        if code_hash and parent.get('code_sha256') \
                and code_hash != parent['code_sha256']:
            return False
        task = compatibility.get('task')
        if task and parent.get('task') and task != parent['task']:
            return False
        return True

    def deliver(self, record_id: str, attempt_record: str) -> dict:
        """Freeze a handoff into an attempt record; auditable, idempotent."""
        record = self.get(record_id)
        if record is None or record['kind'] != 'package':
            raise KnowledgeError('finding record required')
        if not record['payload'].get('ready'):
            raise KnowledgeError('only ready findings can be delivered')
        existing = self.db.execute(
            'SELECT snapshot_path, snapshot_sha256 FROM deliveries WHERE'
            ' record_id=? AND attempt_record=?',
            (record_id, str(attempt_record))).fetchone()
        if existing:
            return {'delivered': True, 'already_delivered': True,
                    'snapshot_path': existing[0],
                    'snapshot_sha256': existing[1]}
        snapshot_path = Path(attempt_record).parent \
            / (Path(attempt_record).stem + '-finding-'
               + record_id + '.json')
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = {'record': {key: record[key] for key in
                               ('id', 'kind', 'branch', 'level', 'payload',
                                'inputs', 'content_sha256', 'created_utc')},
                    'delivered_utc': utc(),
                    'attempt_record': str(attempt_record)}
        text = json.dumps(snapshot, indent=2, sort_keys=True) + '\n'
        snapshot_path.write_text(text)
        snapshot_sha256 = hashlib.sha256(text.encode()).hexdigest()
        self.db.execute(
            'INSERT INTO deliveries(record_id, delivered_utc, attempt_record,'
            ' snapshot_path, snapshot_sha256) VALUES (?,?,?,?,?)',
            (record_id, snapshot['delivered_utc'], str(attempt_record),
             str(snapshot_path), snapshot_sha256))
        self.db.commit()
        return {'delivered': True, 'already_delivered': False,
                'snapshot_path': str(snapshot_path),
                'snapshot_sha256': snapshot_sha256}

    def deliveries(self, record_id: str = None) -> list:
        if record_id:
            rows = self.db.execute(
                'SELECT record_id, delivered_utc, attempt_record,'
                ' snapshot_path, snapshot_sha256 FROM deliveries WHERE'
                ' record_id=? ORDER BY delivered_utc', (record_id,)).fetchall()
        else:
            rows = self.db.execute(
                'SELECT record_id, delivered_utc, attempt_record,'
                ' snapshot_path, snapshot_sha256 FROM deliveries ORDER BY'
                ' delivered_utc').fetchall()
        return [dict(zip(('record_id', 'delivered_utc', 'attempt_record',
                          'snapshot_path', 'snapshot_sha256'), row))
                for row in rows]


def check_findings(knowledge_root, branch: str, level: int,
                   parent: dict = None, attempt_record: str = None) -> dict:
    """Nonblocking attempt-boundary check (requirement: never wait, never fail).

    Returns immediately with ready findings for THIS branch's parent context;
    a missing or broken knowledge base yields an empty result and the attempt
    proceeds. Selected findings are frozen into the attempt record for
    reproducibility; the worker may still reject the advice.
    """
    try:
        base = KnowledgeBase(Path(knowledge_root) / 'knowledge.sqlite')
        try:
            findings = base.ready_findings(branch, level, parent=parent)
            delivered = []
            if attempt_record:
                for finding in findings:
                    delivered.append(base.deliver(finding['id'], attempt_record))
        finally:
            base.close()
        return {'blocked': False, 'findings': findings, 'delivered': delivered}
    except Exception as failure:   # research must never block an RSI attempt
        return {'blocked': False, 'findings': [], 'delivered': [],
                'note': f'knowledge base unavailable ({failure.__class__.__name__}'
                        f'); attempt proceeds without research findings'}
