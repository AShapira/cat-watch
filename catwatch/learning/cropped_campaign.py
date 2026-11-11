"""One authorized, cropped-only Sol campaign; separate ledger and no training."""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

import cv2
import httpx

from . import comparison as cloud
from .campaign import dense_frames
from .contracts import canonical, digest, episode_keys
from .media import file_hash, jpeg
from ..performance import PerformancePolicy, QuietDeferred

CAMPAIGN = '2026-11-09-cropped-care-sol'
MODEL = 'gpt-6.1-sol'
MAX_INPUT = 16384
MAX_OUTPUT = 2048
FRAMES = 32
NOT_BEFORE = 1794198960  # 2026-11-09 04:36 UTC
CUTOVER = 1794162402.050689
BOXES = {'water_fountain':[1180,400,1360,602],
         'eating_pad':[1257,483,1551,776], 'litter_box':[1668,309,2032,623]}
POLICIES = deepcopy(cloud.POLICIES)
POLICIES[MODEL]['output_limit'] = MAX_OUTPUT
PROMPT = cloud.COMPARE_PROMPT + '''
Each sequence is one native-pixel area crop. Location does not establish behavior.
For fountain views, distinguish visible drinking or licking at the water from
sniffing, passing, waiting, grooming and activity whose head/mouth is outside the
crop. A cat body beside a fountain does not establish drinking or eating.
For food views, require visible interaction with the food; for litter views,
distinguish entering, waiting, digging, elimination posture, covering and leaving.
Do not infer a hidden mouth action or successful elimination. Use unclear when
the relevant action is occluded or outside the crop and explain the limitation.
Keep evidence and uncertainty concise, with supporting frame times.
'''


def folder(root):
    return Path(root)/'campaigns'/CAMPAIGN


def ledger(root):
    return cloud.Ledger(folder(root)/'spending.sqlite3', authorization=CAMPAIGN,
                        clip_limit=100, allowed_models=[MODEL])


def read_db(root):
    db=sqlite3.connect((Path(root)/'agent.sqlite3').resolve().as_uri()+'?mode=ro',uri=True,timeout=20)
    db.row_factory=sqlite3.Row
    return db


def ready(root, background=True):
    if time.time()<NOT_BEFORE:
        raise ValueError('The authorized one-hour delay has not elapsed')
    if not (Path(root).parent/'.migration-verified').is_file():
        raise ValueError('Verified RHEL migration marker required; never use rollback data')
    with read_db(root) as db:
        cfg=json.loads(db.execute('SELECT body FROM settings WHERE id=1').fetchone()[0])
        paused=json.loads(db.execute("SELECT body FROM metadata WHERE key='pause_training'").fetchone()[0])
        overrides=json.loads(db.execute("SELECT body FROM metadata WHERE key='classification_crop_overrides'").fetchone()[0])
    if cfg['training'] or not paused or not cfg['continuous']:
        raise ValueError('Monitoring must be on and training paused')
    if overrides['water_fountain']['box']!=BOXES['water_fountain']:
        raise ValueError('Current fountain override differs from the authorized crop')
    with httpx.Client(timeout=10,trust_env=False) as client:
        h=client.get('http://127.0.0.1:8765/api/health').json()
    if h.get('camera')!='connected' or h.get('detector')!='ready' or not h.get('calibrated'):
        raise ValueError('Active camera/calibration is not ready')
    if not h.get('performance',{}).get('training_locked'):
        raise ValueError('Deployment training lock must remain active')
    if background and PerformancePolicy().quiet():
        raise QuietDeferred('Display policy defers campaign work until screen off')
    return h


def validate_clip(clip):
    m=clip['manifest']
    if len(m['areas'])!=1 or m['areas'][0] not in BOXES:
        raise ValueError('Only separate named area crops are authorized')
    area=m['areas'][0]
    if m['crop']!=BOXES[area] or (m['width'],m['height'])!=(2560,1440):
        raise ValueError('Crop differs from the approved area boundaries')
    if clip['start']<CUTOVER or not 5.9<=clip['duration']<=8.01:
        raise ValueError('Require a current post-tightening 6–8 second clip')
    if clip['decision']:
        raise ValueError('Do not replace or expose an existing human-reviewed clip')
    return area


def validate_manifest(m):
    if m['authorization']!=CAMPAIGN or m['dispatch_models']!=[MODEL] or m['budget_micros']!=20_000_000:
        raise ValueError('Campaign/model/budget changed')
    if not 1<=len(m['items'])<=100 or len({i['clip_id'] for i in m['items']})!=len(m['items']):
        raise ValueError('Invalid batch size or duplicate clip')
    if len(m['items'])*cloud.reservation_for(MODEL,manifest=m)>m['budget_micros']:
        raise ValueError('Entire batch worst case exceeds the campaign authorization')
    for i in m['items']:
        box=BOXES.get(i['target'])
        if i['areas']!=[i['target']] or not box or i['crop']!=box or len(i['frames'])!=FRAMES:
            raise ValueError('Nonconforming cropped evidence')
        if any((f['width'],f['height'])!=(box[2]-box[0],box[3]-box[1]) for f in i['frames']):
            raise ValueError('Image dimensions differ from the authorized crop')


def prepare(root, selection):
    ready(root)
    budget=ledger(root)
    try:
        old=budget.manifest();validate_manifest(old);return old
    except ValueError as error:
        if str(error)!='Prepare the explicit authorized comparison first':raise
    clips=cloud.read_clips(root);by_id={c['id']:c for c in clips};episodes=episode_keys(clips)
    chosen=json.loads(Path(selection).read_text())['items']
    if len({i['clip_id'] for i in chosen})!=len(chosen):raise ValueError('Duplicate selection')
    evidence=cloud.Evidence(root);target=folder(root);target.mkdir(parents=True,exist_ok=True)
    (target/'images').mkdir(exist_ok=True);(target/'previews').mkdir(exist_ok=True)
    items=[]
    for selected in chosen:
        ready(root)
        c=by_id[selected['clip_id']];area=validate_clip(c);m=c['manifest']
        path=evidence.safe_path(m['video'])
        if file_hash(path)!=m['video_hash']:raise ValueError('Source video hash changed')
        frames=[]
        for stamp,frame in dense_frames(evidence,c,FRAMES):
            raw=jpeg(frame);sha=hashlib.sha256(raw).hexdigest()
            rel=f'campaigns/{CAMPAIGN}/images/{sha}.jpg';evidence.safe_path(rel).write_bytes(raw)
            frames.append({'time':round(stamp,6),'path':rel,'sha256':sha,
                           'width':frame.shape[1],'height':frame.shape[0]})
        # Keep the comparison video cropped too; originals remain owned locally.
        x,y,x2,y2=m['crop'];preview=target/'previews'/f"{c['id']}.mp4"
        subprocess.run(['ffmpeg','-nostdin','-v','error','-threads','1','-i',str(path),
            '-vf',f'crop={x2-x}:{y2-y}:{x}:{y}:exact=1,pad=ceil(iw/2)*2:ceil(ih/2)*2',
            '-filter_threads','1','-an','-c:v','libx264','-threads','1','-preset','fast','-crf','18',
            '-pix_fmt','yuv420p','-movflags','+faststart','-y',str(preview)],
            check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=90)
        items.append({'clip_id':c['id'],'start':c['start'],'day':c['day'],'duration':c['duration'],
            'target':area,'areas':[area],'crop':m['crop'],'group_key':c['group_key'],
            'episode_key':episodes[c['id']],'source_video_hash':m['video_hash'],
            'source_hashes':m['source_hashes'],'source_video':m['video'],
            'frames':frames,'preview':str(preview.relative_to(root)),
            'selection_reason':selected['reason'],'local_prediction':c['prediction'],
            'human_reference':None,'human_version':c['version']})
        print(json.dumps({'prepared':len(items),'area':area}),flush=True)
    m={'authorization':CAMPAIGN,'created_at':cloud.now_iso(),'expires_epoch':time.time()+86400,
       'authority':'User 2026-11-09: new cropped Sol batch, fountain primary, up to USD20; one-hour delay elapsed.',
       'budget_micros':20_000_000,'automatic_renewal':False,'dispatch_models':[MODEL],
       'max_input_tokens':MAX_INPUT,'max_frames_per_request':FRAMES,'policies':POLICIES,
       'price_checked_date':'2026-11-09','price_source':cloud.PRICE_SOURCE,
       'prompt':PROMPT,'prompt_version':'cropped-care-visible-actions-1','items':items}
    validate_manifest(m);budget.authorize(m)
    (target/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
    # Only protect the selected immutable sources; do not change labels/splits.
    with sqlite3.connect(Path(root)/'agent.sqlite3',timeout=20) as db:
        db.executemany('UPDATE clips SET pinned=1 WHERE id=?',[(i['clip_id'],) for i in items])
    return m


def report(root):
    budget=ledger(root);m=budget.manifest();requests={r['clip_id']:r for r in budget.requests()}
    items=[]
    for i in m['items']:
        r=requests.get(i['clip_id'],{});body=r.get('body',{})
        items.append({**{k:v for k,v in i.items() if k!='frames'},'state':r.get('state','pending'),
            'annotation':body.get('annotation'),'usage':body.get('usage'),
            'response_model':body.get('returned_model'),'elapsed_seconds':body.get('elapsed_seconds'),
            'inference_estimate_usd':(r.get('estimate') or 0)/1e6,
            'conservative_exposure_usd':(r.get('accounted') or 0)/1e6,
            'agreement_with_saved_qwen':cloud.agreement(body.get('annotation'),i.get('local_prediction'))})
    result={'campaign':CAMPAIGN,'updated_at':cloud.now_iso(),'fingerprint':digest(m),
            'states':dict(Counter(i['state'] for i in items)),'totals':budget.totals(),
            'areas':dict(Counter(i['target'] for i in items)),
            'unique_episode_count':len({i['episode_key'] for i in items}),'items':items}
    (folder(root)/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    (folder(root)/'requests.json').write_text(json.dumps(budget.requests(),indent=2)+'\n')
    return result


def record_exposure(root, m):
    """Mark shown proposals as assisted; never submit a human annotation."""
    marker='model_exposure:'+CAMPAIGN
    with sqlite3.connect(Path(root)/'agent.sqlite3',timeout=20) as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM metadata WHERE key=?',(marker,)).fetchone():return
        cfg=json.loads(db.execute('SELECT body FROM settings WHERE id=1').fetchone()[0])
        if cfg['training']:raise ValueError('Training must remain paused')
        changed=[]
        for i in m['items']:
            r=db.execute('SELECT bucket,split,version,decision FROM clips WHERE id=?',(i['clip_id'],)).fetchone()
            if r[3]:raise ValueError('Human review appeared during campaign; inspect exposure')
            changed.append({'clip_id':i['clip_id'],'previous_bucket':r[0],'split':r[1],
                            'version':r[2],'group_key':i['group_key'],'episode_key':i['episode_key'],
                            'source_hashes':i['source_hashes']})
            db.execute("UPDATE clips SET bucket='audit' WHERE id=?",(i['clip_id'],))
        exposure={'created_at':cloud.now_iso(),'model':MODEL,'manifest_fingerprint':digest(m),
                  'human_reviews_submitted':0,'clips':changed,
                  'limitation':'Related episodes/source groups must be excluded from independent evaluation after this assisted report.'}
        db.execute('INSERT INTO metadata VALUES (?,?)',(marker,canonical(exposure)))
    (folder(root)/'model-exposure.json').write_text(json.dumps(exposure,indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['prepare','cloud','report'])
    parser.add_argument('--root',type=Path,default=Path('/data/learning'))
    parser.add_argument('--selection',type=Path)
    args=parser.parse_args();root=args.root
    if args.stage=='prepare':
        m=prepare(root,args.selection)
        print(json.dumps({'prepared':len(m['items']),'fingerprint':digest(m),
                          'worst_case_usd':len(m['items'])*cloud.reservation_for(MODEL,manifest=m)/1e6}),flush=True)
        return
    if args.stage=='cloud':
        ready(root);budget=ledger(root);m=budget.manifest();validate_manifest(m)
        if any(r['state'] not in ('complete','invalid') for r in budget.requests()):
            raise ValueError('Unresolved prior request: no automatic resend')
        key=json.loads(sys.stdin.readline()).get('api_key','')
        if not isinstance(key,str) or not key.strip():raise ValueError('Missing API credential')
        try:
            with httpx.Client(timeout=30,trust_env=False,follow_redirects=False) as client:
                r=client.get(cloud.ENDPOINT+'/models/'+MODEL,headers={'Authorization':'Bearer '+key})
                if r.status_code!=200:raise ValueError(f'Model access HTTP {r.status_code}; no footage sent')
            for i in m['items']:
                ready(root)
                cloud.cloud_one(root,budget,i,MODEL,key)
                value=report(root)
                print(json.dumps({'states':value['states'],'totals':value['totals']}),flush=True)
                row=next(r for r in budget.requests() if r['clip_id']==i['clip_id'])
                if row['state'] not in ('complete','invalid'):
                    raise ValueError('Unresolved request: stopped without retry')
            record_exposure(root,m)
        finally:key=None
    value=report(root)
    print(json.dumps({k:value[k] for k in ['states','totals','areas','unique_episode_count']}),flush=True)


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'stopped':True,'error_type':type(error).__name__,
              'message':str(error) if isinstance(error,(ValueError,QuietDeferred)) else 'Local operation failed; inspect durable evidence without resending.'}),flush=True)
        sys.exit(2 if isinstance(error,QuietDeferred) else 1)
