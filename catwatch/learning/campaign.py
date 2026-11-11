"""Focused local acquisition and one explicitly requested Sol batch; never trains."""
from collections import Counter
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

import cv2
import httpx
import numpy as np

from . import comparison as cloud
from .contracts import canonical, digest, local_day
from .media import file_hash, jpeg, outbound_crop, sample
from .store import LearningStore
from .training import components

CAMPAIGN = '2026-11-04-care-candidates'
TARGETS = ('water_fountain', 'litter_box')
MODEL = 'gpt-6.1-sol'
FRAMES = 32


def ledger(root):
    # All campaigns share one atomic $20 ledger, including the November 3 batch.
    return cloud.Ledger(Path(root)/'cloud-comparison.sqlite3', authorization=CAMPAIGN,
                        clip_limit=100, allowed_models=[MODEL])


def read_source(path):
    db = sqlite3.connect('file:'+str(path)+'?mode=ro', uri=True, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db


def ranked_candidates(root, *, limit=600):
    """Visible visits plus area motion; neither signal is a behavior label."""
    root = Path(root)
    clips = cloud.read_clips(root)
    now = time.time()
    with read_source(root.parent/'catwatch.sqlite3') as db:
        visits = [json.loads(r['effective']) for r in db.execute('SELECT effective FROM events')]
        motions = [dict(r, peaks=json.loads(r['area_peaks'])) for r in db.execute('SELECT * FROM motions')]
        eligible = []
        for c in clips:
            m = c['manifest']
            if c['decision'] or not 5.95 <= c['duration'] <= 8.01 or not outbound_crop(m):
                continue
            target = next((t for t in TARGETS if t in m['areas']), None)
            if not target or not (root/m['video']).is_file():
                continue
            a, b = c['start'], c['start']+c['duration']
            overlap = lambda v: max(0, min(b, v['end'])-max(a, v['start']))
            visit = max((overlap(v) for v in visits if v.get('area') == target and not v.get('rejected') and v.get('end')), default=0)
            nearby = [v for v in motions if overlap(v) > 0]
            motion = max((v['peaks'].get(target, 0) for v in nearby), default=0)
            # Simultaneous near-full-area changes are often light/camera changes.
            global_change = any(min(v['peaks'].get(t, 0) for t in TARGETS) > .8 for v in nearby)
            recent = max(0, 1-(now-a)/(7*86400))
            score = 8*min(1, visit/c['duration'])+3*min(1, motion/.15)+4*recent-3*global_change
            eligible.append({**c, 'target': target, 'score': score,
                             'signals': {'visit_seconds': round(visit, 2), 'area_motion': round(motion, 4),
                                         'global_change': global_change}})
        # Only scan indexed observations for a bounded metadata shortlist.
        shortlist = []
        for target in TARGETS:
            subset = sorted((c for c in eligible if c['target'] == target), key=lambda c: (-c['score'], -c['start'], c['id']))[:limit]
            for c in subset:
                observations = db.execute("SELECT body FROM observations WHERE stamp>=? AND stamp<? AND kind='detection' ORDER BY stamp LIMIT 24",
                                          (c['start'], c['start']+c['duration'])).fetchall()
                cats = []
                for row in observations:
                    ds = json.loads(row['body']).get('detections', [])
                    cats.append(any(d.get('label') == 'cat' and d.get('confidence', 0) >= .25 and
                                    target in d.get('areas', []) for d in ds))
                fraction = sum(cats)/len(cats) if cats else 0
                c['signals'].update(cat_observations=sum(cats), observations=len(cats))
                c['score'] += 5*fraction
            shortlist.extend(c for c in subset if c['signals']['cat_observations'] > 0 or
                             c['signals']['visit_seconds'] > .3 or c['signals']['area_motion'] > .01)
    return sorted(shortlist, key=lambda c: (-c['score'], -c['start'], c['id']))


def diverse_selection(candidates, count=100):
    selected, groups = [], Counter()
    def usable(c):
        # At most two views of an episode, no overlapping camera time and a
        # 12-second neighborhood prevents adjacent extraction windows dominating.
        return groups[c['group_key']] < 2 and not any(
            abs(c['start']-x['start']) < 12 for x in selected)
    pools = {t: [c for c in candidates if c['target'] == t] for t in TARGETS}
    counts = Counter()
    while len(selected) < count:
        added = False
        for target in TARGETS:
            if counts[target] >= count//2:
                continue
            while pools[target]:
                c = pools[target].pop(0)
                if usable(c):
                    selected.append(c); groups[c['group_key']] += 1
                    counts[target] += 1; added = True
                    break
        if not added:
            break
    # Fill a shortfall using the other area's stronger distinct candidates.
    for c in candidates:
        if len(selected) >= count:
            break
        if usable(c):
            selected.append(c); groups[c['group_key']] += 1
    return sorted(selected, key=lambda c: (-c['start'], c['id']))[:count]


def refresh(root):
    """Local-only rolling shortlist. No credentials, spending, or human decisions."""
    root = Path(root); folder = root/'campaigns'/CAMPAIGN
    folder.mkdir(parents=True, exist_ok=True)
    candidates = ranked_candidates(root)
    for frozen in sorted((root/'campaigns').glob('*/manifest.json')):
        prior = json.loads(frozen.read_text())['items']
        prior_ids = {i['clip_id'] for i in prior}
        prior_groups = {i['group_key'] for i in prior}
        # The fixed review queue already owns these examples. The rolling pool
        # should accumulate fresh episodes, not repeatedly propose paid repeats.
        candidates = [c for c in candidates if c['id'] not in prior_ids and c['group_key'] not in prior_groups]
    selected = diverse_selection(candidates)
    result = {'updated_at': cloud.now_iso(), 'method': 'visits+area_motion+cat_observations+recency; 12s spacing; max2/group',
              'eligible_shortlist': len(candidates), 'items': [
                  {k: c[k] for k in ('id', 'start', 'duration', 'day', 'target', 'score', 'signals', 'group_key')}
                  for c in selected]}
    temporary = folder/'shortlist.tmp'
    temporary.write_text(json.dumps(result, indent=2)+'\n'); temporary.replace(folder/'shortlist.json')
    return selected


def dense_frames(evidence, clip, count=FRAMES):
    """Decode once in time order, avoiding 32 expensive seeks through HEVC GOPs."""
    m = clip['manifest']
    indexes = np.linspace(0, min(m['frames']-1, int(min(8., clip['duration'])*m['fps'])-1), count).astype(int)
    if len(set(indexes)) != count:
        raise ValueError('Insufficient distinct video frames')
    wanted = set(indexes); video = cv2.VideoCapture(str(evidence.safe_path(m['video'])))
    x1,y1,x2,y2 = m['crop']
    try:
        for index in range(int(indexes[-1])+1):
            ok = video.grab()
            if not ok:
                raise ValueError('Source video has missing frames')
            if index in wanted:
                ok, frame = video.retrieve()
                if not ok:
                    raise ValueError('Source frame could not be decoded')
                crop = frame[y1:y2,x1:x2]
                if crop.size == 0:
                    raise ValueError('Crop outside video')
                yield index/m['fps'], crop
    finally:
        video.release()


def prepare(root):
    root = Path(root); budget = ledger(root)
    try:
        return budget.manifest()
    except ValueError as e:
        if str(e) != 'Prepare the explicit authorized comparison first':
            raise
    selected = refresh(root)
    if len(selected) != 100:
        raise ValueError(f'Only {len(selected)} diverse usable candidates; do not pad or dispatch a partial selection silently')
    evidence = cloud.Evidence(root); folder = root/'campaigns'/CAMPAIGN
    items = []
    for c in selected:
        m = c['manifest']
        if file_hash(evidence.safe_path(m['video'])) != m['video_hash']:
            raise ValueError('Candidate checksum changed')
        duration = min(8., c['duration'])
        frames = []; sharpness = []; changes = []; previous = None
        for stamp, frame in dense_frames(evidence, c):
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            sharpness.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()))
            if previous is not None:
                changes.append(float(np.mean(cv2.absdiff(gray, previous))))
            previous = gray
            raw = jpeg(frame); sha = hashlib.sha256(raw).hexdigest()
            relative = f'campaigns/{CAMPAIGN}/images/{sha}.jpg'
            path = evidence.safe_path(relative); path.parent.mkdir(exist_ok=True); path.write_bytes(raw)
            frames.append({'time': round(stamp, 6), 'path': relative, 'sha256': sha,
                           'width': frame.shape[1], 'height': frame.shape[0]})
        items.append({'clip_id': c['id'], 'duration': duration, 'start': c['start'], 'day': c['day'],
                      'target': c['target'], 'areas': m['areas'], 'group_key': c['group_key'],
                      'source_video_hash': m['video_hash'], 'frames': frames,
                      'selection': c['signals'], 'rank_score': round(c['score'], 3),
                      'median_sharpness': round(float(np.median(sharpness)), 2),
                      'mean_frame_change': round(float(np.mean(changes)), 3),
                      'local_prediction': c['prediction'], 'human_reference': None,
                      'human_version': c['version']})
        print(json.dumps({'prepared': len(items), 'target': c['target']}), flush=True)
    manifest = {'authorization': CAMPAIGN, 'budget_micros': cloud.BUDGET,
        'created_at': cloud.now_iso(), 'expires_epoch': time.time()+24*3600,
        'authority': 'User on November 4 requested 100 best recent drinking/litter candidates sent to Sol for human acceptance; prior overall USD20 ceiling continues.',
        'automatic_renewal': False, 'max_sol_requests': 100, 'max_astra_requests': 0,
        'max_frames_per_request': FRAMES, 'max_input_tokens': cloud.MAX_INPUT,
        'policies': cloud.POLICIES, 'dispatch_models': [MODEL], 'price_checked_date': '2026-11-04',
        'price_source': cloud.PRICE_SOURCE, 'prompt': cloud.COMPARE_PROMPT,
        'prompt_version': 'paired-visible-actions-1', 'items': items}
    budget.authorize(manifest)
    with LearningStore(root).db() as db:
        db.executemany('UPDATE clips SET pinned=1 WHERE id=?', [(i['clip_id'],) for i in items])
    (folder/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    lines = ['# Focused care labeling: exact outgoing batch', '',
        f'Fingerprint: `{digest(manifest)}`', '',
        '100 clips, 3,200 native cropped JPEG frames. OpenAI GPT-6.1 Sol, medium effort only.',
        '32 timestamped frames per 6–8 second clip. No audio or full camera frames.',
        'Each clip is sent for token counting and one labeling request. No automatic retries or new batches.',
        'All spending shares the original $20 ledger; earlier exposure is retained. Unknown requests retain their reservation.',
        'Sol outputs are proposals. Only your accept/edit decisions become assisted human labels.', '',
        '| # | Local date/time (Asia/Jerusalem) | Area | Clip / local evidence | Selection signals |',
        '| --- | --- | --- | --- | --- |']
    from zoneinfo import ZoneInfo
    for n, i in enumerate(items, 1):
        local = datetime.fromtimestamp(i['start'], ZoneInfo('Asia/Jerusalem')).isoformat(timespec='seconds')
        lines.append(f"| {n} | {local} | {i['target']} | [{i['clip_id'][:12]}](http://localhost:8767/?clip={i['clip_id']}) | {i['selection']} |")
    lines += ['', 'The machine-readable manifest beside this file contains every image path, timestamp and SHA-256.']
    (folder/'approval.md').write_text('\n'.join(lines)+'\n')
    return manifest


def assign_assisted_pool(store, manifest):
    """Audited pre-training reassignment of complete connected components only."""
    marker = 'assisted_pool:'+manifest['authorization']
    with store.db() as db:
        prior = db.execute('SELECT body FROM metadata WHERE key=?', (marker,)).fetchone()
        if prior:
            return json.loads(prior['body'])
        if any(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('datasets', 'models')):
            raise ValueError('Existing datasets/models require an explicit dataset migration')
        cfg = json.loads(db.execute('SELECT body FROM settings WHERE id=1').fetchone()[0])
        if cfg.get('training', True):
            raise ValueError('Suspend training before preparing the assisted pool')
        selected = {i['clip_id'] for i in manifest['items']}
        clips = [store.decode_clip(r) for r in db.execute('SELECT * FROM clips')]
        audit = {'created_at': cloud.now_iso(), 'campaign': manifest['authorization'], 'clips': [], 'partitions': []}
        for members, keys in components(clips):
            if not selected.intersection(c['id'] for c in members):
                continue
            if any(c['decision'] and c['decision'].get('independent') for c in members):
                raise ValueError('Cannot expose or move an independently reviewed component')
            for key in keys:
                row = db.execute('SELECT split FROM partitions WHERE key=?', (key,)).fetchone()
                audit['partitions'].append({'key': key, 'previous': row[0] if row else None})
                db.execute('INSERT OR REPLACE INTO partitions VALUES (?,?)', (key, 'train'))
            for c in members:
                audit['clips'].append({'id': c['id'], 'split': c['split'], 'bucket': c['bucket']})
                # Only the selected proposals get a queue boost; all connected
                # data is training-only, so no related footage leaks into holdout.
                db.execute("UPDATE clips SET split='train',bucket='difficult',priority=MAX(priority,?) WHERE id=?",
                           (20 if c['id'] in selected else 1, c['id']))
        db.execute('INSERT INTO metadata VALUES (?,?)', (marker, canonical(audit)))
    return audit


def report(root):
    root = Path(root); budget = ledger(root); manifest = budget.manifest()
    requests = {r['clip_id']: r for r in budget.requests()}
    items = []
    for item in manifest['items']:
        row = requests.get(item['clip_id'], {})
        annotation = row.get('body', {}).get('annotation')
        items.append({**{k: v for k, v in item.items() if k != 'frames'},
                      'state': row.get('state', 'pending'), 'annotation': annotation,
                      'local_agreement': cloud.agreement(annotation, item.get('local_prediction')),
                      'inference_estimate_usd': (row.get('estimate') or 0)/1e6})
    result = {'updated_at': cloud.now_iso(), 'campaign': CAMPAIGN, 'fingerprint': digest(manifest),
              'totals': budget.totals(), 'states': dict(Counter(i['state'] for i in items)),
              'areas': dict(Counter(i['target'] for i in items)), 'days': dict(Counter(i['day'] for i in items)),
              'items': items}
    (root/'campaigns'/CAMPAIGN/'results.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=['prepare', 'cloud', 'report', 'refresh', 'serve'])
    p.add_argument('--root', default='/data/learning')
    args = p.parse_args(); root = Path(args.root)
    if args.stage == 'refresh':
        print(json.dumps({'candidates': len(refresh(root))})); return
    if args.stage == 'serve':
        import uvicorn
        from .campaign_ui import create_app
        uvicorn.run(create_app(root), host='0.0.0.0', port=8767); return
    manifest = prepare(root)
    if args.stage == 'cloud':
        budget = ledger(root)
        if any(r['state'] not in ('complete', 'invalid') for r in budget.requests()):
            raise ValueError('Unsettled request: no new dispatch or retries until reconciled')
        key = json.loads(sys.stdin.readline()).get('api_key')
        if not isinstance(key, str) or not key.strip():
            raise ValueError('Missing credential')
        try:
            with httpx.Client(timeout=30, trust_env=False, follow_redirects=False) as client:
                r = client.get(cloud.ENDPOINT+'/models/'+MODEL, headers={'Authorization': 'Bearer '+key})
                if r.status_code != 200:
                    raise ValueError(f'Sol access check HTTP {r.status_code}; no footage sent')
            # Label visibility is now committed, so move related data out of holdout.
            assign_assisted_pool(LearningStore(root), manifest)
            for item in manifest['items']:
                cloud.cloud_one(root, budget, item, MODEL, key)
                result = report(root)
                print(json.dumps({k: result[k] for k in ('states', 'totals')}), flush=True)
                row = next(r for r in budget.requests() if r['clip_id'] == item['clip_id'])
                if row['state'] not in ('complete', 'invalid'):
                    raise ValueError('Stopped on unresolved request; no automatic retry')
        finally:
            key = None
    result = report(root)
    print(json.dumps({k: result[k] for k in ('fingerprint', 'states', 'totals', 'areas', 'days')}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'stopped': True, 'type': type(error).__name__,
                          'message': str(error) if isinstance(error, ValueError) else 'See local campaign evidence; no automatic retry'}), flush=True)
        sys.exit(1)
