"""Durable integration state in the application's serialized SQLite connection."""
import json
import time
import uuid

from .contracts import canonical, normalize, source_intervals, union


def migrate(store):
    with store.db() as db:
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version == 5:
            return
        if version != 4:
            raise ValueError('Labeling requires a version 4 or 5 database')
        db.executescript('''
            BEGIN IMMEDIATE;
            CREATE TABLE labeling_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE labeling_jobs (group_id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL,
                state TEXT NOT NULL, error TEXT, updated REAL NOT NULL);
            CREATE TABLE labeling_tasks (task_key TEXT PRIMARY KEY, group_id INTEGER NOT NULL,
                session_id INTEGER NOT NULL, manifest TEXT NOT NULL, remote_id INTEGER UNIQUE,
                state TEXT NOT NULL DEFAULT 'pending', error TEXT, current_annotation TEXT,
                remote_updated TEXT, suppressed INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE labeling_revisions (id INTEGER PRIMARY KEY, task_key TEXT NOT NULL,
                received REAL NOT NULL, raw TEXT NOT NULL, hash TEXT NOT NULL,
                UNIQUE(task_key,hash));
            CREATE TABLE labeling_sync (id INTEGER PRIMARY KEY, remote_id INTEGER,
                payload TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE dataset_exports (id TEXT PRIMARY KEY, state TEXT NOT NULL,
                created REAL NOT NULL, path TEXT, error TEXT);
        ''')
        db.execute('INSERT INTO labeling_state VALUES (?,?)', ('dataset_id', canonical(uuid.uuid4().hex)))
        db.execute('INSERT INTO labeling_state VALUES (?,?)', ('auto_after', canonical(time.time())))
        db.execute('PRAGMA user_version=5')


class LabelingStore:
    def __init__(self, store):
        self.store = store

    def get(self, key, default=None):
        with self.store.db() as db:
            row = db.execute('SELECT value FROM labeling_state WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        with self.store.db() as db:
            db.execute('INSERT OR REPLACE INTO labeling_state VALUES (?,?)', (key, canonical(value)))

    def queue(self, session_id):
        session = self.store.investigation(session_id)
        if session is None:
            raise KeyError(session_id)
        if time.time() < session['end'] + 5:
            raise ValueError('Wait for capture and post-roll to finish')
        with self.store.db() as db:
            if db.execute('SELECT 1 FROM motions WHERE session_id=? AND open=1', (session_id,)).fetchone():
                raise ValueError('Wait for motion processing to drain')
            groups = db.execute('SELECT DISTINCT group_id FROM motions WHERE session_id=?', (session_id,)).fetchall()
            for row in groups:
                db.execute("INSERT OR IGNORE INTO labeling_jobs VALUES (?,?,'queued',NULL,?)", (row[0], session_id, time.time()))
        return len(groups)

    def jobs(self):
        with self.store.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM labeling_jobs ORDER BY session_id,group_id')]

    def job_state(self, gid, state, error=None):
        with self.store.db() as db:
            db.execute('UPDATE labeling_jobs SET state=?,error=?,updated=? WHERE group_id=?', (state, error, time.time(), gid))

    def add_task(self, manifest):
        with self.store.db() as db:
            db.execute('INSERT OR IGNORE INTO labeling_tasks(task_key,group_id,session_id,manifest) VALUES (?,?,?,?)',
                       (manifest['task_key'], manifest['group_id'], manifest['session_id'], canonical(manifest)))

    def tasks(self, group_id=None):
        with self.store.db() as db:
            rows = db.execute('SELECT * FROM labeling_tasks WHERE (? IS NULL OR group_id=?) ORDER BY session_id,group_id,task_key', (group_id, group_id)).fetchall()
        return [dict(r, manifest=json.loads(r['manifest']), current_annotation=json.loads(r['current_annotation']) if r['current_annotation'] else None) for r in rows]

    def update_task(self, key, **changes):
        allowed = {'remote_id', 'state', 'error', 'current_annotation', 'remote_updated', 'suppressed'}
        if not changes or set(changes) - allowed:
            raise ValueError('Unsupported task update')
        with self.store.db() as db:
            db.execute('UPDATE labeling_tasks SET '+','.join(f'{k}=?' for k in changes)+' WHERE task_key=?', (*changes.values(), key))

    def ingest(self, task, annotations, remote_updated=None):
        from .contracts import fingerprint
        raw = {'annotations': annotations, 'remote_updated': remote_updated}
        with self.store.db() as db:
            db.execute('INSERT OR IGNORE INTO labeling_revisions(task_key,received,raw,hash) VALUES (?,?,?,?)',
                       (task['task_key'], time.time(), canonical(raw), fingerprint(raw)))
            completed = [a for a in annotations if not a.get('was_cancelled') and not a.get('draft')]
            state, current, error = 'unreviewed', None, None
            if len(completed) > 1:
                state, error = 'conflict', 'Multiple completed annotations; keep one in Label Studio'
            elif completed:
                try:
                    current = canonical(normalize(completed[0], task['manifest']))
                    state = 'reviewed'
                except (ValueError, KeyError, TypeError):
                    state, error = 'invalid', 'Annotation needs correction: check choices, frame ranges, overlaps and coverage'
            self.update_task(task['task_key'], state=state, current_annotation=current, error=error, remote_updated=remote_updated)

    def activities(self, start=None, end=None):
        items = []
        for task in self.tasks():
            ann = task['current_annotation']
            if task['suppressed'] or task['state'] != 'reviewed' or not ann or not ann['supervised_eligible']:
                continue
            for item in ann['intervals']:
                for a, b in source_intervals(task['manifest'], item):
                    a = max(a, start) if start is not None else a
                    b = min(b, end) if end is not None else b
                    if a < b:
                        items.append(dict(item, start=a, end=b, task_key=task['task_key'],
                                          session_id=task['session_id'], annotation_id=ann['annotation_id']))
        return items

    def report(self, start=None, end=None):
        from .contracts import LABELS
        items = self.activities(start, end)
        # Overlapping tasks may disagree. Exclude contested time from every class.
        conflicts = union((max(a['start'], b['start']), min(a['end'], b['end']))
                          for n, a in enumerate(items) for b in items[n+1:]
                          if a['label'] != b['label'] and max(a['start'], b['start']) < min(a['end'], b['end']))
        def subtract(ranges):
            for a, b in union(ranges):
                for x, y in conflicts:
                    if y <= a or x >= b:
                        continue
                    if a < x:
                        yield [a, x]
                    a = max(a, y)
                if a < b:
                    yield [a, b]
        result = {}
        for label in LABELS:
            spans = list(subtract((i['start'], i['end']) for i in items if i['label'] == label))
            result[label] = {'seconds': sum(b-a for a, b in spans), 'bouts': len(spans), 'intervals': spans}
        covered = list(subtract((i['start'], i['end']) for i in items))
        return {'activities': result, 'reviewed_seconds': sum(b-a for a, b in covered),
                'conflict_seconds': sum(b-a for a, b in conflicts), 'conflicts': conflicts,
                'note': 'Reviewed evidence only. Unlabeled time is not inactivity; capture times are estimates.'}
