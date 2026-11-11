"""Short-window local inference with capture priority and source timestamps."""
import json
import time

import cv2
import numpy as np

from .contracts import LABELS, canonical, digest
from ..regions import crop_regions


class LiveClassifier:
    def __init__(self, learning, source, runtime):
        self.store, self.source, self.runtime = learning, source, runtime
        self.seen = {}
        self.models = {}

    def step(self):
        import torch
        from transformers import VideoMAEForVideoClassification, VideoMAEImageProcessor
        models = self.store.inference_models()
        self.models = {k: v for k, v in self.models.items() if k in {m['id'] for m in models}}
        if not models:
            self.store.set_meta('inference', {'state': 'waiting', 'message': 'Collect confirmed examples to train the first local model'})
            return
        segments = self.source.segments()
        if not segments:
            return
        segment = max(segments, key=lambda s: s['end'])
        if time.time()-segment['end'] > 30:
            return
        session = self.source.investigation()
        if not session:
            return
        for record in models:
            if self.seen.get(record['id']) == segment['id'] or torch.cuda.mem_get_info()[0] < 3*1024**3:
                continue
            if not self.runtime.gpu_lock.acquire(blocking=False):
                return
            with self.source.lock:
                self.runtime.retention.leases[segment['id']] = self.runtime.retention.leases.get(segment['id'], 0)+1
            try:
                if record['id'] not in self.models:
                    path = self.store.safe_path(record['body']['path'])
                    self.models[record['id']] = (VideoMAEForVideoClassification.from_pretrained(str(path), local_files_only=True),
                                                 VideoMAEImageProcessor.from_pretrained(str(path), local_files_only=True))
                model, processor = self.models[record['id']]
                cap = cv2.VideoCapture(str(self.source.root/segment['path']))
                try:
                    fps, count = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    if not 1 <= fps <= 120 or count < 2:
                        raise ValueError('Invalid source timing')
                    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    expected = session['config_snapshot'].get('calibration', {})
                    if expected.get('width', width) != width or expected.get('height', height) != height:
                        self.store.configure({'continuous': False}, internal=True)
                        self.source.stop_investigation()
                        self.store.notice('camera-dimensions:'+str(session['id']), 'system',
                                          {'text': 'Camera dimensions changed. Confirm the camera areas again before monitoring.'})
                        return
                    length = count/fps
                    starts = sorted(set([float(x) for x in range(0, max(1, int(length)-3), 2)] + [max(0., length-4)]))
                    model.to('cuda').eval()
                    results = []
                    cats = [d for d in self.runtime.detections if d.get('label') == 'cat' and d.get('confidence', 0) >= .4]
                    for offset in starts:
                        end = min(length, offset+4)
                        indexes = np.linspace(int(offset*fps), min(count-1, int(end*fps)-1), 16).astype(int)
                        frames = []
                        for index in indexes:
                            cap.set(cv2.CAP_PROP_POS_FRAMES, int(index))
                            ok, frame = cap.read()
                            if not ok:
                                raise ValueError('Incomplete inference sequence')
                            frames.append(frame)
                        for region in crop_regions(session['config_snapshot']['polygons'], width, height, .5):
                            x1, y1, x2, y2 = region['box']
                            values = processor([f[y1:y2, x1:x2, ::-1].copy() for f in frames], return_tensors='pt')['pixel_values'].to('cuda')
                            with torch.inference_mode(), torch.autocast('cuda', dtype=torch.bfloat16):
                                scores = model(pixel_values=values).logits.float().softmax(-1)[0].cpu().tolist()
                            i = max(range(len(scores)), key=scores.__getitem__)
                            label = LABELS[i] if len(cats) <= 1 and scores[i] >= record['body']['thresholds'].get(LABELS[i], 1.) else 'unclear'
                            a, b = segment['start']+offset, min(segment['end'], segment['start']+end)
                            results.append((region, label, scores[i], a, b))
                finally:
                    cap.release()
                with self.store.db() as db:
                    for region, label, score, a, b in results:
                        eid = digest([record['id'], segment['id'], region['box'], a, b])
                        qualified = record['state'] == 'active' and label in record['body']['qualified_classes']
                        candidates = db.execute('SELECT id,manifest FROM clips WHERE start<=? AND start+duration>=?', (a, b)).fetchall()
                        clip_id = next((c['id'] for c in candidates if set(json.loads(c['manifest'])['areas']) == set(region['areas'])), None)
                        db.execute('INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?,?)',
                                   (eid, a, b, label, 'model', record['id'], clip_id, int(qualified),
                                    canonical({'score': score, 'areas': region['areas'], 'segment_id': segment['id']})))
                    # Coverage is derived from actual analyzed source intervals,
                    # not the wall time between successful worker heartbeats.
                    if (self.runtime.state.get('detector') == 'ready' and len(cats) <= 1
                        and time.time()-(self.runtime.state.get('detection_stamp') or 0) < 20
                        and results and all(r[1] != 'unclear' for r in results)):
                        db.execute('INSERT INTO coverage VALUES (?,?,1) ON CONFLICT(start) DO UPDATE SET end=MAX(end,excluded.end),good=1',
                                   (segment['start'], min(segment['end'], segment['start']+length)))
                        db.execute('INSERT OR REPLACE INTO model_coverage VALUES (?,?,?)',
                                   (record['id'], segment['start'], min(segment['end'], segment['start']+length)))
                self.store.set_meta('inference_stamp', segment['end'])
                self.store.set_meta('inference', {'state': record['state'], 'model_id': record['id'], 'updated': time.time()})
                self.seen[record['id']] = segment['id']
            finally:
                if record['id'] in self.models:
                    self.models[record['id']][0].to('cpu')
                    torch.cuda.empty_cache()
                with self.source.lock:
                    self.runtime.retention.leases[segment['id']] -= 1
                self.runtime.gpu_lock.release()
