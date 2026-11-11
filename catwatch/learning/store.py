"""Separate learning database; immutable evidence and append-only decisions."""
from contextlib import contextmanager
from collections import Counter
from pathlib import Path
import json
import os
import sqlite3
import threading
import time

from .contracts import CARE, LABELS, canonical, coarse, digest, episode_keys, local_day, normalize, number

DEFAULTS = {'enabled': True, 'continuous': False, 'training': True,
            'dataset_cap_gb': 20, 'review_minutes': 5, 'daily_decisions': 10,
            'summary_hour': 9, 'telegram_enabled': False, 'telegram_chat_id': '',
            'telegram_evidence': True, 'gpu_reserve_mib': 2048, 'training_free_mib': 8192,
            'ollama_url': 'http://host.containers.internal:11434', 'ollama_model': 'qwen3.5:9b',
            'active_model': None, 'previous_model': None, 'calibration_id': None}


class Conflict(ValueError):
    pass


class LearningStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'agent.sqlite3'
        self.lock = threading.RLock()
        with self.db() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise ValueError('Unsupported learning database version')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS clips (
                    id TEXT PRIMARY KEY, created REAL NOT NULL, start REAL NOT NULL,
                    duration REAL NOT NULL, group_key TEXT NOT NULL, day TEXT NOT NULL,
                    manifest TEXT NOT NULL, prediction TEXT, decision TEXT,
                    version INTEGER NOT NULL DEFAULT 0, skipped_until REAL NOT NULL DEFAULT 0,
                    priority REAL NOT NULL DEFAULT 1, bucket TEXT NOT NULL, split TEXT,
                    pinned INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS clip_queue ON clips(skipped_until,priority);
                CREATE TABLE IF NOT EXISTS predictions (id TEXT PRIMARY KEY, clip_id TEXT NOT NULL, created REAL NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS revisions (id INTEGER PRIMARY KEY, clip_id TEXT NOT NULL,
                    version INTEGER NOT NULL, stamp REAL NOT NULL, action TEXT NOT NULL,
                    previous TEXT, current TEXT, UNIQUE(clip_id,version));
                CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY, kind TEXT NOT NULL,
                    key TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued', attempts INTEGER NOT NULL DEFAULT 0,
                    next_at REAL NOT NULL DEFAULT 0, updated REAL NOT NULL, payload TEXT NOT NULL,
                    result TEXT, error TEXT, UNIQUE(kind,key));
                CREATE TABLE IF NOT EXISTS datasets (id TEXT PRIMARY KEY, created REAL NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS models (id TEXT PRIMARY KEY, created REAL NOT NULL,
                    state TEXT NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS partitions (key TEXT PRIMARY KEY, split TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS coverage (start REAL PRIMARY KEY, end REAL NOT NULL, good INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS model_coverage (model_id TEXT NOT NULL, start REAL NOT NULL, end REAL NOT NULL, PRIMARY KEY(model_id,start));
                CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, start REAL NOT NULL, end REAL NOT NULL,
                    label TEXT NOT NULL, source TEXT NOT NULL, model_id TEXT, clip_id TEXT,
                    qualified INTEGER NOT NULL DEFAULT 0, body TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS event_time ON events(start,end);
                CREATE TABLE IF NOT EXISTS notices (id TEXT PRIMARY KEY, created REAL NOT NULL,
                    kind TEXT NOT NULL, state TEXT NOT NULL, body TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0, next_at REAL NOT NULL DEFAULT 0,
                    acknowledged INTEGER NOT NULL DEFAULT 0, snoozed_until REAL NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS cloud_batches (id TEXT PRIMARY KEY, created REAL NOT NULL,
                    expires REAL NOT NULL, state TEXT NOT NULL, manifest TEXT NOT NULL,
                    reserved_micros INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS cloud_requests (batch_id TEXT NOT NULL, item INTEGER NOT NULL,
                    state TEXT NOT NULL, reserved_micros INTEGER NOT NULL, result TEXT,
                    PRIMARY KEY(batch_id,item));
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, body TEXT NOT NULL);
                PRAGMA user_version=1;
            ''')
            db.execute('INSERT OR IGNORE INTO settings VALUES (1,?)', (canonical(DEFAULTS),))

    @contextmanager
    def db(self):
        with self.lock:
            conn = sqlite3.connect(self.path, timeout=20)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute('BEGIN IMMEDIATE')
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def config(self):
        with self.db() as db:
            result = {**DEFAULTS, **json.loads(db.execute('SELECT body FROM settings WHERE id=1').fetchone()[0])}
        from ..performance import training_locked
        if training_locked():
            result['training'] = False
        return result

    def configure(self, updates, *, internal=False):
        from ..performance import training_locked
        if isinstance(updates, dict) and updates.get('training') and training_locked():
            raise ValueError('Training is paused by the workstation deployment policy')
        allowed = set(DEFAULTS) - {'active_model', 'previous_model', 'calibration_id', 'continuous'}
        if not isinstance(updates, dict) or set(updates) - (set(DEFAULTS) if internal else allowed):
            raise ValueError('Unsupported learning setting')
        with self.db() as db:
            cfg = {**DEFAULTS, **json.loads(db.execute('SELECT body FROM settings WHERE id=1').fetchone()[0]), **updates}
            for key in ('enabled', 'continuous', 'training', 'telegram_enabled', 'telegram_evidence'):
                if type(cfg[key]) is not bool:
                    raise ValueError('Expected a boolean setting')
            for key, low, high in [('dataset_cap_gb', .05, 1000), ('daily_decisions', 1, 50),
                                  ('review_minutes', 1, 30), ('summary_hour', 0, 23),
                                  ('gpu_reserve_mib', 1024, 16384), ('training_free_mib', 2048, 65536)]:
                number(cfg[key], low, high)
            if type(cfg['daily_decisions']) is not int or type(cfg['summary_hour']) is not int:
                raise ValueError('Decision count and summary hour must be integers')
            if cfg['ollama_url'] not in ('http://127.0.0.1:11434', 'http://host.containers.internal:11434'):
                raise ValueError('Use the local Ollama service')
            if cfg['ollama_model'] != 'qwen3.5:9b':
                raise ValueError('The labeling model is pinned to qwen3.5:9b')
            if not isinstance(cfg['telegram_chat_id'], str) or (cfg['telegram_chat_id'] and not cfg['telegram_chat_id'].isdigit()):
                raise ValueError('Use a positive private Telegram chat ID')
            if cfg['telegram_enabled'] and not cfg['telegram_chat_id']:
                raise ValueError('Pair a private Telegram chat first')
            db.execute('UPDATE settings SET body=? WHERE id=1', (canonical(cfg),))
        return cfg

    def meta(self, key, default=None):
        with self.db() as db:
            row = db.execute('SELECT body FROM metadata WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_meta(self, key, value):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)', (key, canonical(value)))

    @staticmethod
    def decode_clip(row, blind=False):
        out = dict(row)
        for key in ('manifest', 'prediction', 'decision'):
            out[key] = json.loads(out[key]) if out[key] else None
        if blind and not out['decision'] and out['bucket'] == 'evaluation':
            out['prediction'] = None
            out['blind'] = True
        return out

    def add_clip(self, manifest):
        duration = number(manifest.get('duration'), .05, 60)
        number(manifest.get('start'), 0, 1e12)
        ident = manifest['id']
        if len(ident) != 64 or any(c not in '0123456789abcdef' for c in ident):
            raise ValueError('Clip identity must be a SHA-256 digest')
        if not isinstance(manifest.get('group_key'), str) or not manifest['group_key']:
            raise ValueError('A source episode identity is required')
        bucket = ('evaluation' if int(ident[:8], 16) % 10 >= 8 else
                  'audit' if int(ident[:8], 16) % 10 >= 6 else 'difficult')
        with self.db() as db:
            keys = [f"day:{local_day(manifest['start'])}", f"day:{local_day(manifest['start']+duration)}",
                    'group:'+manifest['group_key'], 'video:'+manifest['video_hash']]
            keys += ['source:'+h for h in manifest.get('source_hashes', [])]
            prior = {r['split'] for key in keys for r in db.execute('SELECT split FROM partitions WHERE key=?', (key,))}
            value = int(digest(keys[0])[:8], 16) % 10
            split = ('quarantine' if len(prior) > 1 else next(iter(prior)) if prior else
                     'train' if value < 6 else 'validation' if value < 8 else 'test')
            if split != 'quarantine':
                for key in keys:
                    db.execute('INSERT OR IGNORE INTO partitions VALUES (?,?)', (key, split))
            if split != 'train':
                bucket = 'evaluation'
            db.execute('INSERT OR IGNORE INTO clips(id,created,start,duration,group_key,day,manifest,bucket,split) VALUES (?,?,?,?,?,?,?,?,?)',
                       (ident, time.time(), manifest['start'], duration, manifest['group_key'],
                        local_day(manifest['start']), canonical(manifest), bucket, split))
            for event in db.execute("SELECT id,body FROM events WHERE source='model' AND clip_id IS NULL AND start>=? AND end<=?",
                                    (manifest['start'], manifest['start']+duration)).fetchall():
                if set(json.loads(event['body']).get('areas', [])) == set(manifest.get('areas', [])):
                    db.execute('UPDATE events SET clip_id=? WHERE id=?', (ident, event['id']))
        self.enqueue('label', ident, {'clip_id': ident})
        return ident

    def clip(self, ident, blind=False):
        with self.db() as db:
            row = db.execute('SELECT * FROM clips WHERE id=?', (ident,)).fetchone()
            if row is None:
                raise KeyError(ident)
            out = self.decode_clip(row, blind)
            out['history'] = [dict(r, previous=json.loads(r['previous']) if r['previous'] else None,
                                   current=json.loads(r['current']) if r['current'] else None)
                              for r in db.execute('SELECT * FROM revisions WHERE clip_id=? ORDER BY version', (ident,))]
            out['prediction_history'] = ([] if blind and out.get('blind') else
                [json.loads(r[0]) for r in db.execute('SELECT body FROM predictions WHERE clip_id=? ORDER BY created', (ident,))])
        return out

    def clips(self, *, limit=50, offset=0, reviewed=None):
        if not 1 <= limit <= 500 or offset < 0:
            raise ValueError('Invalid page')
        where = '' if reviewed is None else ('WHERE decision IS NOT NULL' if reviewed else 'WHERE decision IS NULL')
        with self.db() as db:
            count = db.execute(f'SELECT COUNT(*) FROM clips {where}').fetchone()[0]
            rows = db.execute(f'SELECT * FROM clips {where} ORDER BY start DESC,id LIMIT ? OFFSET ?', (limit, offset)).fetchall()
        return {'items': [self.decode_clip(r, blind=True) for r in rows], 'total': count, 'offset': offset}

    def review_queue(self, now=None):
        now = time.time() if now is None else now
        day = local_day(now)
        cfg = self.config()
        with self.db() as db:
            completed = sum(local_day(r['stamp']) == day for r in db.execute("SELECT MIN(stamp) stamp FROM revisions WHERE action='review' GROUP BY clip_id"))
            rows = db.execute('SELECT * FROM clips WHERE decision IS NULL AND skipped_until<=? ORDER BY priority DESC,start,id', (now,)).fetchall()
        remaining = max(0, cfg['daily_decisions'] - completed)
        selected = []
        for bucket, quota in [('difficult', 6), ('audit', 2), ('evaluation', 2)]:
            selected.extend([r for r in rows if r['bucket'] == bucket][:quota])
        ids = {r['id'] for r in selected}
        selected.extend(r for r in rows if r['id'] not in ids)
        return {'items': [self.decode_clip(r, blind=True) for r in selected[:remaining]],
                'completed_today': completed, 'daily_limit': cfg['daily_decisions'], 'remaining': remaining,
                'pending': len(rows), 'minutes': cfg['review_minutes']}

    def prediction(self, ident, body, provenance):
        clip = self.clip(ident)
        ann = normalize(body, clip['duration'], proposal=True)
        if not all(isinstance(provenance.get(k), str) and provenance[k] for k in ('provider', 'model', 'prompt_version')):
            raise ValueError('Prediction provenance is required')
        result = {**ann, 'provenance': provenance, 'created': time.time(), 'status': 'suggestion'}
        priority = 1 + sum(i['label'] == 'unclear' or bool(i['uncertainty']) for i in ann['intervals']) + bool(ann['quality'])
        with self.db() as db:
            previous = db.execute('SELECT prediction FROM clips WHERE id=?', (ident,)).fetchone()[0]
            if previous and {coarse(i['label']) for i in json.loads(previous)['intervals']} != {coarse(i['label']) for i in ann['intervals']}:
                priority += 5
                result['disagreement'] = True
            db.execute('INSERT OR IGNORE INTO predictions VALUES (?,?,?,?)', (digest(result), ident, time.time(), canonical(result)))
            db.execute('UPDATE clips SET prediction=?,priority=? WHERE id=?', (canonical(result), priority, ident))
        return result

    def review(self, ident, body, *, assisted_by=None):
        if not isinstance(body, dict) or set(body) - {'version', 'action', 'annotation', 'notes'}:
            raise ValueError('Supply version, action, annotation and optional notes')
        if type(body.get('version')) is not int or body['version'] < 0:
            raise ValueError('Supply the current review version')
        action = body.get('action', 'review')
        if action not in ('review', 'skip', 'undo'):
            raise ValueError('Unknown review action')
        notes = body.get('notes', '')
        if not isinstance(notes, str) or len(notes) > 2000:
            raise ValueError('Review notes must be at most 2000 characters')
        with self.db() as db:
            row = db.execute('SELECT * FROM clips WHERE id=?', (ident,)).fetchone()
            if row is None:
                raise KeyError(ident)
            if row['version'] != body['version']:
                raise Conflict('This decision changed. Reload before saving.')
            previous = row['decision']
            current = previous
            skipped = 0
            if action == 'skip':
                skipped = time.time() + 86400
            elif action == 'undo':
                last = db.execute("SELECT previous FROM revisions WHERE clip_id=? AND action!='skip' ORDER BY version DESC LIMIT 1", (ident,)).fetchone()
                if last is None:
                    raise ValueError('No decision to undo')
                current = last['previous']
            else:
                ann = normalize(body.get('annotation'), row['duration'])
                current = canonical({**ann, 'notes': notes, 'source': 'human', 'created': time.time(),
                                     'independent': row['bucket'] == 'evaluation' and not assisted_by,
                                     **({'assisted_by': assisted_by} if assisted_by else {})})
            version = row['version'] + 1
            db.execute('INSERT INTO revisions(clip_id,version,stamp,action,previous,current) VALUES (?,?,?,?,?,?)',
                       (ident, version, time.time(), action, previous, current))
            db.execute('UPDATE clips SET decision=?,version=?,skipped_until=?,pinned=MAX(pinned,?) WHERE id=?',
                       (current, version, skipped, int(current is not None), ident))
            # A corrected source invalidates models trained or evaluated on its older label.
            if action != 'skip':
                for model in db.execute("SELECT * FROM models WHERE state NOT IN ('invalidated','failed')").fetchall():
                    info = json.loads(model['body'])
                    if ident in info.get('label_versions', {}) and info['label_versions'][ident] != version:
                        db.execute("UPDATE models SET state='invalidated' WHERE id=?", (model['id'],))
                        db.execute('UPDATE events SET qualified=0 WHERE model_id=?', (model['id'],))
                        db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)', ('model_invalidated_since', canonical(time.time())))
                db.execute("DELETE FROM events WHERE clip_id=? AND source='human'", (ident,))
                if current:
                    for i in json.loads(current)['intervals']:
                        if coarse(i['label']) in LABELS:
                            eid = digest([ident, version, i])
                            db.execute('INSERT OR REPLACE INTO events VALUES (?,?,?,?,?,?,?,?,?)',
                                       (eid, row['start']+i['start'], row['start']+i['end'], coarse(i['label']),
                                        'human', None, ident, 1, canonical({'version': version})))
        return self.clip(ident)

    def enqueue(self, kind, key, payload):
        with self.db() as db:
            db.execute('INSERT OR IGNORE INTO jobs(kind,key,updated,payload) VALUES (?,?,?,?)',
                       (kind, key, time.time(), canonical(payload)))

    def claim(self, kind, now=None):
        now = time.time() if now is None else now
        with self.db() as db:
            row = db.execute("SELECT * FROM jobs WHERE kind=? AND state='queued' AND next_at<=? ORDER BY id LIMIT 1", (kind, now)).fetchone()
            if row is None:
                return None
            db.execute("UPDATE jobs SET state='running',attempts=attempts+1,updated=? WHERE id=?", (now, row['id']))
        return dict(row, attempts=row['attempts']+1, payload=json.loads(row['payload']))

    def finish(self, job_id, result=None, *, error=None, retry_after=None):
        state = 'complete' if error is None else 'queued' if retry_after is not None else 'failed'
        with self.db() as db:
            db.execute('UPDATE jobs SET state=?,result=?,error=?,next_at=?,updated=? WHERE id=?',
                       (state, canonical(result) if result is not None else None, error,
                        time.time()+(retry_after or 0), time.time(), job_id))

    def recover(self):
        with self.db() as db:
            db.execute("UPDATE jobs SET state='queued',error='Worker restarted; resuming checkpoint' WHERE state='running'")
            db.execute("UPDATE notices SET state='unknown' WHERE state='sending'")
            db.execute("UPDATE cloud_requests SET state='unknown' WHERE state='sending'")

    def defer(self, job_id):
        """Yield a claimed job without exhausting its error retry allowance."""
        with self.db() as db:
            db.execute("UPDATE jobs SET state='queued',attempts=MAX(0,attempts-1),next_at=?,updated=?,error=NULL WHERE id=? AND state='running'",
                       (time.time()+5, time.time(), job_id))

    def jobs(self):
        with self.db() as db:
            return [dict(r, payload=json.loads(r['payload']), result=json.loads(r['result']) if r['result'] else None)
                    for r in db.execute('SELECT * FROM jobs ORDER BY id DESC LIMIT 100')]

    def models(self):
        with self.db() as db:
            return [dict(r, body=json.loads(r['body'])) for r in db.execute('SELECT * FROM models ORDER BY created DESC LIMIT 20')]

    def inference_models(self):
        models = self.models()
        return [m for m in models if m['state'] == 'active'][:1] + [m for m in models if m['state'] == 'shadow'][:1]

    def status(self):
        counts = Counter()
        episodes = {label: set() for label in LABELS}
        with self.db() as db:
            clip_rows = db.execute('SELECT * FROM clips').fetchall()
            independent = episode_keys(clip_rows)
            for row in clip_rows:
                counts['clips'] += 1
                counts['suggestions'] += row['prediction'] is not None
                counts['reviewed'] += row['decision'] is not None
                if row['decision']:
                    for i in json.loads(row['decision'])['intervals']:
                        if coarse(i['label']) in episodes:
                            episodes[coarse(i['label'])].add(independent[row['id']])
            jobs = [dict(r) for r in db.execute('SELECT kind,state,COUNT(*) count FROM jobs GROUP BY kind,state')]
            models = [dict(r, body=json.loads(r['body'])) for r in db.execute('SELECT * FROM models ORDER BY created DESC LIMIT 20')]
            datasets = [dict(r, body={k: v for k, v in json.loads(r['body']).items() if k not in ('rows','label_versions')})
                        for r in db.execute('SELECT * FROM datasets ORDER BY created DESC LIMIT 10')]
        return {'counts': dict(counts), 'episodes': {k: len(v) for k, v in episodes.items()},
                'jobs': jobs, 'models': models, 'datasets': datasets,
                'config': self.config(), 'worker': self.meta('worker', {'state': 'not started'}),
                'storage': self.meta('storage', {}), 'cloud_default': 'disabled; approval per batch',
                'training_ready': all(len(episodes[k]) >= 30 for k in CARE)}

    def safe_path(self, relative):
        if not isinstance(relative, str) or Path(relative).is_absolute():
            raise ValueError('Use an owned relative evidence path')
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root.resolve()) or path == self.root.resolve():
            raise ValueError('Evidence path escapes learning storage')
        return path

    def save_model(self, ident, state, body):
        with self.db() as db:
            if state in ('shadow', 'active'):
                for cid, version in body.get('label_versions', {}).items():
                    current = db.execute('SELECT version FROM clips WHERE id=?', (cid,)).fetchone()
                    if not current or current[0] != version:
                        raise Conflict('Labels changed; rebuild the dataset before using this model')
            db.execute('INSERT INTO models VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,body=excluded.body',
                       (ident, time.time(), state, canonical(body)))

    def model(self, ident):
        with self.db() as db:
            r = db.execute('SELECT * FROM models WHERE id=?', (ident,)).fetchone()
            if r is None:
                raise KeyError(ident)
            return dict(r, body=json.loads(r['body']))

    def notice(self, key, kind, body, *, shadow=False):
        with self.db() as db:
            db.execute('INSERT OR IGNORE INTO notices(id,created,kind,state,body) VALUES (?,?,?,?,?)',
                       (key, time.time(), kind, 'shadow' if shadow else 'queued', canonical(body)))

    def notices(self, *, all_rows=False):
        with self.db() as db:
            return [dict(r, body=json.loads(r['body'])) for r in db.execute('SELECT * FROM notices ORDER BY created DESC'+('' if all_rows else ' LIMIT 100'))]
