"""Persistent investigation sessions, motion evidence and restartable analysis jobs."""
import json
import math
import time


MOTION_DEFAULTS = {"motion_fraction": .0005, "motion_seconds": .2,
                   "masks": [[0, 0, .38, .065]]}


class InvestigationStore:
    def init_investigation(self):
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS investigations (
                    id INTEGER PRIMARY KEY, start REAL NOT NULL, deadline REAL NOT NULL,
                    stop REAL, settings TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS motions (
                    id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, group_id INTEGER,
                    start REAL NOT NULL, end REAL NOT NULL, open INTEGER NOT NULL DEFAULT 1,
                    interrupted INTEGER NOT NULL DEFAULT 0, peak REAL NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS motion_time ON motions(start,end);
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY, session_id INTEGER, stamp REAL NOT NULL,
                    kind TEXT NOT NULL, body TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS observation_time ON observations(stamp);
                CREATE TABLE IF NOT EXISTS analysis_jobs (
                    id INTEGER PRIMARY KEY, motion_id INTEGER NOT NULL, kind TEXT NOT NULL,
                    status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                    result TEXT, error TEXT);
                CREATE INDEX IF NOT EXISTS job_status ON analysis_jobs(status,id);
                PRAGMA user_version=2;
            ''')

    def investigation(self):
        with self.db() as db:
            row = db.execute('SELECT * FROM investigations ORDER BY id DESC LIMIT 1').fetchone()
        if row is None:
            return None
        result = dict(row)
        result['settings'] = json.loads(result['settings'])
        result['end'] = min(result['deadline'], result['stop'] or result['deadline'])
        result['active'] = result['start'] <= time.time() < result['end']
        return result

    def start_investigation(self, updates=None, now=None):
        settings = dict(MOTION_DEFAULTS, **(updates or {}))
        self.validate_motion_settings(settings)
        now = time.time() if now is None else now
        with self.db() as db:
            current = self.investigation()
            if current and current['end'] + 10 > now:
                raise ValueError('An investigation is already active or finishing its evidence padding')
            db.execute('INSERT INTO investigations(start,deadline,settings) VALUES (?,?,?)',
                       (now, now+86400, json.dumps(settings)))
        return self.investigation()

    @staticmethod
    def validate_motion_settings(settings):
        if set(settings) != set(MOTION_DEFAULTS):
            raise ValueError('Unsupported investigation setting')
        for key, low, high in [('motion_fraction', .00001, .5), ('motion_seconds', .05, 5)]:
            value = settings[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError('Invalid '+key)
        if not isinstance(settings['masks'], list) or len(settings['masks']) > 10:
            raise ValueError('Supply up to ten rectangular masks')
        for box in settings['masks']:
            if not isinstance(box, list) or len(box) != 4 or any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or not 0 <= v <= 1 for v in box):
                raise ValueError('Masks must contain four normalized coordinates')
            if box[0] >= box[2] or box[1] >= box[3]:
                raise ValueError('Mask corners must be ordered')

    def stop_investigation(self, now=None):
        now = time.time() if now is None else now
        with self.db() as db:
            db.execute('UPDATE investigations SET stop=? WHERE stop IS NULL AND deadline>?', (now, now))
        return self.investigation()

    def configure_investigation(self, settings):
        self.validate_motion_settings(settings)
        with self.db() as db:
            session = self.investigation()
            if not session or not session['active']:
                raise ValueError('No active investigation')
            db.execute('UPDATE investigations SET settings=? WHERE id=?',(json.dumps(settings),session['id']))
        return self.investigation()

    def open_motion(self, session_id, stamp, peak, group_id=None):
        with self.db() as db:
            mid = db.execute('INSERT INTO motions(session_id,group_id,start,end,peak) VALUES (?,?,?,?,?)',
                             (session_id, group_id, stamp, stamp, peak)).lastrowid
            if group_id is None:
                db.execute('UPDATE motions SET group_id=? WHERE id=?', (mid, mid))
        return mid

    def update_motion(self, mid, stamp, peak):
        with self.db() as db:
            db.execute('UPDATE motions SET end=MAX(end,?),peak=MAX(peak,?) WHERE id=?', (stamp, peak, mid))

    def close_motion(self, mid, interrupted=False):
        with self.db() as db:
            db.execute('UPDATE motions SET open=0,interrupted=? WHERE id=?', (int(interrupted), mid))

    def motions(self, limit=50, before=None):
        if not 1 <= limit <= 200:
            raise ValueError('Limit must be 1 to 200')
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM motions WHERE (? IS NULL OR id<?) ORDER BY id DESC LIMIT ?', (before, before, limit))]

    def motion(self, mid):
        with self.db() as db:
            row = db.execute('SELECT * FROM motions WHERE id=?', (mid,)).fetchone()
        if row is None:
            raise KeyError(mid)
        return dict(row)

    def investigation_intervals(self):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT start,end FROM motions')]

    def observation(self, stamp, kind, body, session_id=None):
        with self.db() as db:
            db.execute('INSERT INTO observations(session_id,stamp,kind,body) VALUES (?,?,?,?)',
                       (session_id, stamp, kind, json.dumps(body, allow_nan=False)))
            # Diagnostics have a bounded horizon; event/job records outlive video expiry.
            db.execute('DELETE FROM observations WHERE id IN (SELECT id FROM observations WHERE stamp<? LIMIT 1000)', (time.time()-7*86400,))

    def observations(self, start, end, limit=200, after=0):
        if not 1 <= limit <= 500 or not math.isfinite(start) or not math.isfinite(end) or start >= end or end-start > 86400:
            raise ValueError('Choose up to one day and 1 to 500 observations')
        with self.db() as db:
            return [dict(r, body=json.loads(r['body'])) for r in db.execute(
                'SELECT * FROM observations WHERE stamp>=? AND stamp<=? AND id>? ORDER BY id LIMIT ?', (start, end, after, limit))]

    def enqueue_analysis(self, mid, force=False):
        motion = self.motion(mid)
        if motion['open']:
            raise ValueError('Wait for motion to finish')
        with self.db() as db:
            for kind in ('detector_comparison', 'video_description'):
                exists = db.execute('SELECT 1 FROM analysis_jobs WHERE motion_id=? AND kind=?'+(" AND status IN ('queued','running')" if force else ''), (mid, kind)).fetchone()
                if not exists:
                    now = time.time()
                    db.execute('INSERT INTO analysis_jobs(motion_id,kind,status,created,updated) VALUES (?,?,?,?,?)', (mid,kind,'queued',now,now))

    def queue_completed_motions(self, now=None):
        now = time.time() if now is None else now
        with self.db() as db:
            ids = [r[0] for r in db.execute('SELECT id FROM motions WHERE open=0 AND end+10<=? AND NOT EXISTS (SELECT 1 FROM analysis_jobs WHERE motion_id=motions.id)', (now,))]
        for mid in ids:
            self.enqueue_analysis(mid)

    def claim_job(self, kind):
        with self.db() as db:
            row = db.execute("SELECT * FROM analysis_jobs WHERE status='queued' AND kind=? ORDER BY id LIMIT 1", (kind,)).fetchone()
            if row is None:
                return None
            db.execute("UPDATE analysis_jobs SET status='running',updated=? WHERE id=?", (time.time(),row['id']))
            return dict(row)

    def finish_job(self, jid, result=None, error=None):
        with self.db() as db:
            db.execute('UPDATE analysis_jobs SET status=?,updated=?,result=?,error=? WHERE id=?',
                       ('failed' if error else 'complete', time.time(), json.dumps(result) if result is not None else None, error, jid))

    def jobs(self, mid=None, limit=50, before=None):
        if not 1 <= limit <= 200:
            raise ValueError('Limit must be 1 to 200')
        with self.db() as db:
            return [dict(r, result=json.loads(r['result']) if r['result'] else None) for r in db.execute(
                'SELECT * FROM analysis_jobs WHERE (? IS NULL OR motion_id=?) AND (? IS NULL OR id<?) ORDER BY id DESC LIMIT ?', (mid,mid,before,before,limit))]

    def recover_investigation(self):
        with self.db() as db:
            previous = db.execute('SELECT MAX(stamp) FROM observations').fetchone()[0]
            db.execute('UPDATE motions SET open=0,interrupted=1 WHERE open=1')
            db.execute("UPDATE analysis_jobs SET status='queued' WHERE status='running'")
            db.execute("""UPDATE analysis_jobs SET status='failed', error=?
                WHERE kind='video_description' AND status='complete'
                AND COALESCE(json_extract(result,'$.input_version'),0)<2""",
                ('Invalid initial video sampling; rerun retained evidence with corrected resolution.',))
        if previous is not None:
            now = time.time()
            self.observation(now,'capture_gap',{'reason':'application restarted','start':previous,'end':now})

    def investigation_report(self, session_id=None):
        from collections import Counter
        with self.db() as db:
            row = db.execute('SELECT * FROM investigations WHERE (? IS NULL OR id=?) ORDER BY id DESC LIMIT 1',(session_id,session_id)).fetchone()
            if row is None:
                raise KeyError(session_id)
            session = dict(row)
            end = min(session['stop'] or session['deadline'],session['deadline'],time.time())
            motions = [dict(r) for r in db.execute('SELECT * FROM motions WHERE session_id=? ORDER BY start',(session['id'],))]
            diagnostics = [json.loads(r[0]) for r in db.execute("SELECT body FROM observations WHERE session_id=? AND kind='detection'",(session['id'],))]
            gaps = [dict(r,body=json.loads(r['body'])) for r in db.execute("SELECT stamp,kind,body FROM observations WHERE stamp>=? AND stamp<=? AND kind IN ('capture_gap','motion_gap','detector_gap') ORDER BY stamp",(session['start'],end))]
            jobs = dict(Counter(r[0] for r in db.execute('SELECT status FROM analysis_jobs WHERE motion_id IN (SELECT id FROM motions WHERE session_id=?)',(session['id'],))))
        available = sum(bool(self.evidence(m['start'],m['end'],padding=0)) for m in motions)
        return {'session_id':session['id'],'start':session['start'],'end':end,'deadline':session['deadline'],
                'finished':not (session['stop'] is None and time.time()<session['deadline']),
                'elapsed_seconds':max(0,end-session['start']), 'motion_groups':len({m['group_id'] for m in motions}),
                'motion_chunks':len(motions),'chunks_with_remaining_evidence':available,
                'frames_analyzed':len(diagnostics),'cat_candidate_frames':sum(any(d['class_id']==15 and d['confidence']>=o['threshold'] for d in o['detections']) for o in diagnostics),
                'visit_rule_outcomes':dict(Counter(o['reason'] for o in diagnostics)), 'analysis_jobs':jobs,
                'gaps':gaps,'accuracy':'Not evaluated. Independent labeled footage review is required; motion-only retention cannot establish missed-trigger recall.'}
