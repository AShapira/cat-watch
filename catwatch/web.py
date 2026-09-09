import csv
import io
import secrets
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
        if name not in ("app.js", "style.css"):
            raise HTTPException(404)
        return FileResponse(Path(__file__).parent / "static" / name)

    @app.get("/api/session")
    def session():
        return {"token": token, "areas": AREAS, "behaviors": BEHAVIORS}

    @app.get("/api/health")
    def health():
        return {**runtime.state, "storage": runtime.retention.last, "now": time.time(),
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
        return {"detections": runtime.detections, "stamp": runtime.state["last_frame"]}

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
