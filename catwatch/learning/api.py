"""Local authenticated interfaces for learning and monitoring."""
import json
import os
import time

from fastapi import Body, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response

from . import cloud
from .contracts import ALL_LABELS, LABELS, coarse
from .media import jpeg, sample
from .monitoring import acknowledge, presentation_events, summary
from .store import Conflict
from .training import make_dataset
from .worker import Agent


def install(app, source, runtime):
    agent = Agent(source, runtime)
    store = agent.store
    app.state.agent = agent

    @app.exception_handler(Conflict)
    async def conflict(request, error):
        return JSONResponse({'detail': str(error)}, 409)

    @app.get('/api/learning/status')
    def status():
        from ..performance import policy_for
        state = store.status()
        state['performance'] = policy_for(runtime).status()
        state.update(labels=ALL_LABELS, inference=store.meta('inference', {}), gpu=store.meta('gpu', {}),
                     review_only=bool(runtime.state.get('review_only')),
                     heavy_worker=store.meta('heavy_worker', {}),
                     training_progress=store.meta('training_progress', {}),
                     telegram_configured=bool(os.environ.get('CATWATCH_TELEGRAM_TOKEN')),
                     cloud_configured=bool(os.environ.get('CATWATCH_OPENAI_API_KEY')),
                     prepared_dataset_available=os.path.isdir(os.environ.get('CATWATCH_PREPARED_DATASET', '/legacy-dataset')))
        with source.db() as db:
            state['archive'] = {'investigations': db.execute('SELECT COUNT(*) FROM investigations').fetchone()[0],
                                'groups': db.execute('SELECT COUNT(DISTINCT group_id) FROM motions').fetchone()[0],
                                'group_reviews': db.execute('SELECT COUNT(*) FROM motion_group_reviews').fetchone()[0]}
        return state

    @app.put('/api/learning/settings')
    def settings(body: dict = Body(...)):
        return store.configure(body)

    @app.post('/api/learning/import')
    def import_existing():
        store.enqueue('import', 'prepared-dataset', {})
        with store.db() as db:
            db.execute("UPDATE jobs SET state='queued',next_at=0 WHERE kind='import' AND state IN ('complete','failed')")
        return {'queued': True}

    @app.post('/api/learning/discover')
    def discover():
        agent.discover()
        return {'queued': True}

    @app.get('/api/learning/decisions')
    def decisions():
        return store.review_queue()

    @app.get('/api/learning/clips')
    def clips(limit: int = 50, offset: int = 0, reviewed: bool | None = None):
        return store.clips(limit=limit, offset=offset, reviewed=reviewed)

    @app.get('/api/learning/clips/{ident}')
    def clip(ident: str):
        return store.clip(ident, blind=True)

    @app.get('/api/learning/clips/{ident}/video')
    def video(ident: str):
        path = store.safe_path(store.clip(ident)['manifest']['video'])
        if not path.is_file():
            raise HTTPException(410, 'Evidence unavailable')
        return FileResponse(path, media_type='video/mp4')

    @app.get('/api/learning/clips/{ident}/thumbnail')
    def thumbnail(ident: str):
        return Response(jpeg(sample(store, store.clip(ident), count=1)[0][1]), media_type='image/jpeg')

    @app.put('/api/learning/clips/{ident}/decision')
    def review(ident: str, body: dict = Body(...)):
        return store.review(ident, body)

    @app.get('/api/learning/export')
    def export():
        with store.db() as db:
            rows = [store.decode_clip(r) for r in db.execute('SELECT * FROM clips WHERE decision IS NOT NULL ORDER BY start,id')]
        tasks = []
        for c in rows:
            annotation = c['decision']
            results = [{'id': str(n), 'from_name': 'activity', 'to_name': 'video', 'type': 'timelinelabels',
                        'value': {'ranges': [{'start': int(i['start']*c['manifest']['fps'])+1,
                                             'end': min(c['manifest']['frames'], max(int(i['start']*c['manifest']['fps'])+1, round(i['end']*c['manifest']['fps'])))}],
                                  'timelinelabels': [i['label']]}}
                       for n, i in enumerate(annotation['intervals'])]
            for key in ('subject', 'coverage', 'quality'):
                value = annotation[key]
                results.append({'from_name': key, 'to_name': 'video', 'type': 'choices',
                                'value': {'choices': value if isinstance(value, list) else [value]}})
            tasks.append({'id': c['id'], 'data': {'video': f"/api/learning/clips/{c['id']}/video"},
                          'meta': {'manifest': c['manifest'], 'revision': c['version']},
                          'annotations': [{'id': c['version'], 'result': results, 'was_cancelled': False}]})
        return JSONResponse(tasks, headers={'Content-Disposition': 'attachment; filename="cat-watch-labels.json"'})

    @app.get('/api/learning/jobs')
    def jobs():
        return store.jobs()

    @app.post('/api/learning/jobs/{job_id}/retry')
    def retry(job_id: int):
        with store.db() as db:
            row = db.execute('SELECT state FROM jobs WHERE id=?', (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row['state'] not in ('failed', 'queued'):
                raise ValueError('Only waiting or failed work can be retried')
            db.execute("UPDATE jobs SET state='queued',next_at=0,attempts=0,error=NULL WHERE id=?", (job_id,))
        return {'queued': True}

    @app.post('/api/learning/datasets')
    def dataset():
        return make_dataset(store)

    @app.post('/api/learning/train')
    def train():
        from ..performance import training_locked
        if training_locked():
            raise ValueError('Training is paused by the workstation deployment policy')
        if any(m['state'] == 'shadow' and m['body'].get('qualified_classes') for m in store.models()):
            raise ValueError('A candidate is undergoing shadow evaluation; finish or invalidate it before another training cycle')
        if not store.status()['training_ready']:
            raise ValueError('Confirm 30 independent episodes per care behavior before exploratory training')
        data = make_dataset(store)
        if not all(data['splits'].get(s) for s in ('train', 'validation', 'test')):
            raise ValueError('Collect independent recording days for all three dataset splits')
        store.enqueue('train', data['id'], {'dataset_id': data['id']})
        return {'dataset_id': data['id'], 'queued': True}

    @app.post('/api/learning/models/rollback')
    def rollback():
        cfg = store.config()
        if not cfg['previous_model']:
            raise ValueError('No previous qualified model is available')
        previous = store.model(cfg['previous_model'])
        if previous['state'] == 'invalidated':
            raise ValueError('The previous model was invalidated by corrected labels')
        if cfg['active_model']:
            active = store.model(cfg['active_model'])
            store.save_model(active['id'], 'retired', active['body'])
        store.save_model(previous['id'], 'active', previous['body'])
        return store.configure({'active_model': previous['id'], 'previous_model': cfg['active_model']}, internal=True)

    @app.get('/api/learning/cloud')
    def cloud_batches():
        with store.db() as db:
            ids = [r[0] for r in db.execute('SELECT id FROM cloud_batches ORDER BY created DESC LIMIT 20')]
        return {'models': cloud.policies(), 'batches': [cloud.batch(store, i) for i in ids]}

    @app.post('/api/learning/cloud')
    def propose_cloud(body: dict = Body(...)):
        return cloud.propose(store, body)

    @app.post('/api/learning/cloud/{ident}/approve')
    def approve_cloud(ident: str, body: dict = Body(...)):
        return cloud.approve(store, ident, body.get('fingerprint'))

    @app.post('/api/learning/cloud/{ident}/revoke')
    def revoke_cloud(ident: str):
        return cloud.revoke(store, ident)

    @app.get('/api/learning/cloud/{ident}/images/{item}/{index}')
    def cloud_image(ident: str, item: int, index: int):
        data = cloud.batch(store, ident)
        if not 0 <= item < len(data['manifest']['items']) or not 0 <= index < len(data['manifest']['items'][item]['images']):
            raise HTTPException(404)
        return FileResponse(store.safe_path(data['manifest']['items'][item]['images'][index]['path']), media_type='image/jpeg')

    @app.get('/api/monitoring/today')
    def today():
        from ..performance import policy_for
        now = time.time()
        return {**summary(store, now-86400, now), 'events': presentation_events(store, now-86400, now)[-100:],
                'notices': store.notices(), 'baseline': store.meta('baseline', {'ready': False, 'valid_days': 0}),
                'continuous': store.config()['continuous'], 'performance': policy_for(runtime).status()}

    @app.post('/api/monitoring/start')
    def start_monitoring(body: dict = Body(...)):
        return agent.start_monitoring(body.get('calibration_id'))

    @app.post('/api/monitoring/stop')
    def stop_monitoring():
        return agent.stop_monitoring()

    @app.put('/api/monitoring/notices/{ident}')
    def notice(ident: str, body: dict = Body(...)):
        acknowledge(store, ident, body)
        return {'saved': True}

    return agent
