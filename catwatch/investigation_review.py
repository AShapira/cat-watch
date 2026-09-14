"""Saved detector evidence and human review, independent of recording workers."""
import json
import math
import re
import time
from collections import defaultdict

from .core import AREAS, box_assignment

REVIEW_BEHAVIORS = ('eating','drinking','litter_activity','other_activity','unclear')
REVIEW_STATUSES = ('unreviewed', 'cat_confirmed', 'no_cat', 'uncertain')
MODELS = ('yolo11n/640', 'yolo11m/640', 'yolo11m/1280', 'yolo11n/640/live', *(f'yolo11m/640/crop:{area}' for area in AREAS))


class ReviewConflict(ValueError):
    pass


def assignment(polygons, box, thresholds):
    return box_assignment(polygons, box, thresholds)


class InvestigationReviewStore:
    def init_motion_review(self):
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS motion_analysis_cache (
                    job_id INTEGER PRIMARY KEY, updated REAL NOT NULL, summary TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS motion_group_reviews (
                    group_id INTEGER PRIMARY KEY, status TEXT NOT NULL, areas TEXT NOT NULL,
                    notes TEXT NOT NULL, updated REAL NOT NULL, version INTEGER NOT NULL, behaviors TEXT NOT NULL);
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
                        if observation.get('crop_area'):
                            model += '/crop:'+observation['crop_area']
                        models.add(model)
                        cats = [d for d in observation.get('detections',[]) if d.get('label') == 'cat']
                        if cats:
                            samples.append({'stamp':observation['stamp'], 'model':model, 'detections':cats})
                    summary = {'status':'complete' if observations else 'missing',
                               'models':sorted(models), 'samples':samples}
                    db.execute('INSERT OR REPLACE INTO motion_analysis_cache VALUES (?,?,?)',
                               (job['id'],job['updated'],json.dumps(summary)))
                result[mid] = dict(summary,status=attempt['status']) if attempt['status']!='complete' else summary
            # Expose live cat candidates while expensive comparisons are deferred.
            for motion in db.execute('SELECT id,start,end FROM motions'):
                mid = motion['id']
                if mid in completed:
                    continue
                samples = []
                for row in db.execute("SELECT stamp,body FROM observations WHERE kind='detection' AND stamp>=? AND stamp<=?",(motion['start'],motion['end'])):
                    body = json.loads(row['body'])
                    cats = [d for d in body.get('detections',[]) if d.get('label')=='cat']
                    if cats:
                        model = f"{body['model']}/{body['imgsz']}/live" + ('/area_crops' if body.get('input_scope')=='area_crops' else '')
                        samples.append({'stamp':row['stamp'],'model':model,'detections':cats})
                if samples:
                    summary = result.setdefault(mid,{'status':'pending','samples':[],'models':[]})
                    summary['samples'].extend(samples)
                    summary['models'] = sorted(set(summary['models']) | {s['model'] for s in samples})
            return result

    def group_review(self, gid):
        with self.db() as db:
            row = db.execute('SELECT * FROM motion_group_reviews WHERE group_id=?',(gid,)).fetchone()
        if row:
            return dict(row, areas=json.loads(row['areas']),behaviors=json.loads(row['behaviors']))
        return {'group_id':gid,'status':'unreviewed','areas':[],'behaviors':[],'notes':'','updated':None,'version':0}

    def review_group(self, gid, body):
        if not isinstance(body,dict) or set(body) != {'status','areas','behaviors','notes','version'}:
            raise ValueError('Supply status, areas, behaviors, notes and review version')
        status, areas, notes, version = (body[k] for k in ('status','areas','notes','version'))
        if status not in REVIEW_STATUSES or not isinstance(notes,str) or len(notes)>2000:
            raise ValueError('Invalid review label or notes (maximum 2000 characters)')
        if not isinstance(areas,list) or any(not isinstance(a,str) or a not in (*AREAS,'outside','unknown') for a in areas) or len(set(areas))!=len(areas):
            raise ValueError('Choose valid, distinct presence areas')
        behaviors = body['behaviors']
        if (not isinstance(behaviors,list) or any(b not in REVIEW_BEHAVIORS for b in behaviors)
                or len(set(behaviors)) != len(behaviors) or ('unclear' in behaviors and len(behaviors)>1)):
            raise ValueError('Choose distinct behaviors; unclear cannot be combined with observed activity')
        if status != 'cat_confirmed' and (areas or behaviors):
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
            current = {'group_id':gid,'status':status,'areas':areas,'behaviors':behaviors,'notes':notes.strip(),
                       'updated':time.time(),'version':version+1}
            db.execute('INSERT OR REPLACE INTO motion_group_reviews VALUES (?,?,?,?,?,?,?)',
                       (gid,status,json.dumps(areas),current['notes'],current['updated'],current['version'],json.dumps(behaviors)))
            db.execute('INSERT INTO motion_group_review_history(group_id,stamp,previous,current) VALUES (?,?,?,?)',
                       (gid,current['updated'],json.dumps(previous),json.dumps(current)))
        return current

    def motion_group_list(self, *, cat='all', confidence=.4, area='all', review='all',
                          model='all', analysis='all', disagreement=False, start=None,
                          end=None, min_duration=0., max_duration=None, offset=0, limit=24, session_id=None, motion_area='all', presence='all'):
        if motion_area not in ('all',*AREAS,'unknown') or session_id is not None and session_id<1:
            raise ValueError('Invalid session or motion area')
        if cat not in ('all','detected','not_detected') or area not in ('all',*AREAS,'outside','overlap','unknown') or review not in ('all',*REVIEW_STATUSES) or not isinstance(model,str) or len(model)>128 or (model!='all' and not re.fullmatch(r'[A-Za-z0-9_-]+/[0-9]+(?:/live(?:/area_crops)?|/crop:[a-z_]+)?',model)) or analysis not in ('all','complete','incomplete','gap'):
            raise ValueError('Invalid investigation filter')
        if not math.isfinite(confidence) or not .1<=confidence<=1 or not 1<=limit<=100 or offset<0:
            raise ValueError('Invalid confidence or page size')
        values = (start,end,min_duration,max_duration)
        if any(v is not None and not math.isfinite(v) for v in values) or min_duration<0 or (max_duration is not None and max_duration<min_duration) or (start is not None and end is not None and start>end):
            raise ValueError('Invalid time or duration range')
        if presence not in ('all','buffered_motion','cat','sustained','brief','uncertain'):
            raise ValueError('Invalid presence filter')
        summaries = self.saved_cat_analysis()
        with self.db() as db:
            session_settings = {r['id']:json.loads(r['settings']) for r in db.execute('SELECT id,settings FROM investigations')}
            snapshots = {r['id']:json.loads(r['config_snapshot']) for r in db.execute('SELECT id,config_snapshot FROM investigations')}
            motions = [dict(r) for r in db.execute('SELECT * FROM motions WHERE (? IS NULL OR session_id=?) ORDER BY start,id',(session_id,session_id))]
            reviews = {r['group_id']:dict(r,areas=json.loads(r['areas']),behaviors=json.loads(r['behaviors'])) for r in db.execute('SELECT * FROM motion_group_reviews')}
        grouped = defaultdict(list)
        for motion in motions:
            grouped[motion['group_id']].append(motion)
        output = []
        metrics = {area:{'motion_groups':0,'cat_groups':0,'reviewed_missed_groups':0} for area in AREAS}
        for gid, chunks in grouped.items():
            config = snapshots[chunks[0]['session_id']]
            polygons, thresholds = config['polygons'],config['area_overlap']
            a,b = min(m['start'] for m in chunks),max(m['end'] for m in chunks)
            motion_areas = sorted({area for m in chunks for area in json.loads(m['area_peaks'])})
            if motion_area=='unknown' and motion_areas or motion_area not in ('all','unknown') and motion_area not in motion_areas:
                continue
            if start is not None and b<start or end is not None and a>end or b-a<min_duration or max_duration is not None and b-a>max_duration:
                continue
            samples = [dict(s,motion_id=m['id']) for m in chunks for s in summaries.get(m['id'],{}).get('samples',[])]
            selected = [s for s in samples if model=='all' or s['model']==model]
            detections = [(s,d) for s in selected for d in s['detections'] if d['confidence']>=confidence]
            found = bool(detections)
            complete = all(summaries.get(m['id'],{}).get('status')=='complete' and
                           (model=='all' or model in summaries[m['id']]['models']) for m in chunks)
            gap = any(m['interrupted'] for m in chunks)
            label = reviews.get(gid, {'group_id':gid,'status':'unreviewed','areas':[], 'behaviors':[], 'notes':'','updated':None,'version':0})
            models = sorted({s['model'] for s in samples if any(d['confidence']>=confidence for d in s['detections'])})
            differs = any(k.startswith('yolo11m/') for k in models) and 'yolo11n/640' not in models and all('yolo11n/640' in summaries.get(m['id'],{}).get('models',[]) for m in chunks)
            assigned = [assignment(polygons,d['box'],thresholds) for _,d in detections]
            areas = sorted({a for d in assigned for a in d['areas']})
            locations = {d['location'] for d in assigned}
            overlapping = any(len(d['areas'])>1 for d in assigned)
            sustained = set()
            # Union duplicate model samples but never bridge a >1.5-second evidence gap.
            for name in AREAS:
                stamps = sorted({sample['stamp'] for (sample,_),match in zip(detections,assigned) if name in match['areas']})
                first = previous = None
                for stamp in stamps:
                    if previous is None or stamp-previous>1.5:
                        first = stamp
                    if stamp-first>=2:
                        sustained.add(name)
                    previous = stamp
            buffered = bool(motion_areas and session_settings[chunks[0]['session_id']].get('motion_buffer') is not None)
            if (presence=='buffered_motion' and not buffered or presence=='cat' and not found
                or presence=='sustained' and not sustained or presence=='brief' and (not areas or sustained)
                or presence=='uncertain' and not (differs or gap or not complete or label['status']=='uncertain')):
                continue
            for key in AREAS:
                metrics[key]['motion_groups'] += key in motion_areas
                metrics[key]['cat_groups'] += key in areas
                metrics[key]['reviewed_missed_groups'] += label['status']=='cat_confirmed' and key in label['areas'] and key not in areas
            if cat=='detected' and not found or cat=='not_detected' and (found or not complete):
                continue
            area_match = area=='all' or area in areas or area in locations or (area=='overlap' and overlapping)
            if not area_match or review!='all' and label['status']!=review:
                continue
            if analysis=='complete' and not complete or analysis=='incomplete' and complete or analysis=='gap' and not gap or disagreement and not differs:
                continue
            # A candidate-frame thumbnail is selected from the chosen model even below threshold.
            best = max(((s,d) for s in selected for d in s['detections']), key=lambda x:x[1]['confidence'], default=None)
            output.append({'id':gid,'start':a,'end':b,'duration':b-a,'motion_count':len(chunks),
                           'session_id':chunks[0]['session_id'],'motion_areas':motion_areas,'motion_ids':[m['id'] for m in chunks],'open':any(m['open'] for m in chunks),
                           'peak':max(m['peak'] for m in chunks),
                           'peak_unknown':any(m['interrupted'] and m['peak']==0 for m in chunks),
                           'analysis_gap':gap,'analysis_complete':complete,'cat_detected':found,
                           'best_confidence':best[1]['confidence'] if best else None,
                           'best_stamp':best[0]['stamp'] if best else None,
                           'best_motion_id':best[0]['motion_id'] if best else chunks[0]['id'],
                           'sustained_areas':sorted(sustained),'buffered_motion':buffered,'areas':areas,'overlapping':overlapping,'locations':sorted(locations),'models':models,'disagreement':differs,'review':label})
        output.sort(key=lambda g:(g['start'],g['id']),reverse=True)
        page = output[offset:offset+limit]
        return {'groups':page,'total':len(output),'all_groups':len(grouped),'all_motions':len(motions),
                'next_offset':offset+limit if offset+limit<len(output) else None,
                'confidence':confidence,'area_metrics':metrics,'models':sorted({model for v in summaries.values() for model in v.get('models',[])}),
                'area_basis':'intersection / cat box area; session calibration and overlap thresholds',
                'detection_basis':'latest successful saved comparison per motion; failed reruns remain incomplete; not human confirmation'}

    def motion_group_detail(self, gid):
        # A full detail uses every saved cat candidate; the UI selects model and threshold.
        with self.db() as db:
            chunks = [dict(r) for r in db.execute('SELECT * FROM motions WHERE group_id=? ORDER BY start,id',(gid,))]
        if not chunks:
            raise KeyError(gid)
        summaries = self.saved_cat_analysis()
        session = self.investigation(chunks[0]['session_id'])
        config = session['config_snapshot']
        polygons, thresholds = config['polygons'], config['area_overlap']
        a,b = min(m['start'] for m in chunks),max(m['end'] for m in chunks)
        samples = []
        for m in chunks:
            for sample in summaries.get(m['id'],{}).get('samples',[]):
                samples.append(dict(sample, motion_id=m['id'], detections=[dict(d,**assignment(polygons,d['box'],thresholds)) for d in sample['detections']]))
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
                'samples':samples,'models':sorted({model for m in chunks for model in summaries.get(m['id'],{}).get('models',[])}),
                'best_stamp':best['stamp'] if best else None,'polygons':polygons,
                'crop_context':session['settings'].get('crop_context',.5),'calibration':config.get('calibration',{}),
                'review':self.group_review(gid),'history':history,'descriptions':descriptions,
                'baseline_reasons':reasons,'overlay_max_age_seconds':.35,
                'area_overlap':thresholds,
                'area_basis':'intersection / cat box area; session calibration and thresholds; baseline reasons reflect the original run'}
