"""Job-scoped durable research store: sources, hypotheses, experiments, decisions.

This store is the seeder's own research memory and is deliberately separate
from the verified-method library (scripts/library_rsi/store.py): job and
experiment bookkeeping must never masquerade as curated, verified methods.
Records are immutable once written; revisions append rather than replace.
"""
import json
import sqlite3
from pathlib import Path

from .models import canonical, digest, utc

SCHEMA = '''
CREATE TABLE IF NOT EXISTS sources(
  url TEXT PRIMARY KEY, latest_content_sha256 TEXT, status TEXT NOT NULL,
  first_seen_utc TEXT NOT NULL, last_retrieved_utc TEXT, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_revisions(
  id TEXT PRIMARY KEY, url TEXT NOT NULL, content_sha256 TEXT NOT NULL,
  retrieved_utc TEXT NOT NULL, local_path TEXT, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS hypotheses(id TEXT PRIMARY KEY, created_utc TEXT NOT NULL,
  status TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS experiments(id TEXT PRIMARY KEY, created_utc TEXT NOT NULL,
  kind TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY, created_utc TEXT NOT NULL,
  action TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, created_utc TEXT NOT NULL,
  kind TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS budget_ledger(id INTEGER PRIMARY KEY, created_utc TEXT NOT NULL,
  category TEXT NOT NULL, seconds REAL NOT NULL DEFAULT 0, usd REAL NOT NULL DEFAULT 0,
  tool_calls INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS experiments_kind ON experiments(kind);
CREATE INDEX IF NOT EXISTS source_revisions_url ON source_revisions(url);
'''


class ResearchStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=30)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    # -- sources -----------------------------------------------------------
    def record_source(self, source: dict) -> dict:
        """Insert or update a source; a changed content hash appends a revision.

        Returns {'source':..., 'new_revision': bool, 'revisions': n} so callers
        can tell 'fetched again, unchanged' from 'external content changed'.
        """
        url = source['url']
        content = source.get('content_sha256', '')
        with self.db:
            row = self.db.execute('SELECT payload FROM sources WHERE url=?', (url,)).fetchone()
            new_revision = not row or json.loads(row[0]).get('content_sha256') != content
            revision_id = digest({'url': url, 'content': content}) if content else None
            if revision_id:
                payload = canonical({'url': url, 'content_sha256': content,
                                     'retrieved_utc': source.get('retrieved_utc', utc()),
                                     'local_path': source.get('local_path', ''),
                                     'bytes': source.get('bytes', 0),
                                     'revision': source.get('revision', '')})
                self.db.execute('INSERT OR IGNORE INTO source_revisions VALUES (?,?,?,?,?,?)',
                                (revision_id, url, content, source.get('retrieved_utc', utc()),
                                 source.get('local_path', ''), payload))
            if row:
                self.db.execute('UPDATE sources SET latest_content_sha256=?, status=?, '
                                'last_retrieved_utc=?, payload=? WHERE url=?',
                                (content, source.get('status', 'pending'),
                                 source.get('retrieved_utc', utc()), canonical(source), url))
            else:
                self.db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?)',
                                (url, content, source.get('status', 'pending'), utc(),
                                 source.get('retrieved_utc'), canonical(source)))
            count = self.db.execute('SELECT COUNT(*) FROM source_revisions WHERE url=?',
                                    (url,)).fetchone()[0]
        return {'source': source, 'new_revision': new_revision, 'revisions': count}

    def get_source(self, url: str):
        row = self.db.execute('SELECT payload FROM sources WHERE url=?', (url,)).fetchone()
        return json.loads(row[0]) if row else None

    def list_sources(self, status: str = None):
        rows = self.db.execute('SELECT payload FROM sources ORDER BY first_seen_utc').fetchall()
        sources = [json.loads(row[0]) for row in rows]
        return [source for source in sources if status is None or source['status'] == status]

    def source_revision_count(self, url: str) -> int:
        return self.db.execute('SELECT COUNT(*) FROM source_revisions WHERE url=?',
                               (url,)).fetchone()[0]

    # -- hypotheses ---------------------------------------------------------
    def record_hypothesis(self, hypothesis: dict) -> dict:
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO hypotheses VALUES (?,?,?,?)',
                            (hypothesis['id'], hypothesis.get('created_utc', utc()),
                             hypothesis.get('status', 'active'), canonical(hypothesis)))
        return hypothesis

    def get_hypothesis(self, hypothesis_id: str):
        row = self.db.execute('SELECT payload FROM hypotheses WHERE id=?',
                              (hypothesis_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list_hypotheses(self, status: str = None):
        rows = self.db.execute('SELECT payload FROM hypotheses ORDER BY created_utc').fetchall()
        items = [json.loads(row[0]) for row in rows]
        return [item for item in items if status is None or item['status'] == status]

    # -- experiments ----------------------------------------------------------
    def record_experiment(self, experiment: dict) -> dict:
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO experiments VALUES (?,?,?,?,?)',
                            (experiment['id'], utc(), experiment['kind'],
                             experiment['status'], canonical(experiment)))
        return experiment

    def get_experiment(self, experiment_id: str):
        row = self.db.execute('SELECT payload FROM experiments WHERE id=?',
                              (experiment_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def find_experiment(self, kind: str, params_digest: str = None):
        """Recover a completed experiment by kind (and optional params digest)."""
        for (payload,) in self.db.execute(
                'SELECT payload FROM experiments WHERE kind=? ORDER BY created_utc', (kind,)):
            experiment = json.loads(payload)
            if params_digest is None or digest(experiment.get('params', {})) == params_digest:
                return experiment
        return None

    def list_experiments(self, kind: str = None):
        rows = self.db.execute('SELECT payload FROM experiments ORDER BY created_utc').fetchall()
        items = [json.loads(row[0]) for row in rows]
        return [item for item in items if kind is None or item['kind'] == kind]

    # -- decisions and events -------------------------------------------------
    def record_decision(self, decision: dict) -> dict:
        with self.db:
            self.db.execute('INSERT INTO decisions(created_utc,action,payload) VALUES (?,?,?)',
                            (decision.get('created_utc', utc()), decision['action'],
                             canonical(decision)))
        return decision

    def last_decision(self):
        row = self.db.execute('SELECT payload FROM decisions ORDER BY id DESC LIMIT 1').fetchone()
        return json.loads(row[0]) if row else None

    def list_decisions(self):
        rows = self.db.execute('SELECT payload FROM decisions ORDER BY id').fetchall()
        return [json.loads(row[0]) for row in rows]

    def event(self, kind: str, payload: dict) -> None:
        with self.db:
            self.db.execute('INSERT INTO events(created_utc,kind,payload) VALUES (?,?,?)',
                            (utc(), kind, canonical(payload)))

    def list_events(self, kind: str = None):
        rows = self.db.execute('SELECT kind, payload FROM events ORDER BY id').fetchall()
        return [{'kind': row[0], **json.loads(row[1])}
                for row in rows if kind is None or row[0] == kind]

    # -- budget ledger -----------------------------------------------------------
    def charge(self, category: str, seconds: float = 0.0, usd: float = 0.0,
               tool_calls: int = 0, note: str = '') -> None:
        with self.db:
            self.db.execute(
                'INSERT INTO budget_ledger(created_utc,category,seconds,usd,tool_calls,note) '
                'VALUES (?,?,?,?,?,?)', (utc(), category, seconds, usd, tool_calls, note))

    def totals(self) -> dict:
        rows = self.db.execute('SELECT category, SUM(seconds), SUM(usd), SUM(tool_calls) '
                               'FROM budget_ledger GROUP BY category').fetchall()
        return {row[0]: {'seconds': row[1] or 0.0, 'usd': row[2] or 0.0,
                         'tool_calls': row[3] or 0} for row in rows}

    def tool_call_count(self) -> int:
        row = self.db.execute('SELECT COALESCE(SUM(tool_calls),0) FROM budget_ledger').fetchone()
        return int(row[0])

    def search_count(self) -> int:
        row = self.db.execute("SELECT COUNT(*) FROM events WHERE kind='web_search'").fetchone()
        return int(row[0])
