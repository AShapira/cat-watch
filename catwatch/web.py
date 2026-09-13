import csv
import io
import secrets
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.background import BackgroundTask
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .core import AREAS, BEHAVIORS, report


def create_app(store, runtime, run_worker=True):
    token = secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app):
        if run_worker:
            runtime.start()
        yield
        if run_worker:
            runtime.shutdown()

    app = FastAPI(title="cat-watch", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def local_access(request: Request, call_next):
        annotation = request.method == 'PUT' and (re.fullmatch(r'/api/investigation/groups/[0-9]+/review',request.url.path)
                       or request.url.path == '/api/investigation/area-settings')
        if request.method not in ('GET', 'HEAD') and runtime.state.get('review_only') and not annotation:
            return JSONResponse({'detail':'Review-only mode: investigation and all background work are stopped.'},403)
        if request.method not in ("GET", "HEAD") and request.headers.get("x-catwatch-token") != token:
            return JSONResponse({"detail": "Reload the local dashboard before making changes"}, 403)
        origin = request.headers.get("origin")
        if origin and origin not in ("http://127.0.0.1:8765", "http://localhost:8765"):
            return JSONResponse({"detail": "Local dashboard requests only"}, 403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; media-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({"detail": str(error)}, 400)

    @app.exception_handler(KeyError)
    async def missing(request, error):
        return JSONResponse({"detail": "Event not found"}, 404)

    @app.get("/")
    def index():
        return FileResponse(Path(__file__).parent / "static/index.html")

    @app.get("/static/{name}")
    def static(name: str):
        if name not in ("app.js", "style.css", "investigation.js"):
            raise HTTPException(404)
        return FileResponse(Path(__file__).parent / "static" / name)

    @app.get("/api/session")
    def session():
        return {"token": token, "areas": AREAS, "behaviors": BEHAVIORS}

    @app.get("/api/health")
    def health():
        return {**runtime.state, "calibrated":bool(store.config()["polygons"]), "storage": runtime.retention.last, "now": time.time(),
                "frame_age_seconds": None if runtime.state["last_frame"] is None else round(time.time()-runtime.state["last_frame"],1)}

    @app.get("/api/config")
    def config():
        return store.config()

    @app.put("/api/config")
    def configure(body: dict = Body(...)):
        return store.configure(body)

    @app.get("/api/frame")
    def frame():
        if runtime.frame is None:
            raise HTTPException(503, "Waiting for a camera frame")
        return Response(runtime.frame, media_type="image/jpeg")

    @app.get("/api/detections")
    def detections():
        return {"detections": runtime.detections, "stamp": runtime.state.get('detection_stamp',runtime.state["last_frame"])}

    @app.post('/api/calibration/preview')
    def enable_preview():
        store.require_setup()
        runtime.preview_enabled = True
        return {'preview':True}

    @app.post('/api/calibration/prepare')
    def prepare_calibration():
        source = runtime.state.get('source') or {}
        return store.prepare(runtime.frame,runtime.state['last_frame'],source.get('width'),source.get('height'))

    @app.get('/api/calibration')
    def calibration():
        return store.preparation()

    @app.get('/api/calibration/image')
    def calibration_image():
        prepared = store.preparation()
        if not prepared:
            raise HTTPException(404,'Prepare a camera image first')
        return FileResponse(store.root/prepared['reference_image'],media_type='image/jpeg')

    @app.post('/api/calibration/confirm')
    def confirm_calibration(body: dict=Body(...)):
        return store.confirm_calibration(body)

    @app.get('/api/analysis')
    def analysis_status():
        return dict(store.analysis_status(),capture_drained=runtime.analysis_ready())

    @app.post('/api/analysis/retry')
    def retry_analysis(body: dict=Body(default={})):
        if set(body)-{'session_id'} or ('session_id' in body and type(body['session_id']) is not int):
            raise ValueError('Supply an investigation ID')
        if not runtime.analysis_ready():
            raise ValueError('Capture queues and live GPU inference must finish first')
        return store.request_analysis(body.get('session_id'))

    @app.put('/api/analysis/control')
    def control_analysis(body: dict=Body(...)):
        if not runtime.analysis_ready():
            raise ValueError('Capture queues and live GPU inference must finish first')
        return store.control_analysis(body)

    @app.get('/api/investigation')
    def investigation():
        return {'session':store.investigation(), 'sessions':store.sessions(), 'health':health(),
                'preparation':store.preparation(),'analysis':store.analysis_status()}

    @app.post('/api/investigation')
    def start_investigation(body: dict = Body(default={})):
        result = store.start_investigation(body)
        runtime.preview_enabled = False
        return result

    @app.post('/api/investigation/stop')
    def stop_investigation():
        return store.stop_investigation()

    @app.patch('/api/investigation')
    def configure_investigation(body: dict = Body(...)):
        return store.configure_investigation(body)

    @app.get('/api/investigation/groups')
    def motion_groups(cat: str='all', confidence: float=.4, area: str='all', review: str='all',
                      model: str='all', analysis: str='all', disagreement: bool=False,
                      start: float | None=None, end: float | None=None,
                      min_duration: float=0., max_duration: float | None=None,
                      offset: int=0, limit: int=24, session_id: int | None=None, motion_area: str='all', presence: str='all'):
        return store.motion_group_list(cat=cat,confidence=confidence,area=area,review=review,
            model=model,analysis=analysis,disagreement=disagreement,start=start,end=end,
            min_duration=min_duration,max_duration=max_duration,offset=offset,limit=limit,session_id=session_id,motion_area=motion_area,presence=presence)

    @app.post('/api/investigation/preview-regions')
    def preview_regions(body: dict=Body(...)):
        import math
        import cv2
        from .regions import region_masks
        from .core import AREAS
        from .investigation import MOTION_DEFAULTS
        polygons=body.get('polygons',{})
        if not isinstance(polygons,dict) or set(polygons)-set(AREAS):
            raise ValueError('Invalid areas')
        for points in polygons.values():
            if (not isinstance(points,list) or len(points)>20 or any(not isinstance(p,list) or len(p)!=2 or
                any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=1 for v in p) for p in points)):
                raise ValueError('Invalid polygon coordinates')
        settings=dict(MOTION_DEFAULTS,motion_buffer=body.get('motion_buffer',.2),masks=body.get('masks',[]))
        store.validate_motion_settings(settings)
        prepared=store.preparation()
        ratio=prepared['height']/prepared['width'] if prepared else 9/16
        width,height=960,max(1,round(960*ratio))
        masks=region_masks(polygons,width,height,settings['motion_buffer'],settings['masks'])
        outlines={}
        for area,mask in masks.items():
            contours,_=cv2.findContours(mask,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
            outlines[area]=[[[float(x)/width,float(y)/height] for x,y in contour[:,0]] for contour in contours]
        return {'outlines':outlines,'motion_buffer':settings['motion_buffer']}

    @app.get('/api/investigation/area-settings')
    def area_settings():
        return {'area_overlap':store.config()['area_overlap']}

    @app.put('/api/investigation/area-settings')
    def update_area_settings(body: dict=Body(...)):
        if set(body) != {'area_overlap'}:
            raise ValueError('Only area overlap thresholds can be changed here')
        return {'area_overlap':store.configure(body)['area_overlap']}

    @app.get('/api/investigation/groups/{gid}')
    def group_detail(gid: int):
        return store.motion_group_detail(gid)

    @app.put('/api/investigation/groups/{gid}/review')
    def group_review(gid: int, body: dict=Body(...)):
        from .investigation_review import ReviewConflict
        try:
            return store.review_group(gid,body)
        except ReviewConflict as exc:
            raise HTTPException(409,str(exc)) from exc

    @app.get('/api/investigation/groups/{gid}/thumbnail')
    def group_thumbnail(gid: int, model: str='all'):
        from .investigation_review import MODELS
        if len(model)>128:
            raise ValueError('Invalid model')
        import cv2
        from .analysis import evidence_lease, sampled_frames
        with store.db() as db:
            chunks=[dict(r) for r in db.execute('SELECT * FROM motions WHERE group_id=? ORDER BY start',(gid,))]
        if not chunks:
            raise KeyError(gid)
        analysis=store.saved_cat_analysis()
        samples=[s for m in chunks for s in analysis.get(m['id'],{}).get('samples',[]) if model=='all' or s['model']==model]
        best=max(samples,key=lambda s:max(d['confidence'] for d in s['detections']),default=None)
        stamp=best['stamp'] if best else chunks[0]['start']
        with evidence_lease(runtime,stamp,stamp+.5) as segments:
            frames=sampled_frames(store.root,segments,stamp,stamp+.5,1)
            try:
                _,frame=next(frames)
                frame=cv2.resize(frame,(320,max(1,round(frame.shape[0]*320/frame.shape[1]))))
                ok,jpeg=cv2.imencode('.jpg',frame)
                if ok:
                    return Response(jpeg.tobytes(),media_type='image/jpeg')
            except StopIteration:
                pass
            finally:
                frames.close()
        raise HTTPException(410,'Evidence expired or unavailable')

    def motion_evidence(motion):
        from .analysis import covers
        clips = store.evidence(motion['start'],motion['end'])
        return {**motion,'clips':clips,'evidence':'available' if covers(clips,motion['start']-5,motion['end']+5) else 'partial' if clips else 'expired'}

    @app.get('/api/investigation/motions')
    def motions(limit: int = 50, before: int | None = None):
        items = store.motions(limit,before)
        return {'motions':[motion_evidence(m) for m in items], 'next_before':items[-1]['id'] if len(items)==limit else None}

    @app.get('/api/investigation/motions/{mid}')
    def motion(mid: int):
        return {**motion_evidence(store.motion(mid)),'jobs':store.jobs(mid)}

    @app.post('/api/investigation/motions/{mid}/analyze')
    def analyze_motion(mid: int):
        store.enqueue_analysis(mid,True)
        return {'jobs':store.jobs(mid)}

    @app.get('/api/investigation/motions/{mid}/thumbnail')
    def thumbnail(mid: int):
        import cv2
        from .analysis import evidence_lease, sampled_frames
        motion = store.motion(mid)
        with evidence_lease(runtime,motion['start'],motion['end']) as segments:
            frames = sampled_frames(store.root,segments,motion['start'],motion['end'],1)
            try:
                _,frame = next(frames)
                frame = cv2.resize(frame,(320,max(1,round(frame.shape[0]*320/frame.shape[1]))))
                ok,jpeg = cv2.imencode('.jpg',frame)
                if ok:
                    return Response(jpeg.tobytes(),media_type='image/jpeg')
            except StopIteration:
                pass
            finally:
                frames.close()
        raise HTTPException(410,'Evidence expired')

    @app.get('/api/investigation/observations')
    def observations(start: float, end: float, limit: int = 200, after: int = 0):
        items = store.observations(start,end,limit,after)
        return {'observations':items,'next_after':items[-1]['id'] if len(items)==limit else None}

    @app.get('/api/investigation/jobs')
    def jobs(limit: int = 50, before: int | None = None):
        return {'jobs':store.jobs(limit=limit,before=before)}

    @app.get('/api/investigation/report')
    def investigation_report(session_id: int | None = None):
        return store.investigation_report(session_id)

    def decorate(event):
        clips = store.evidence(event["start"], event["end"])
        core = [s for s in clips if s["start"] < event["end"] and s["end"] > event["start"]]
        complete = bool(core)
        cursor = event["start"]
        for clip in core:
            if clip["start"] > cursor + 1:
                complete = False
            cursor = max(cursor, clip["end"])
        complete = complete and cursor >= event["end"] - 1
        return {**event, "duration_seconds": round(event["end"]-event["start"],2), "clips": clips,
                "evidence": "available" if complete else "partial" if clips else "expired"}

    @app.get("/api/events")
    def events(limit: int = 100, before: int | None = None):
        if not 1 <= limit <= 200:
            raise ValueError("Limit must be 1 to 200")
        all_events = [e for e in store.events() if before is None or e["id"] < before]
        return {"events": [decorate(e) for e in all_events[:limit]],
                "next_before": all_events[limit-1]["id"] if len(all_events) > limit else None}

    @app.get("/api/events/{event_id}")
    def event(event_id: int):
        return decorate(store.event(event_id))

    @app.patch("/api/events/{event_id}")
    def correct(event_id: int, body: dict = Body(...)):
        return decorate(store.correct(event_id, body))

    @app.post("/api/events")
    def add(body: dict = Body(...)):
        if set(body) - {"area", "start", "end", "behavior", "rejected"} or not {"area", "start", "end"} <= set(body):
            raise ValueError("Supply area, start and end")
        return decorate(store.add_manual(body))

    @app.post("/api/events/{event_id}/split")
    def split(event_id: int, body: dict = Body(...)):
        stamp = body.get("at")
        if not isinstance(stamp, (float, int)):
            raise ValueError("Supply a split timestamp")
        return [decorate(e) for e in store.split(event_id, stamp)]

    @app.post("/api/merge")
    def merge(body: dict = Body(...)):
        ids = body.get("ids")
        if not isinstance(ids, list) or any(not isinstance(i, int) for i in ids):
            raise ValueError("Supply two event IDs")
        return decorate(store.merge(ids))

    @app.get("/api/evidence")
    def evidence(start: float, end: float):
        if start >= end or end-start > 86400:
            raise ValueError("Choose an interval of up to one day")
        return store.evidence(start, end, padding=0)

    @app.get("/api/clips/{segment_id}")
    def clip(segment_id: int):
        with store.lock:
            candidates = [s for s in store.segments() if s["id"] == segment_id]
            if not candidates:
                raise HTTPException(410, "Evidence expired")
            path = store.root / candidates[0]["path"]
            if not path.is_file():
                raise HTTPException(410, "Evidence expired")
            runtime.retention.leases[segment_id] = runtime.retention.leases.get(segment_id, 0) + 1

        def release():
            with store.lock:
                runtime.retention.leases[segment_id] -= 1
        return FileResponse(path, media_type="video/mp4", background=BackgroundTask(release))

    def rows(start, end, days):
        if not 1 <= days <= 366:
            raise ValueError("Days must be 1 to 366")
        if start is None and end is None:
            now = datetime.now(ZoneInfo("Asia/Jerusalem"))
            start = (now.replace(hour=0,minute=0,second=0,microsecond=0) - timedelta(days=days-1)).timestamp()
            end = now.timestamp()
        if start is None or end is None:
            raise ValueError("Supply both start and end")
        if start >= end or end-start > 366*86400:
            raise ValueError("Choose an interval of up to one year")
        return report(store.events(), store.coverage(), start, end)

    @app.get("/api/reports")
    def reports(start: float | None = None, end: float | None = None, days: int = 7):
        return {"timezone": "Asia/Jerusalem", "rows": rows(start,end,days)}

    @app.get("/api/reports.csv")
    def export(start: float | None = None, end: float | None = None, days: int = 7):
        data = rows(start,end,days)
        flat = [{k:v for k,v in row.items() if k != "behaviors"} | row["behaviors"] for row in data]
        stream = io.StringIO()
        if flat:
            writer = csv.DictWriter(stream, fieldnames=list(flat[0]))
            writer.writeheader()
            writer.writerows(flat)
        return Response(stream.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="cat-watch-report.csv"'})

    return app
