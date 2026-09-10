"""Saved detector evidence and human review, independent of recording workers."""
import json
import math
import time
from collections import defaultdict

from .core import AREAS, contains

REVIEW_STATUSES = ('unreviewed', 'cat_confirmed', 'no_cat', 'uncertain')
MODELS = ('yolo11n/640', 'yolo11m/640', 'yolo11m/1280')


class ReviewConflict(ValueError):
    pass


def assignment(polygons, box):
    point = [(box[0]+box[2])/2, box[3]]
    matches = [name for name, polygon in polygons.items() if contains(polygon, point)]
    area = matches[0] if len(matches) == 1 else 'ambiguous' if matches else 'outside'
    return {'point': point, 'area': area if polygons else 'unknown'}


class InvestigationReviewStore:
    def init_motion_review(self):
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS motion_analysis_cache (
                    job_id INTEGER PRIMARY KEY, updated REAL NOT NULL, summary TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS motion_group_reviews (
                    group_id INTEGER PRIMARY KEY, status TEXT NOT NULL, areas TEXT NOT NULL,
                    notes TEXT NOT NULL, updated REAL NOT NULL, version INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS motion_group_review_history (
                    id INTEGER PRIMARY KEY, group_id INTEGER NOT NULL, stamp REAL NOT NULL,
                    previous TEXT NOT NULL, current TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS motion_review_history_group
                    ON motion_group_review_history(group_id,id);
            ''')

    def saved_cat_analysis(self):
        """Parse each completed job once; reuse compact evidence across UI requests."""
        with self.db() as db:
            jobs = db.execute("SELECT id,motion_id,updated,status FROM analysis_jobs WHERE kind='detector_comparison' ORDER BY id").fetchall()
            cached = {r['job_id']:r for r in db.execute('SELECT * FROM motion_analysis_cache')}
            # Failed reruns preserve previous positive evidence, but remain incomplete.
            latest = {r['motion_id']:dict(r) for r in jobs}
            completed = {r['motion_id']:dict(r) for r in jobs if r['status']=='complete'}
            result = {}
            for mid, attempt in latest.items():
                job = completed.get(mid,attempt)
                if job['status'] != 'complete':
                    result[mid] = {'status':job['status'], 'samples':[], 'models':[]}
                    continue
                cache = cached.get(job['id'])
                if cache and cache['updated'] == job['updated']:
                    summary = json.loads(cache['summary'])
                else:
                    raw = db.execute('SELECT result FROM analysis_jobs WHERE id=?',(job['id'],)).fetchone()[0]
                    body = json.loads(raw) if raw else {}
                    samples, models = [], set()
                    observations = body.get('observations', [])
                    for observation in observations:
                        model = observation['model']+'/'+str(observation['imgsz'])
                        models.add(model)
                        cats = [d for d in observation.get('detections',[]) if d.get('label') == 'cat']
                        if cats:
                            samples.append({'stamp':observation['stamp'], 'model':model, 'detections':cats})
                    summary = {'status':'complete' if observations else 'missing',
                               'models':sorted(models), 'samples':samples}
                    db.execute('INSERT OR REPLACE INTO motion_analysis_cache VALUES (?,?,?)',
                               (job['id'],job['updated'],json.dumps(summary)))
                result[mid] = dict(summary,status=attempt['status']) if attempt['status']!='complete' else summary
            return result

    def group_review(self, gid):
        with self.db() as db:
            row = db.execute('SELECT * FROM motion_group_reviews WHERE group_id=?',(gid,)).fetchone()
        if row:
            return dict(row, areas=json.loads(row['areas']))
        return {'group_id':gid,'status':'unreviewed','areas':[],'notes':'','updated':None,'version':0}

    def review_group(self, gid, body):
        if not isinstance(body,dict) or set(body) != {'status','areas','notes','version'}:
            raise ValueError('Supply status, areas, notes and review version')
        status, areas, notes, version = (body[k] for k in ('status','areas','notes','version'))
        if status not in REVIEW_STATUSES or not isinstance(notes,str) or len(notes)>2000:
            raise ValueError('Invalid review label or notes (maximum 2000 characters)')
        if not isinstance(areas,list) or any(not isinstance(a,str) or a not in (*AREAS,'outside','unknown') for a in areas) or len(set(areas))!=len(areas):
            raise ValueError('Choose valid, distinct presence areas')
        if status != 'cat_confirmed' and areas:
            raise ValueError('Presence areas require a confirmed cat label')
        if isinstance(version,bool) or not isinstance(version,int) or version<0:
            raise ValueError('Invalid review version')
        with self.db() as db:
            # Serialize across processes, as well as the Store's thread lock.
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM motions WHERE group_id=?',(gid,)).fetchone():
                raise KeyError(gid)
            previous = self.group_review(gid)
            if previous['version'] != version:
                raise ReviewConflict('This review changed in another tab. Reopen the group before saving.')
            current = {'group_id':gid,'status':status,'areas':areas,'notes':notes.strip(),
                       'updated':time.time(),'version':version+1}
            db.execute('INSERT OR REPLACE INTO motion_group_reviews VALUES (?,?,?,?,?,?)',
                       (gid,status,json.dumps(areas),current['notes'],current['updated'],current['version']))
            db.execute('INSERT INTO motion_group_review_history(group_id,stamp,previous,current) VALUES (?,?,?,?)',
                       (gid,current['updated'],json.dumps(previous),json.dumps(current)))
        return current

    def motion_group_list(self, *, cat='all', confidence=.4, area='all', review='all',
                          model='all', analysis='all', disagreement=False, start=None,
                          end=None, min_duration=0., max_duration=None, offset=0, limit=24):
        if cat not in ('all','detected','not_detected') or area not in ('all',*AREAS,'outside','ambiguous','unknown') or review not in ('all',*REVIEW_STATUSES) or model not in ('all',*MODELS) or analysis not in ('all','complete','incomplete','gap'):
            raise ValueError('Invalid investigation filter')
        if not math.isfinite(confidence) or not .1<=confidence<=1 or not 1<=limit<=100 or offset<0:
            raise ValueError('Invalid confidence or page size')
        values = (start,end,min_duration,max_duration)
        if any(v is not None and not math.isfinite(v) for v in values) or min_duration<0 or (max_duration is not None and max_duration<min_duration) or (start is not None and end is not None and start>end):
            raise ValueError('Invalid time or duration range')
        summaries = self.saved_cat_analysis()
        polygons = self.config()['polygons']
        with self.db() as db:
            motions = [dict(r) for r in db.execute('SELECT * FROM motions ORDER BY start,id')]
            reviews = {r['group_id']:dict(r,areas=json.loads(r['areas'])) for r in db.execute('SELECT * FROM motion_group_reviews')}
        grouped = defaultdict(list)
        for motion in motions:
            grouped[motion['group_id']].append(motion)
        output = []
        for gid, chunks in grouped.items():
            a,b = min(m['start'] for m in chunks),max(m['end'] for m in chunks)
            if start is not None and b<start or end is not None and a>end or b-a<min_duration or max_duration is not None and b-a>max_duration:
                continue
            samples = [dict(s,motion_id=m['id']) for m in chunks for s in summaries.get(m['id'],{}).get('samples',[])]
            selected = [s for s in samples if model=='all' or s['model']==model]
            detections = [(s,d) for s in selected for d in s['detections'] if d['confidence']>=confidence]
            found = bool(detections)
            complete = all(summaries.get(m['id'],{}).get('status')=='complete' and
                           (model=='all' or model in summaries[m['id']]['models']) for m in chunks)
            gap = any(m['interrupted'] for m in chunks)
            label = reviews.get(gid, {'group_id':gid,'status':'unreviewed','areas':[], 'notes':'','updated':None,'version':0})
            models = sorted({s['model'] for s in samples if any(d['confidence']>=confidence for d in s['detections'])})
            differs = any(k.startswith('yolo11m/') for k in models) and 'yolo11n/640' not in models and all('yolo11n/640' in summaries.get(m['id'],{}).get('models',[]) for m in chunks)
            areas = sorted({assignment(polygons,d['box'])['area'] for _,d in detections})
            if cat=='detected' and not found or cat=='not_detected' and (found or not complete):
                continue
            if area!='all' and area not in areas or review!='all' and label['status']!=review:
                continue
            if analysis=='complete' and not complete or analysis=='incomplete' and complete or analysis=='gap' and not gap or disagreement and not differs:
                continue
            # A candidate-frame thumbnail is selected from the chosen model even below threshold.
            best = max(((s,d) for s in selected for d in s['detections']), key=lambda x:x[1]['confidence'], default=None)
            output.append({'id':gid,'start':a,'end':b,'duration':b-a,'motion_count':len(chunks),
                           'motion_ids':[m['id'] for m in chunks],'open':any(m['open'] for m in chunks),
                           'peak':max(m['peak'] for m in chunks),
                           'peak_unknown':any(m['interrupted'] and m['peak']==0 for m in chunks),
                           'analysis_gap':gap,'analysis_complete':complete,'cat_detected':found,
                           'best_confidence':best[1]['confidence'] if best else None,
                           'best_stamp':best[0]['stamp'] if best else None,
                           'best_motion_id':best[0]['motion_id'] if best else chunks[0]['id'],
                           'areas':areas,'models':models,'disagreement':differs,'review':label})
        output.sort(key=lambda g:(g['start'],g['id']),reverse=True)
        page = output[offset:offset+limit]
        return {'groups':page,'total':len(output),'all_groups':len(grouped),'all_motions':len(motions),
                'next_offset':offset+limit if offset+limit<len(output) else None,
                'confidence':confidence,'area_basis':'current saved polygons; detector footpoint',
                'detection_basis':'latest successful saved comparison per motion; failed reruns remain incomplete; not human confirmation'}

    def motion_group_detail(self, gid):
        # A full detail uses every saved cat candidate; the UI selects model and threshold.
        with self.db() as db:
            chunks = [dict(r) for r in db.execute('SELECT * FROM motions WHERE group_id=? ORDER BY start,id',(gid,))]
        if not chunks:
            raise KeyError(gid)
        summaries = self.saved_cat_analysis()
        polygons = self.config()['polygons']
        a,b = min(m['start'] for m in chunks),max(m['end'] for m in chunks)
        samples = []
        for m in chunks:
            for sample in summaries.get(m['id'],{}).get('samples',[]):
                samples.append(dict(sample, motion_id=m['id'], detections=[dict(d,**assignment(polygons,d['box'])) for d in sample['detections']]))
        samples.sort(key=lambda s:(s['stamp'],s['model']))
        best = max(samples,key=lambda s:max(d['confidence'] for d in s['detections']),default=None)
        with self.db() as db:
            descriptions=[]
            for m in chunks:
                row=db.execute("SELECT status,result,error FROM analysis_jobs WHERE motion_id=? AND kind='video_description' ORDER BY id DESC LIMIT 1",(m['id'],)).fetchone()
                if row:
                    descriptions.append({'motion_id':m['id'],'status':row['status'],'error':row['error'],
                                         'windows':json.loads(row['result']).get('windows',[]) if row['status']=='complete' and row['result'] else []})
            reasons={r[0]:r[1] for r in db.execute("SELECT json_extract(body,'$.reason'),count(*) FROM observations WHERE kind='detection' AND stamp>=? AND stamp<=? GROUP BY json_extract(body,'$.reason')",(a,b))}
            history=[dict(r,previous=json.loads(r['previous']),current=json.loads(r['current'])) for r in db.execute('SELECT * FROM motion_group_review_history WHERE group_id=? ORDER BY id DESC',(gid,))]
        return {'id':gid,'start':a,'end':b,'motions':chunks,'clips':self.evidence(a,b),
                'samples':samples,'models':sorted({s['model'] for s in samples}),
                'best_stamp':best['stamp'] if best else None,'polygons':polygons,
                'review':self.group_review(gid),'history':history,'descriptions':descriptions,
                'baseline_reasons':reasons,'overlay_max_age_seconds':.35,
                'area_basis':'current saved polygons; baseline reasons reflect the original run'}
