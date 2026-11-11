"""Durable local work, independent of an interactive assistant session."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import httpx

from .contracts import PROMPT, PROMPT_VERSION, canonical, digest
from .media import extract, import_prepared, jpeg, sample
from .store import LearningStore


class Agent:
    def __init__(self, store, runtime):
        self.source, self.runtime = store, runtime
        self.store = LearningStore(store.root/'learning')
        self.stop = threading.Event()
        self.threads = []
        self.training = None
        self.training_job = None
        self.last_discovery = 0
        self.next_local_probe = 0
        self.local_ready = False
        runtime.learning = self.store
        runtime.retention.learning = self.store

    def start(self):
        # Only the patched worker starting may retire the online legacy bridge;
        # read-only viewers and ordinary LearningStore users must leave it active.
        from .crop_policy import remove_queue_bridge
        with self.store.db() as db:
            remove_queue_bridge(db)
        self.store.recover()
        prepared = Path(os.environ.get('CATWATCH_PREPARED_DATASET', '/legacy-dataset'))
        if (prepared/'.cat-watch-dataset').is_file():
            self.store.enqueue('import', 'prepared-dataset', {})
        for name, function in [('agent', self.control), ('teacher', self.heavy), ('behavior', self.infer)]:
            thread = threading.Thread(target=function, daemon=True, name='catwatch-'+name)
            thread.start()
            self.threads.append(thread)

    def shutdown(self):
        self.stop.set()
        self.store.set_meta('pause_training', True)
        for thread in self.threads:
            thread.join(timeout=3)
        if self.training and self.training.poll() is None:
            try:
                self.training.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.training.terminate()
                self.training.wait(timeout=5)

    def start_monitoring(self, calibration_id):
        if self.store.config()['continuous']:
            raise ValueError('Continuous monitoring is already running')
        # This existing method verifies explicit fresh calibration and snapshots it.
        session = self.source.start_investigation({'calibration_id': calibration_id, 'duration_seconds': 86400,
                                                   'analysis_mode': 'live', 'masks': (self.source.preparation() or {}).get('masks', [])})
        self.store.configure({'continuous': True, 'calibration_id': calibration_id}, internal=True)
        self.store.set_meta('monitor_session', session['id'])
        self.runtime.preview_enabled = False
        return session

    def stop_monitoring(self):
        self.store.configure({'continuous': False}, internal=True)
        self.store.set_meta('pause_training', True)
        return self.source.stop_investigation()

    def discover(self):
        now = time.time()
        with self.source.db() as db:
            groups = db.execute('SELECT session_id,group_id,MIN(start) start,MAX(end) end,MAX(open) open FROM motions GROUP BY session_id,group_id').fetchall()
            visits = db.execute('SELECT id,effective FROM events').fetchall()
        intervals = []
        for g in groups:
            session = self.source.investigation(g['session_id'])
            intervals.append((f"motion:{g['session_id']}:{g['group_id']}", g['start']-5,
                              min(g['end']+5, now-6), session, not g['open']))
        session = self.source.investigation()
        for v in visits:
            e = json.loads(v['effective'])
            if session and e['start'] >= session['start'] and not e['rejected']:
                intervals.append((f"visit:{v['id']}", e['start']-5, min(e['end']+5, now-6), session, not e['open']))
        if session and self.store.config()['continuous']:
            # Deterministic random offsets survive restarts without selecting a new sample.
            first = max(session['start'], now-1800)
            for bucket in range(int(first//900), int(now//900)+1):
                a = bucket*900 + int(digest(['audit', bucket])[:8], 16) % 870
                if session['start'] <= a and a+10 < now-6:
                    intervals.append((f'audit:{bucket}', a, a+10, session, True))
        for key, a, b, session, complete in intervals:
            marker = ['discovered', b, complete]
            if self.store.meta('discovery:'+key) == marker:
                continue
            a = max(a, session['start'])
            for index in range(max(0, int((b-a+5.999)//6))):
                start, end = a+index*6, min(a+index*6+8, b)
                if end-start < 1 or not complete and end-start < 8:
                    continue
                payload = {'start': start, 'end': end, 'session_id': session['id'], 'group_key': key,
                           'polygons': session['config_snapshot']['polygons'], 'kind': key.split(':')[0]}
                self.store.enqueue('extract', digest([key, start, end]), payload)
            self.store.set_meta('discovery:'+key, marker)

    def control(self):
        from .monitoring import deliver_one, tick
        from .scene import SceneGuard
        scene = SceneGuard()
        last_tick = 0
        while not self.stop.is_set():
            try:
                cfg = self.store.config()
                now = time.time()
                if cfg['continuous']:
                    sid = self.store.meta('monitor_session')
                    current = self.source.investigation()
                    if not current or current['id'] != sid or current['stop'] is not None:
                        self.store.configure({'continuous': False}, internal=True)
                    else:
                        with self.source.db() as db:
                            db.execute('UPDATE investigations SET deadline=? WHERE id=? AND stop IS NULL', (now+86400, sid))
                if cfg['enabled']:
                    if now-self.last_discovery >= 60:
                        self.discover()
                        self.last_discovery = now
                    job = self.store.claim('extract')
                    if job:
                        try:
                            with self.source.lock:
                                segments = [s for s in self.source.segments() if s['end'] > job['payload']['start'] and s['start'] < job['payload']['end']]
                                for s in segments:
                                    self.runtime.retention.leases[s['id']] = self.runtime.retention.leases.get(s['id'], 0)+1
                            try:
                                ids = extract(self.store, self.source, job['payload'])
                            finally:
                                with self.source.lock:
                                    for s in segments:
                                        self.runtime.retention.leases[s['id']] -= 1
                            self.store.finish(job['id'], {'clips': ids})
                        except Exception as error:
                            self.store.finish(job['id'], error=str(error)[:250],
                                              retry_after=300 if job['attempts'] < 3 else None)
                if now-last_tick >= 15:
                    if cfg['continuous'] and now-(self.runtime.state.get('last_frame') or 0) < 20:
                        scene.check(self.source, self.runtime, self.store)
                    tick(self.store, self.runtime, now)
                    deliver_one(self.store)
                    last_tick = now
                self.store.set_meta('worker', {'state': 'running', 'updated': time.time(),
                                    'message': 'Collecting evidence and preparing decisions'})
            except Exception as error:
                self.store.set_meta('worker', {'state': 'waiting', 'updated': time.time(),
                                    'message': f'{type(error).__name__}: {str(error)[:250]}'})
            self.stop.wait(2)

    def label(self, clip_id):
        from ..performance import QuietDeferred, policy_for
        cfg = self.store.config()
        clip = self.store.clip(clip_id)
        # Four eight-second windows cover older prepared clips without inventing
        # action boundaries from a single still or prose description.
        intervals, qualities, subjects = [], set(), set()
        with httpx.Client(timeout=180, follow_redirects=False, trust_env=False) as client:
            loaded = client.get(cfg['ollama_url']+'/api/ps', timeout=5)
            loaded.raise_for_status()
            model = next((m for m in loaded.json()['models'] if m['name'] == cfg['ollama_model']), None)
            if not model:
                raise ValueError('Local Qwen is not loaded; waiting without changing the shared service')
            for a in range(0, int(clip['duration'])+1, 8):
                b = min(a+8, clip['duration'])
                if b-a < .05:
                    continue
                key = f"label:{clip_id}:{model['digest']}:{PROMPT_VERSION}:{a}"
                answer = self.store.meta(key)
                if answer is None:
                    if policy_for(self.runtime).quiet():
                        raise QuietDeferred()
                    images, times = [], []
                    for stamp, frame in sample(self.store, clip, start=a, end=b):
                        images.append(base64.b64encode(jpeg(frame)).decode())
                        times.append(round(stamp-a, 3))
                    if policy_for(self.runtime).quiet():
                        raise QuietDeferred()
                    reply = client.post(cfg['ollama_url']+'/api/chat', headers={'X-Catwatch-Display-Managed': '1'} if policy_for(self.runtime).path else {}, json={
                        'model': cfg['ollama_model'], 'stream': False, 'think': False, 'format': 'json',
                        'options': {'num_ctx': 16384, 'num_predict': 1024, 'temperature': 0},
                        'messages': [{'role': 'system', 'content': PROMPT}, {'role': 'user',
                            'content': f'Duration {b-a:.3f}s; frame times in order: {times}.', 'images': images}]})
                    if reply.status_code == 409 and policy_for(self.runtime).path:
                        raise QuietDeferred()
                    reply.raise_for_status()
                    identity = client.get(cfg['ollama_url']+'/api/ps', timeout=5)
                    identity.raise_for_status()
                    if not any(m.get('digest') == model['digest'] for m in identity.json()['models']):
                        raise ValueError('Local model changed during annotation; retry with consistent provenance')
                    from .contracts import normalize
                    answer = normalize(json.loads(reply.json()['message']['content']), b-a, proposal=True)
                    self.store.set_meta(key, answer)
                intervals.extend({**i, 'start': i['start']+a, 'end': i['end']+a} for i in answer['intervals'])
                subjects.add(answer['subject']); qualities.update(answer['quality'])
        subject = 'multiple_cats' if 'multiple_cats' in subjects else 'uncertain_presence' if 'uncertain_presence' in subjects else 'single_cat' if 'single_cat' in subjects else 'no_cat'
        if subject in ('multiple_cats', 'uncertain_presence'):
            intervals = [{**i, 'label': 'unclear'} for i in intervals]
        return self.store.prediction(clip_id, {'subject': subject, 'quality': sorted(qualities), 'intervals': intervals},
                                     {'provider': 'ollama', 'model': cfg['ollama_model'], 'digest': model['digest'],
                                      'prompt_version': PROMPT_VERSION, 'sampling': '16 frames / 8 seconds; native area crops'})

    def heavy(self):
        from ..performance import QuietDeferred, policy_for, training_locked
        from .cloud import dispatch_one
        from .training import gpu_free_mib, make_dataset
        while not self.stop.is_set():
            try:
                cfg = self.store.config()
                if training_locked() or policy_for(self.runtime).quiet():
                    self.store.set_meta('pause_training', True)
                if policy_for(self.runtime).quiet():
                    self.store.set_meta('heavy_worker', {'state': 'quiet', 'updated': time.time(),
                        'message': 'Quiet mode: recording and evidence collection continue; model proposals wait for the screen to turn off.'})
                    self.stop.wait(1)
                    continue
                if not cfg['enabled']:
                    self.store.set_meta('pause_training', True)
                    self.stop.wait(5)
                    continue
                if self.training:
                    if self.training.poll() is None:
                        lag = self.runtime.state.get('detector_lag_seconds', 0) or 0
                        self.store.set_meta('pause_training', not cfg['training'] or lag > 15)
                        self.stop.wait(3)
                        continue
                    job = self.training_job
                    result = self.store.meta('training_result:'+job['payload']['dataset_id']) or {'error': 'Training worker exited unexpectedly'}
                    self.training = None
                    if result.get('paused'):
                        self.store.finish(job['id'], error=result['reason'], retry_after=300)
                    elif result.get('error'):
                        self.store.finish(job['id'], error=result['error'])
                    else:
                        self.store.finish(job['id'], result)
                    self.training_job = None
                job = self.store.claim('import')
                if job:
                    try:
                        root = os.environ.get('CATWATCH_PREPARED_DATASET', '/legacy-dataset')
                        self.store.finish(job['id'], {'imported': import_prepared(self.store, root)})
                    except Exception as error:
                        self.store.finish(job['id'], error=str(error)[:250])
                    continue
                dispatch_one(self.store)
                try:
                    free = gpu_free_mib()
                except (ImportError, RuntimeError):
                    free = 0
                self.store.set_meta('gpu', {'free_mib': free, 'updated': time.time()})
                if cfg['training'] and free >= cfg['training_free_mib']:
                    status = self.store.status()
                    count = status['counts'].get('reviewed', 0)
                    last = self.store.meta('last_training', {'count': -50, 'stamp': 0})
                    if (status['training_ready'] and not any(m['state'] == 'shadow' and m['body'].get('qualified_classes') for m in status['models'])
                        and (count-last['count'] >= 50 or self.store.meta('model_invalidated_since', 0) > last['stamp'])
                        and time.time()-last['stamp'] >= 86400):
                        dataset = make_dataset(self.store)
                        if all(dataset['splits'].get(s) for s in ('train', 'validation', 'test')):
                            self.store.enqueue('train', dataset['id'], {'dataset_id': dataset['id']})
                            self.store.set_meta('last_training', {'count': count, 'stamp': time.time()})
                    job = None if any(m['state'] == 'shadow' and m['body'].get('qualified_classes') for m in status['models']) else self.store.claim('train')
                    if job:
                        self.store.set_meta('pause_training', False)
                        self.store.set_meta('training_result:'+job['payload']['dataset_id'], None)
                        self.training = subprocess.Popen([sys.executable, '-m', 'catwatch.learning.training',
                            '--root', str(self.store.root), '--dataset', job['payload']['dataset_id']],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        self.training_job = job
                        continue
                if free >= cfg['gpu_reserve_mib'] and time.time() >= self.next_local_probe:
                    self.next_local_probe = time.time()+60
                    try:
                        with httpx.Client(timeout=5, trust_env=False) as client:
                            response = client.get(cfg['ollama_url']+'/api/ps')
                            response.raise_for_status()
                            loaded = response.json()['models']
                            self.local_ready = any(m['name'] == cfg['ollama_model'] for m in loaded)
                            if not self.local_ready and free >= 8192:
                                response = client.post(cfg['ollama_url']+'/api/generate',
                                    json={'model': cfg['ollama_model'], 'stream': False}, timeout=180)
                                response.raise_for_status()
                                self.local_ready = True
                    except Exception:
                        self.local_ready = False
                    if not self.local_ready:
                        self.store.set_meta('heavy_worker', {'state': 'waiting', 'message': 'Local Qwen is unavailable. Evidence review remains available; checking again in one minute.'})
                if free >= cfg['gpu_reserve_mib'] and self.local_ready:
                    self.store.set_meta('heavy_worker', {'state': 'running',
                        'message': 'Local Qwen is ready; preparing behavior proposals for review.',
                        'updated': time.time()})
                    job = self.store.claim('label')
                    if job:
                        try:
                            result = self.label(job['payload']['clip_id'])
                            self.store.finish(job['id'], {'status': result['status']})
                        except QuietDeferred:
                            self.store.defer(job['id'])
                        except Exception:
                            if policy_for(self.runtime).quiet():
                                self.store.defer(job['id'])
                            else:
                                self.store.finish(job['id'], error='Local model unavailable or response invalid; review remains available',
                                                  retry_after=300 if job['attempts'] < 3 else None)
                            self.store.set_meta('heavy_worker', {'state': 'waiting',
                                'message': 'The latest local proposal could not be completed; retrying while evidence review remains available.',
                                'updated': time.time()})
            except Exception as error:
                self.store.set_meta('heavy_worker', {'state': 'waiting', 'message': f'{type(error).__name__}: {str(error)[:200]}'})
            self.stop.wait(3)

    def infer(self):
        from ..performance import policy_for
        from .inference import LiveClassifier
        classifier = LiveClassifier(self.store, self.source, self.runtime)
        while not self.stop.is_set():
            try:
                if self.store.config()['continuous'] and not policy_for(self.runtime).quiet():
                    classifier.step()
            except Exception:
                self.store.set_meta('inference', {'state': 'waiting', 'message': 'Behavior model or fresh evidence unavailable'})
            self.stop.wait(1)
