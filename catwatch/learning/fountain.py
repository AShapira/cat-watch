"""A second, fountain-only batch with native closeups and a shared hard budget."""
from collections import Counter
from copy import deepcopy
from datetime import datetime
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from zoneinfo import ZoneInfo

import cv2
import httpx
import numpy as np

from . import comparison as cloud
from .campaign import read_source, assign_assisted_pool, MODEL
from .contracts import canonical, digest
from .media import file_hash, jpeg, outbound_crop
from .store import LearningStore

CAMPAIGN = '2026-11-04-fountain-100'
MAX_INPUT = 6000
MAX_OUTPUT = 1536
FOCUS_FRAMES = 32
POLICIES = deepcopy(cloud.POLICIES)
POLICIES[MODEL]['output_limit'] = MAX_OUTPUT
PROMPT = cloud.COMPARE_PROMPT + '''
This batch investigates activity in and near a drinking fountain, not a food bowl.
Images marked Fountain detail are native-pixel closeups; Context images show the
surrounding saved area at the first/last timestamp. These are two views of the
same moments, not extra elapsed time. Assess the visible action across the sequence.
Distinguish drinking/licking at the fountain from sniffing, passing, grooming,
waiting, or eating at a neighboring food area. Do not label drinking from head
position or location alone, or eating merely because the head is lowered.
Use the clearest visible evidence and its timestamps. If contact/mouth movement
is obscured or too subtle, say what prevents classification and use unclear.
Keep evidence/uncertainty concise, normally one sentence per interval.
'''


def ledger(root):
    return cloud.Ledger(Path(root)/'cloud-comparison.sqlite3', authorization=CAMPAIGN,
                        clip_limit=100, allowed_models=[MODEL])


def previous_windows(root, clips):
    by_id = {c['id']: c for c in clips}
    windows, ids, groups = [], set(), set()
    path = Path(root)/'cloud-comparison.sqlite3'
    if not path.exists():
        return windows, ids, groups
    with read_source(path) as db:
        sent = {r['clip_id'] for r in db.execute("SELECT DISTINCT clip_id FROM requests WHERE model!='qwen3.5:9b'")}
        for row in db.execute('SELECT manifest FROM authorization'):
            m = json.loads(row['manifest'])
            for i in m['items']:
                if i['clip_id'] not in sent or 'water_fountain' not in i.get('areas', []):
                    continue
                c = by_id.get(i['clip_id'])
                if not c:
                    raise ValueError('Cannot verify prior uploaded interval: source clip metadata unavailable')
                ids.add(c['id']); groups.add(c['group_key'])
                windows.append((c['start'], c['start']+i['duration']))
    return windows, ids, groups


def focus_crop(manifest, polygons):
    """Bound fountain plus 20% vicinity to the already saved privacy crop."""
    points = polygons.get('water_fountain')
    if not points or len(points) < 3:
        raise ValueError('No saved fountain calibration for this clip')
    xs = [p[0]*manifest['width'] for p in points]; ys = [p[1]*manifest['height'] for p in points]
    dx, dy = (max(xs)-min(xs))*.2, (max(ys)-min(ys))*.2
    original = manifest['crop']
    box = [max(original[0], int(min(xs)-dx)), max(original[1], int(min(ys)-dy)),
           min(original[2], int(np.ceil(max(xs)+dx))), min(original[3], int(np.ceil(max(ys)+dy)))]
    if box[2]-box[0] < 40 or box[3]-box[1] < 40:
        raise ValueError('Fountain crop is too small or outside the saved privacy crop')
    # No downsampling: unusual large calibrations need a separately budgeted
    # payload instead of silently destroying detail or exceeding this protocol.
    if (box[2]-box[0]) > 300 or (box[3]-box[1]) > 370:
        raise ValueError('Native fountain crop exceeds the bounded closeup protocol')
    return box


def inventory(root):
    root = Path(root); clips = cloud.read_clips(root)
    windows, sent_ids, sent_groups = previous_windows(root, clips)
    now = time.time(); eligible = []
    with read_source(root.parent/'catwatch.sqlite3') as db:
        sessions = {r['id']: json.loads(r['config_snapshot']).get('polygons', {}) for r in db.execute('SELECT id,config_snapshot FROM investigations')}
        visits = [(r['id'], json.loads(r['effective'])) for r in db.execute('SELECT id,effective FROM events')]
        visits = [(i,v) for i,v in visits if v.get('area')=='water_fountain' and not v.get('rejected') and v.get('end')]
        motions = [dict(r, peaks=json.loads(r['area_peaks'])) for r in db.execute('SELECT * FROM motions')]
        for c in clips:
            m = c['manifest']; a,b = c['start'], c['start']+c['duration']
            if c['decision'] or c['id'] in sent_ids or 'water_fountain' not in m['areas']:
                continue
            if not 5.95 <= c['duration'] <= 8.01 or not outbound_crop(m) or not (root/m['video']).is_file():
                continue
            if any(a < y and x < b for x,y in windows):
                continue
            provenance = m.get('provenance', {})
            polygons = (provenance.get('original_manifest') or {}).get('calibration', {}).get('polygons') or sessions.get(provenance.get('session_id'), {})
            try:
                focus = focus_crop(m, polygons)
            except ValueError:
                continue
            overlap = lambda x: max(0., min(b,x['end'])-max(a,x['start']))
            matching = [(overlap(v), i) for i,v in visits if overlap(v)>0]
            visit_seconds, visit_id = max(matching, default=(0., None))
            nearby = [v for v in motions if overlap(v)>0]
            motion = max((v['peaks'].get('water_fountain',0) for v in nearby), default=0)
            global_change = any(min(v['peaks'].get(k,0) for k in ('water_fountain','litter_box'))>.8 for v in nearby)
            local_cat = (c['prediction'] or {}).get('subject') == 'single_cat'
            # Search the whole eligible archive, not a pre-truncated top-600 list.
            if visit_seconds <= .3 and motion <= .01 and not local_cat:
                continue
            obs = db.execute("SELECT body FROM observations WHERE stamp>=? AND stamp<? AND kind='detection' ORDER BY stamp LIMIT 24",(a,b)).fetchall()
            positives=0; near=0; max_confidence=0.; water_specific=0
            for row in obs:
                cats=[d for d in json.loads(row['body']).get('detections',[]) if d.get('label')=='cat' and d.get('confidence',0)>=.25]
                hits=[d for d in cats if 'water_fountain' in d.get('areas',[])]
                positives += bool(hits)
                for d in hits:
                    max_confidence=max(max_confidence,d['confidence'])
                water_specific += any(d.get('overlaps',{}).get('water_fountain',0)>d.get('overlaps',{}).get('eating_pad',0) for d in hits)
                # Include cats just outside the calibrated footprint, inside the
                # expanded closeup. This is proximity evidence, never a label.
                for d in cats:
                    box=d['box'];cx=(box[0]+box[2])*.5*m['width'];cy=(box[1]+box[3])*.5*m['height']
                    if focus[0]<=cx<=focus[2] and focus[1]<=cy<=focus[3]:near+=1;break
            if not (positives or near or visit_seconds>.3 or (local_cat and motion>.01)):
                continue
            n=max(1,len(obs));recent=max(0.,1-(now-a)/(7*86400))
            score=7*positives/n+3*water_specific/n+5*min(1.,visit_seconds/c['duration'])+3*recent+min(1.,motion/.1)-3*global_change
            signals={'visit_seconds':round(visit_seconds,2),'fountain_cat_observations':positives,
                     'nearby_cat_observations':near,'observations':len(obs),'water_specific_observations':water_specific,
                     'max_cat_confidence':round(max_confidence,3),'area_motion':round(motion,4),
                     'global_change':global_change,'local_cat_proposal':local_cat}
            eligible.append({**c,'target':'water_fountain','focus_crop':focus,'score':score,'signals':signals,
                             'episode_key':f'fountain-visit:{visit_id}' if visit_id is not None else c['group_key'],
                             'new_source_group':c['group_key'] not in sent_groups})
    return sorted(eligible,key=lambda c:(-c['score'],-c['start'],c['id']))


def select(candidates, count=100):
    result=[]; episodes=Counter(); groups=Counter()
    # First seek a single sample per recorded visit; then a separated second
    # view of longer visits only when needed to reach the requested 100 clips.
    for cap in (1,2):
        for c in candidates:
            if len(result)>=count:break
            if episodes[c['episode_key']]>=cap or groups[c['group_key']]>=2:continue
            if any(abs(c['start']-x['start'])<12 for x in result):continue
            result.append(c);episodes[c['episode_key']]+=1;groups[c['group_key']]+=1
    return sorted(result,key=lambda c:(-c['start'],c['id']))


def views(root, c):
    m=c['manifest'];count=FOCUS_FRAMES
    indexes=np.linspace(0,min(m['frames']-1,int(min(8.,c['duration'])*m['fps'])-1),count).astype(int)
    if len(set(indexes))!=count:raise ValueError('Not enough distinct video frames')
    wanted=set(indexes);video=cv2.VideoCapture(str(Path(root)/m['video']))
    try:
        for index in range(int(indexes[-1])+1):
            if not video.grab():raise ValueError('Missing frame; cannot fill a recording gap')
            if index not in wanted:continue
            ok,frame=video.retrieve()
            if not ok:raise ValueError('Cannot decode source frame')
            stamp=index/m['fps']
            if index in (indexes[0],indexes[-1]):
                x,y,x2,y2=m['crop'];yield stamp,'Context',frame[y:y2,x:x2]
            x,y,x2,y2=c['focus_crop'];yield stamp,'Fountain detail',frame[y:y2,x:x2]
    finally:video.release()


def prepare(root):
    root=Path(root);budget=ledger(root)
    try:return budget.manifest()
    except ValueError as error:
        if str(error)!='Prepare the explicit authorized comparison first':raise
    candidates=inventory(root); selected=select(candidates)
    folder=root/'campaigns'/CAMPAIGN;folder.mkdir(parents=True,exist_ok=True)
    (folder/'selection.json').write_text(json.dumps({'eligible':len(candidates),'selected':len(selected),
        'days':dict(Counter(c['day'] for c in selected)),'source_groups':len({c['group_key'] for c in selected}),
        'visit_groups':len({c['episode_key'] for c in selected}),
        'items':[{k:c[k] for k in ('id','day','start','duration','group_key','episode_key','score','signals','focus_crop')} for c in selected]},indent=2)+'\n')
    if len(selected)!=100:raise ValueError(f'Only {len(selected)} distinct usable fountain clips; do not pad with empty/repeated footage')
    protocol={'policies':POLICIES,'max_input_tokens':MAX_INPUT}
    maximum=100*cloud.reservation_for(MODEL,manifest=protocol)
    if budget.totals()['remaining_authorized_usd']*1e6+1e-6<maximum:
        raise ValueError('Remaining shared ceiling cannot cover all 100 bounded requests')
    items=[];evidence=cloud.Evidence(root)
    for c in selected:
        m=c['manifest']
        if file_hash(evidence.safe_path(m['video']))!=m['video_hash']:raise ValueError('Source checksum changed')
        frames=[]
        for stamp,view,frame in views(root,c):
            raw=jpeg(frame);sha=hashlib.sha256(raw).hexdigest()
            path=f'campaigns/{CAMPAIGN}/images/{sha}.jpg';target=evidence.safe_path(path)
            target.parent.mkdir(exist_ok=True);target.write_bytes(raw)
            frames.append({'time':round(stamp,6),'view':view,'path':path,'sha256':sha,'width':frame.shape[1],'height':frame.shape[0]})
        items.append({'clip_id':c['id'],'duration':min(8.,c['duration']),'start':c['start'],'day':c['day'],
            'target':'water_fountain','areas':m['areas'],'group_key':c['group_key'],'episode_key':c['episode_key'],
            'focus_crop':c['focus_crop'],'source_video_hash':m['video_hash'],'frames':frames,
            'selection':c['signals'],'rank_score':round(c['score'],3),'local_prediction':c['prediction'],
            'human_reference':None,'human_version':c['version']})
        print(json.dumps({'prepared':len(items)}),flush=True)
    manifest={'authorization':CAMPAIGN,'budget_micros':cloud.BUDGET,'created_at':cloud.now_iso(),
        'expires_epoch':time.time()+24*3600,'authority':'User requested 100 most promising activities in and near the fountain, sent to Sol; original USD20 ceiling continues.',
        'automatic_renewal':False,'max_sol_requests':100,'max_astra_requests':0,'max_frames_per_request':34,
        'max_input_tokens':MAX_INPUT,'policies':POLICIES,'dispatch_models':[MODEL],
        'price_source':cloud.PRICE_SOURCE,'price_checked_date':'2026-11-04','prompt':PROMPT,
        'prompt_version':'fountain-native-closeups-1','maximum_batch_exposure_micros':maximum,'items':items}
    budget.authorize(manifest)
    with LearningStore(root).db() as db:
        db.executemany('UPDATE clips SET pinned=1 WHERE id=?',[(i['clip_id'],) for i in items])
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    lines=['# Exact fountain-only Sol batch','',f'Fingerprint: `{digest(manifest)}`','',
        '100 previously unsent fountain time windows; 3,400 native cropped images: 32 fountain detail views plus two context views per clip.',
        'OpenAI GPT-6.1 Sol, medium. One labeling request and one matching token-count request per clip; no automatic retries or additional batches.',
        f'Input limit {MAX_INPUT:,}; output limit {MAX_OUTPUT:,} tokens per clip. Counting above the input limit stops the run before generation; no image replacement or retry.',
        f'Maximum new conservative exposure: ${maximum/1e6:.6f}, within the original $20 shared ceiling including all prior accounting.',
        'Crops remain inside the previously saved camera privacy crop. No audio/full camera frames. No model response becomes a human label automatically.','',
        '| # | Local time (Asia/Jerusalem) | Source visit/group | Selection evidence | Review |','| --- | --- | --- | --- | --- |']
    for n,i in enumerate(items,1):
        stamp=datetime.fromtimestamp(i['start'],ZoneInfo('Asia/Jerusalem')).isoformat(timespec='seconds')
        lines.append(f"| {n} | {stamp} | {i['episode_key']} | {i['selection']} | [Clip](http://localhost:8767/?campaign={CAMPAIGN}&clip={i['clip_id']}) |")
    lines+=['','The adjacent manifest lists every outgoing crop, timestamp, dimension and SHA-256. A clip is a candidate, not a confirmed drinking episode.']
    (folder/'approval.md').write_text('\n'.join(lines)+'\n')
    return manifest


def report(root):
    root=Path(root);budget=ledger(root);m=budget.manifest();rows={r['clip_id']:r for r in budget.requests()}
    items=[]
    for i in m['items']:
        r=rows.get(i['clip_id'],{});ann=r.get('body',{}).get('annotation')
        items.append({**{k:v for k,v in i.items() if k!='frames'},'state':r.get('state','pending'),
                      'annotation':ann,'local_agreement':cloud.agreement(ann,i.get('local_prediction')),
                      'inference_estimate_usd':(r.get('estimate') or 0)/1e6})
    value={'updated_at':cloud.now_iso(),'campaign':CAMPAIGN,'fingerprint':digest(m),'totals':budget.totals(),
           'states':dict(Counter(i['state'] for i in items)),'days':dict(Counter(i['day'] for i in items)),'items':items}
    (root/'campaigns'/CAMPAIGN/'results.json').write_text(json.dumps(value,indent=2)+'\n');return value


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=['scan','prepare','report','cloud']);p.add_argument('--root',default='/data/learning')
    args=p.parse_args();root=Path(args.root)
    if args.stage=='scan':
        cs=inventory(root);chosen=select(cs)
        print(json.dumps({'eligible':len(cs),'selected':len(chosen),'days':dict(Counter(c['day'] for c in chosen)),
            'groups':len({c['group_key'] for c in chosen}),'visits':len({c['episode_key'] for c in chosen}),
            'cat_observations':sum(c['signals']['fountain_cat_observations']>0 for c in chosen)}));return
    m=prepare(root);budget=ledger(root)
    if args.stage=='cloud':
        if any(r['state'] not in ('complete','invalid') for r in budget.requests()):raise ValueError('Unresolved prior request; no new dispatch or retries')
        key=json.loads(sys.stdin.readline()).get('api_key')
        if not isinstance(key,str) or not key.strip():raise ValueError('Missing API credential')
        try:
            with httpx.Client(timeout=30,trust_env=False,follow_redirects=False) as client:
                r=client.get(cloud.ENDPOINT+'/models/'+MODEL,headers={'Authorization':'Bearer '+key})
                if r.status_code!=200:raise ValueError(f'Model access HTTP {r.status_code}; no footage sent')
            assign_assisted_pool(LearningStore(root),m)
            for i in m['items']:
                cloud.cloud_one(root,budget,i,MODEL,key);result=report(root)
                print(json.dumps({k:result[k] for k in ('states','totals')}),flush=True)
                r=next(r for r in budget.requests() if r['clip_id']==i['clip_id'])
                if r['state'] not in ('complete','invalid'):raise ValueError('Unresolved request: stopped without retry')
        finally:key=None
    value=report(root);print(json.dumps({k:value[k] for k in ('fingerprint','states','totals','days')}),flush=True)


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'stopped':True,'error_type':type(error).__name__,'message':str(error) if isinstance(error,ValueError) else 'Local operation failed; inspect evidence. No automatic retry.'}),flush=True);sys.exit(1)
