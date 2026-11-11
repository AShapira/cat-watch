"""Persistent investigation sessions, motion evidence and restartable analysis jobs."""
import json
import math
import time
import uuid

PADDING = 5


MOTION_DEFAULTS = {"motion_fraction": .0005, "motion_seconds": .5,
                   "masks": [[0, 0, .38, .065]], "motion_scope":"areas",
                   "motion_fps":5, "analysis_mode":"deferred", "crop_comparison":True, "duration_seconds":28800,
                   "motion_buffer":.2, "crop_context":.5, "detector_model":"yolo11m",
                   "description_provider":"ollama", "description_model":"qwen3.5:9b",
                   "description_url":"http://host.containers.internal:11434", "description_timeout":180}


class InvestigationStore:
    def init_investigation(self):
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS investigations (
                    id INTEGER PRIMARY KEY, start REAL NOT NULL, deadline REAL NOT NULL,
                    stop REAL, settings TEXT NOT NULL, config_snapshot TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS motions (
                    id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, group_id INTEGER,
                    start REAL NOT NULL, end REAL NOT NULL, open INTEGER NOT NULL DEFAULT 1,
                    interrupted INTEGER NOT NULL DEFAULT 0, peak REAL NOT NULL DEFAULT 0, area_peaks TEXT NOT NULL DEFAULT '{}');
                CREATE INDEX IF NOT EXISTS motion_time ON motions(start,end);
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY, session_id INTEGER, stamp REAL NOT NULL,
                    kind TEXT NOT NULL, body TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS observation_time ON observations(stamp);
                CREATE TABLE IF NOT EXISTS analysis_jobs (
                    id INTEGER PRIMARY KEY, motion_id INTEGER NOT NULL, kind TEXT NOT NULL,
                    status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                    result TEXT, error TEXT, manual INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS job_status ON analysis_jobs(status,id);
                CREATE TABLE IF NOT EXISTS protected_segments (
                    segment_id INTEGER PRIMARY KEY, reason TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS protected_sessions (session_id INTEGER PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS preparation (id INTEGER PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS analysis_control (session_id INTEGER PRIMARY KEY,
                    body TEXT NOT NULL);
            ''')
            # Never downgrade the separate Label Studio bridge's v5 schema.
            if db.execute('PRAGMA user_version').fetchone()[0] < 4:
                db.execute('PRAGMA user_version=4')


    def sessions(self):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT id,start,deadline,stop FROM investigations ORDER BY id DESC')]

    def protect_existing_evidence(self):
        with self.db() as db:
            db.execute("INSERT OR IGNORE INTO protected_segments SELECT id,'prior investigation' FROM segments")
            db.execute('INSERT OR IGNORE INTO protected_sessions SELECT id FROM investigations')

    def deferred_analysis(self, now=None):
        session = self.investigation()
        now = time.time() if now is None else now
        return bool(session and session['settings']['analysis_mode']=='deferred' and now<session['end']+PADDING)

    def investigation(self, session_id=None):
        with self.db() as db:
            row = db.execute('SELECT * FROM investigations WHERE (? IS NULL OR id=?) ORDER BY id DESC LIMIT 1',(session_id,session_id)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result['settings'] = json.loads(result['settings'])
        result['config_snapshot'] = json.loads(result['config_snapshot'])
        result['end'] = min(result['deadline'], result['stop'] or result['deadline'])
        result['active'] = result['start'] <= time.time() < result['end']
        return result

    def require_setup(self):
        session = self.investigation()
        if session and time.time() < session['end'] + PADDING:
            raise ValueError('Finish the investigation before changing its setup')

    def preparation(self):
        with self.db() as db:
            row = db.execute('SELECT body FROM preparation WHERE id=1').fetchone()
        return json.loads(row[0]) if row else None

    def prepare(self, jpeg, stamp, width, height):
        self.require_setup()
        if not jpeg or stamp is None or time.time()-stamp > 15:
            raise ValueError('Wait for a fresh camera preview')
        ident = uuid.uuid4().hex
        directory = self.root/'calibration'
        directory.mkdir(exist_ok=True)
        path = directory/(ident+'.jpg')
        path.write_bytes(jpeg)
        body = {'id':ident,'reference_image':str(path.relative_to(self.root)),
                'frame_stamp':stamp,'width':width,'height':height,'confirmed':False}
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO preparation VALUES (1,?)',(json.dumps(body),))
        return body

    def confirm_calibration(self, body):
        self.require_setup()
        if set(body) != {'id','polygons','masks'}:
            raise ValueError('Supply the prepared image, polygons and exclusion masks')
        prepared = self.preparation()
        if not prepared or prepared.get('used') or body['id'] != prepared['id']:
            raise ValueError('Refresh the calibration image first')
        self.validate_motion_settings(dict(MOTION_DEFAULTS,masks=body['masks']))
        config = self.configure({'polygons':body['polygons']})
        if not config['polygons']:
            raise ValueError('Draw all three areas')
        prepared.update(confirmed=True,config=config,masks=body['masks'],confirmed_at=time.time())
        with self.db() as db:
            db.execute('UPDATE preparation SET body=? WHERE id=1',(json.dumps(prepared),))
        return prepared

    def start_investigation(self, updates=None, now=None):
        updates = dict(updates or {})
        calibration_id = updates.pop('calibration_id',None)
        settings = dict(MOTION_DEFAULTS, **updates)
        self.validate_motion_settings(settings)
        now = time.time() if now is None else now
        with self.db() as db:
            self.require_setup()
            control = self.analysis_status()
            if control.get('phase') in ('checking','processing','stage_complete') or control.get('owner'):
                raise ValueError('Finish pending analysis and GPU cleanup before starting another investigation')
            prepared = self.preparation()
            if (not prepared or not prepared['confirmed'] or prepared['id'] != calibration_id
                    or prepared['config'] != self.config() or prepared['masks'] != settings['masks']):
                raise ValueError('Confirm the areas and masks on a fresh image before starting')
            snapshot = dict(prepared['config'],calibration={k:v for k,v in prepared.items()
                            if k not in ('config','confirmed','masks')},masks=prepared['masks'])
            self.protect_existing_evidence()
            cursor = db.execute('INSERT INTO investigations(start,deadline,settings,config_snapshot) VALUES (?,?,?,?)',
                       (now, now+settings['duration_seconds'], json.dumps(settings), json.dumps(snapshot)))
            db.execute('INSERT INTO analysis_control VALUES (?,?)',(cursor.lastrowid,json.dumps(
                {'attempt':0,'phase':'waiting_capture','message':'Deferred until capture ends','allowed_kind':None,'owner':None})))
            prepared['confirmed'] = False
            prepared['used'] = True
            db.execute('UPDATE preparation SET body=? WHERE id=1',(json.dumps(prepared),))
        return self.investigation()

    @staticmethod
    def validate_motion_settings(settings):
        duration = settings.get('duration_seconds')
        if isinstance(duration,bool) or not isinstance(duration,int) or not 900<=duration<=86400 or duration%900:
            raise ValueError('Duration must be 15 minutes to 24 hours in 15-minute steps')
        if set(settings) != set(MOTION_DEFAULTS):
            raise ValueError('Unsupported investigation setting')
        for key, low, high in [('motion_buffer',0,1),('crop_context',0,1),('description_timeout',30,600),('motion_fraction', .00001, .5), ('motion_seconds', .05, 5)]:
            value = settings[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError('Invalid '+key)
        if settings['detector_model'] != 'yolo11m' or settings['description_provider'] != 'ollama' or settings['description_model'] != 'qwen3.5:9b':
            raise ValueError('New investigations use YOLO11m and shared Qwen3.5-9B')
        if settings['description_url'] not in ('http://host.containers.internal:11434','http://127.0.0.1:11434'):
            raise ValueError('Use the local shared Ollama service')
        if settings['motion_scope'] not in ('full_frame','areas') or settings['analysis_mode'] not in ('live','deferred'):
            raise ValueError('Invalid motion scope or analysis mode')
        if isinstance(settings['motion_fps'],bool) or not isinstance(settings['motion_fps'],(int,float)) or not 2<=settings['motion_fps']<=10:
            raise ValueError('Motion processing rate must be 2 to 10 fps')
        if not isinstance(settings['crop_comparison'],bool):
            raise ValueError('Invalid crop comparison setting')
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
        raise ValueError('Investigation settings are fixed; stop and prepare a new investigation')

    def open_motion(self, session_id, stamp, peak, group_id=None):
        with self.db() as db:
            mid = db.execute('INSERT INTO motions(session_id,group_id,start,end,peak) VALUES (?,?,?,?,?)',
                             (session_id, group_id, stamp, stamp, peak)).lastrowid
            if group_id is None:
                db.execute('UPDATE motions SET group_id=? WHERE id=?', (mid, mid))
        return mid

    def update_motion(self, mid, stamp, peak, area_peaks=None):
        with self.db() as db:
            db.execute('UPDATE motions SET end=MAX(end,?),peak=MAX(peak,?) WHERE id=?', (stamp, peak, mid))
            if area_peaks:
                previous = json.loads(db.execute('SELECT area_peaks FROM motions WHERE id=?',(mid,)).fetchone()[0])
                for area,value in area_peaks.items():
                    previous[area] = max(previous.get(area,0),value)
                db.execute('UPDATE motions SET area_peaks=? WHERE id=?',(json.dumps(previous),mid))

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
            self.prune_observations(db)

    def prune_observations(self, db):
        # Bound rows INSPECTED, not just rows deleted. A protected archive may
        # contain millions of old rows; scanning it on every detection stalls
        # capture and API requests behind the shared database lock on Windows.
        now = time.monotonic()
        if now < getattr(self, '_observation_prune_after', 0):
            return
        cursor = getattr(self, '_observation_prune_cursor', 0)
        rows = db.execute('SELECT id,stamp,session_id FROM observations WHERE id>? ORDER BY id LIMIT 1000',
                          (cursor,)).fetchall()
        protected = {r[0] for r in db.execute('SELECT session_id FROM protected_sessions')}
        cutoff = time.time()-7*86400
        expired = [(r['id'],) for r in rows if r['stamp'] < cutoff and r['session_id'] not in protected]
        db.executemany('DELETE FROM observations WHERE id=?', expired)
        self._observation_prune_cursor = rows[-1]['id'] if len(rows) == 1000 else 0
        self._observation_prune_after = now+60

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
                    db.execute('INSERT INTO analysis_jobs(motion_id,kind,status,created,updated,manual) VALUES (?,?,?,?,?,?)', (mid,kind,'queued',now,now,int(force)))

    def queue_completed_motions(self, now=None):
        now = time.time() if now is None else now
        with self.db() as db:
            ids = [r[0] for r in db.execute('SELECT id FROM motions WHERE open=0 AND session_id NOT IN (SELECT session_id FROM protected_sessions) AND end+5<=? AND NOT EXISTS (SELECT 1 FROM analysis_jobs WHERE motion_id=motions.id)', (now,))]
        for mid in ids:
            self.enqueue_analysis(mid)

    def claim_job(self, kind):
        control = self.analysis_status()
        if control.get('allowed_kind') != kind or control.get('phase') != 'processing':
            return None
        with self.db() as db:
            row = db.execute("SELECT * FROM analysis_jobs WHERE status='queued' AND kind=? AND motion_id IN (SELECT id FROM motions WHERE session_id=?) ORDER BY id LIMIT 1", (kind,control['session_id'])).fetchone()
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
            for row in db.execute('SELECT session_id,body FROM analysis_control').fetchall():
                body = json.loads(row['body'])
                if body.get('phase') in ('checking','processing','stage_complete'):
                    body.update(phase='blocked',allowed_kind=None,message='Application restarted; retry analysis explicitly')
                    db.execute('UPDATE analysis_control SET body=? WHERE session_id=?',(json.dumps(body),row['session_id']))
        session = self.investigation()
        if previous is not None and session and session['active']:
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
