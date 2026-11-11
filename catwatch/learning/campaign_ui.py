"""Local review companion, isolated from the continuous camera recorder."""
from contextlib import asynccontextmanager
import json
from pathlib import Path
import secrets
import threading
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .campaign import CAMPAIGN, MODEL, assign_assisted_pool, ledger, refresh
from . import fountain
from .contracts import ALL_LABELS
from .media import jpeg, sample
from .store import Conflict, LearningStore


def create_app(root, *, refresh_seconds=900):
    root = Path(root); store = LearningStore(root); budget = ledger(root)
    contexts = {}
    for name, selected_budget, title in ((CAMPAIGN, budget, 'Care batch — 4 November'),
            (fountain.CAMPAIGN, fountain.ledger(root), 'Fountain investigation — 100 clips')):
        try:
            manifest = selected_budget.manifest()
        except ValueError as error:
            if str(error) == 'Prepare the explicit authorized comparison first':
                continue
            raise
        contexts[name] = {'budget': selected_budget, 'manifest': manifest, 'title': title,
                          'members': {i['clip_id']: i for i in manifest['items']}}
    if CAMPAIGN not in contexts:
        raise ValueError('Original care batch is required for the review companion')
    token = secrets.token_urlsafe(32); stop = threading.Event()
    folder = root/'campaigns'/CAMPAIGN

    def gather():
        while not stop.wait(60 if not (folder/'refresh-status.json').exists() else refresh_seconds):
            try:
                candidates = refresh(root)
                result = {'updated': time.time(), 'candidates': len(candidates), 'state': 'ready'}
            except Exception as error:
                result = {'updated': time.time(), 'state': 'failed', 'error_type': type(error).__name__}
            (folder/'refresh-status.json').write_text(json.dumps(result)+'\n')

    @asynccontextmanager
    async def lifespan(app):
        thread = threading.Thread(target=gather, daemon=True); thread.start()
        yield
        stop.set(); thread.join(timeout=2)

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', 'testserver'])

    @app.middleware('http')
    async def security(request: Request, call_next):
        if request.method not in ('GET', 'HEAD'):
            origin = request.headers.get('origin')
            if origin and origin not in ('http://localhost:8767', 'http://127.0.0.1:8767'):
                return JSONResponse({'detail': 'Local origin required'}, 403)
            if not secrets.compare_digest(request.headers.get('x-catwatch-token', ''), token):
                return JSONResponse({'detail': 'Review token required'}, 403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'; frame-ancestors 'none'"
        return response

    @app.exception_handler(Conflict)
    async def conflict(request, error):
        return JSONResponse({'detail': str(error)}, 409)

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({'detail': str(error)}, 400)

    def context(request):
        name = request.query_params.get('campaign', CAMPAIGN)
        if name not in contexts:
            raise HTTPException(404, 'Unknown prepared campaign')
        return name, contexts[name]

    def item(request, ident):
        _, selected = context(request)
        if ident not in selected['members']:
            raise HTTPException(404, 'Not a member of this batch')
        return store.clip(ident)

    @app.get('/api/batches')
    def batches():
        return [{'id': name, 'title': ctx['title'], 'clips': len(ctx['members'])}
                for name, ctx in contexts.items()]

    @app.get('/')
    def index():
        return FileResponse(Path(__file__).with_name('campaign.html'))

    @app.get('/app.js')
    def script():
        return FileResponse(Path(__file__).with_name('campaign.js'), media_type='text/javascript')

    @app.get('/api/batch')
    def batch(request: Request):
        name, selected = context(request)
        budget, manifest, members = selected['budget'], selected['manifest'], selected['members']
        results = {r['clip_id']: r for r in budget.requests()}
        with store.db() as db:
            placeholders = ','.join('?' for _ in members)
            clips = {r['id']: store.decode_clip(r) for r in db.execute(
                f'SELECT * FROM clips WHERE id IN ({placeholders})', tuple(members))}
        rows = []
        for i in manifest['items']:
            c = clips[i['clip_id']]; result = results.get(c['id'], {})
            rows.append({**{k: i[k] for k in ('clip_id', 'start', 'target', 'duration', 'selection')},
                         'state': result.get('state', 'pending'), 'decision': c['decision'],
                         'skipped': c['skipped_until'] > time.time(),
                         'labels': list(dict.fromkeys(x['label'] for x in result.get('body', {}).get('annotation', {}).get('intervals', [])))})
        refresh_state = json.loads((folder/'refresh-status.json').read_text()) if (folder/'refresh-status.json').exists() else None
        return {'token': token, 'campaign': name, 'title': selected['title'], 'items': rows, 'totals': budget.totals(), 'labels': ALL_LABELS,
                'training_enabled': store.config()['training'], 'refresh': refresh_state,
                'note': 'Sol proposals need your review. Accepting records an assisted human label; training remains suspended.'}

    @app.get('/api/clips/{ident}')
    def detail(ident: str, request: Request):
        name, selected = context(request)
        budget, members = selected['budget'], selected['members']
        c = item(request, ident)
        result = next((r for r in budget.requests() if r['clip_id'] == ident), None)
        return {'id': ident, 'version': c['version'], 'duration': c['duration'], 'crop': c['manifest']['crop'],
                'focus_crop': members[ident].get('focus_crop'),
                'decision': c['decision'], 'annotation': result['body'].get('annotation') if result else None,
                'local_prediction': members[ident].get('local_prediction') if result else None,
                'state': result['state'] if result else 'pending'}

    @app.get('/api/clips/{ident}/video')
    def video(ident: str, request: Request):
        c = item(request, ident); path = store.safe_path(c['manifest']['video'])
        if not path.is_file():
            raise HTTPException(410, 'Evidence unavailable')
        return FileResponse(path, media_type='video/mp4')

    @app.get('/api/clips/{ident}/thumbnail')
    def thumbnail(ident: str, request: Request):
        return Response(jpeg(sample(store, item(request, ident), count=1)[0][1]), media_type='image/jpeg')

    @app.put('/api/clips/{ident}/decision')
    async def decision(ident: str, request: Request):
        name, selected = context(request)
        manifest = selected['manifest']
        item(request, ident)
        body = await request.json()
        if body.get('action', 'review') == 'review':
            assign_assisted_pool(store, manifest)
        result = store.review(ident, body, assisted_by=f'{MODEL}/medium review campaign={name}; human decision')
        return {'id': result['id'], 'version': result['version'], 'decision': result['decision']}

    return app
