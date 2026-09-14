import json
import math
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .core import AREAS, BEHAVIORS
from .investigation import InvestigationStore
from .analysis_control import AnalysisControlStore
from .investigation_review import InvestigationReviewStore

DEFAULTS = {"storage_cap_gb": 50, "enter_seconds": 2.0, "leave_seconds": 5.0,
            "sample_fps": 2, "confidence": 0.4, "timezone": "Asia/Jerusalem",
            "pre_seconds": 5, "post_seconds": 5, "polygons": {},
            "area_overlap": {area:.2 for area in AREAS}}


class Store(InvestigationStore, InvestigationReviewStore, AnalysisControlStore):
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.local = threading.local()
        self.path = self.root / "catwatch.sqlite3"
        with self.db() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 4, 5):
                raise ValueError('Unsupported database version; use its matching application')
            db.executescript('''
                PRAGMA journal_mode=DELETE;
                CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, original TEXT NOT NULL, effective TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS revisions (id INTEGER PRIMARY KEY, event_id INTEGER, stamp REAL, body TEXT);
                CREATE TABLE IF NOT EXISTS segments (id INTEGER PRIMARY KEY, path TEXT UNIQUE, start REAL, end REAL, size INTEGER, retained INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS coverage (id INTEGER PRIMARY KEY, start REAL, end REAL);
            ''')
            db.execute("INSERT OR IGNORE INTO settings VALUES (1,?)", (json.dumps(DEFAULTS),))
        self.init_investigation()
        self.init_motion_review()
        from .labeling.storage import migrate
        migrate(self)

    @contextmanager
    def db(self):
        with self.lock:
            if getattr(self.local, "connection", None) is not None:
                yield self.local.connection
                return
            conn = sqlite3.connect(self.path, timeout=20)
            conn.row_factory = sqlite3.Row
            self.local.connection = conn
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                self.local.connection = None
                conn.close()

    def config(self):
        with self.db() as db:
            saved = json.loads(db.execute("SELECT body FROM settings WHERE id=1").fetchone()[0])
        return saved

    def configure(self, updates):
        self.require_setup()
        config = self.config()
        if set(updates) - set(DEFAULTS):
            raise ValueError("Unknown configuration field")
        config.update(updates)
        thresholds = config['area_overlap']
        if (not isinstance(thresholds,dict) or set(thresholds)!=set(AREAS) or
                any(isinstance(v,bool) or not isinstance(v,(int,float)) or not .01<=v<=1
                    for v in thresholds.values())):
            raise ValueError('Supply an overlap threshold from 1% to 100% for each area')
        for key, low, high in (("storage_cap_gb", .05, 10000), ("enter_seconds", .5, 30),
                               ("leave_seconds", 1, 60), ("confidence", .1, .95)):
            if not isinstance(config[key], (float, int)) or not low <= config[key] <= high:
                raise ValueError(f"Invalid {key}")
        for key in ("sample_fps", "timezone", "pre_seconds", "post_seconds"):
            if config[key] != DEFAULTS[key]:
                raise ValueError(f"{key} is fixed in v1")
        polygons = config["polygons"]
        if not isinstance(polygons, dict) or set(polygons) not in (set(), set(AREAS)):
            raise ValueError("Draw all three areas before saving")
        for polygon in polygons.values():
            if not isinstance(polygon, list) or not 3 <= len(polygon) <= 20:
                raise ValueError("An area needs 3 to 20 points")
            for point in polygon:
                if not isinstance(point, list) or len(point) != 2 or any(isinstance(v,bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1 for v in point):
                    raise ValueError("Points must be normalized coordinates")
            area = abs(sum(polygon[i-1][0]*p[1]-p[0]*polygon[i-1][1] for i,p in enumerate(polygon))) / 2
            if area < .0001:
                raise ValueError("Area is too small")
        with self.db() as db:
            db.execute("UPDATE settings SET body=? WHERE id=1", (json.dumps(config),))
            if updates:
                db.execute("UPDATE preparation SET body=json_set(body,'$.confirmed',json('false')) WHERE id=1")
        return config

    def events(self):
        with self.db() as db:
            return [dict(json.loads(row["effective"]), id=row["id"]) for row in db.execute("SELECT * FROM events ORDER BY id DESC")]

    def event(self, event_id):
        with self.db() as db:
            row = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
            if row is None:
                raise KeyError(event_id)
            result = dict(json.loads(row["effective"]), id=row["id"], original=json.loads(row["original"]))
            result["history"] = [dict(r) for r in db.execute("SELECT stamp,body FROM revisions WHERE event_id=? ORDER BY id", (event_id,))]
        return result

    def open_visit(self, area, start, end):
        body = {"area": area, "start": start, "end": end, "open": True, "interrupted": False,
                "reviewed": False, "rejected": False, "behavior": "unknown", "source": "automatic"}
        with self.db() as db:
            return db.execute("INSERT INTO events(original,effective) VALUES (?,?)", (json.dumps(body), json.dumps(body))).lastrowid

    def touch_visit(self, event_id, stamp):
        self._automatic_update(event_id, {"end": stamp})

    def close_visit(self, event_id, stamp, interrupted):
        self._automatic_update(event_id, {"end": stamp, "open": False, "interrupted": interrupted})

    def _automatic_update(self, event_id, update):
        with self.db() as db:
            row = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
            original, effective = json.loads(row["original"]), json.loads(row["effective"])
            original.update(update)
            effective.update(update)
            db.execute("UPDATE events SET original=?,effective=? WHERE id=?", (json.dumps(original), json.dumps(effective), event_id))

    def recover(self):
        self.recover_investigation()
        for event in self.events():
            if event["open"]:
                self.close_visit(event["id"], event["end"], True)

    def correct(self, event_id, changes, action="review"):
        allowed = {"area", "start", "end", "behavior", "rejected"}
        if set(changes) - allowed:
            raise ValueError("Unsupported correction")
        with self.db() as db:
            row = db.execute("SELECT effective FROM events WHERE id=?", (event_id,)).fetchone()
            if row is None:
                raise KeyError(event_id)
            body = json.loads(row[0])
            if body["open"]:
                raise ValueError("Wait for the visit to finish before reviewing")
            before = body.copy()
            body.update(changes)
            self.validate_event(body)
            body["reviewed"] = True
            db.execute("UPDATE events SET effective=? WHERE id=?", (json.dumps(body), event_id))
            db.execute("INSERT INTO revisions(event_id,stamp,body) VALUES (?,?,?)", (event_id, time.time(), json.dumps({"action": action, "before": before, "after": body})))
        return self.event(event_id)

    @staticmethod
    def validate_event(body):
        import math
        if body["area"] not in AREAS or body["behavior"] not in BEHAVIORS or not isinstance(body["rejected"], bool):
            raise ValueError("Invalid event decision")
        if any(not isinstance(body[k], (float, int)) or not math.isfinite(body[k]) for k in ("start", "end")):
            raise ValueError("Invalid event time")
        if not 0 <= body["start"] < body["end"] <= time.time() + 60:
            raise ValueError("Start must precede end, without future times")

    def add_manual(self, changes, action="add"):
        body = {"area": "eating_pad", "behavior": "unknown", "rejected": False, **changes,
                "open": False, "interrupted": False, "reviewed": True, "source": "manual"}
        self.validate_event(body)
        if not self.evidence(body["start"], body["end"], padding=0):
            raise ValueError("No retained evidence overlaps these times")
        with self.db() as db:
            event_id = db.execute("INSERT INTO events(original,effective) VALUES (?,?)", (json.dumps(body), json.dumps(body))).lastrowid
            db.execute("INSERT INTO revisions(event_id,stamp,body) VALUES (?,?,?)", (event_id, time.time(), json.dumps({"action": action, "after": body})))
        return self.event(event_id)

    def add_segment(self, path, start, end, size):
        with self.db() as db:
            db.execute("INSERT OR IGNORE INTO segments(path,start,end,size) VALUES (?,?,?,?)", (path, start, end, size))

    def segment_id(self, path):
        with self.db() as db:
            return db.execute('SELECT id FROM segments WHERE path=?',(path,)).fetchone()[0]

    def split(self, event_id, stamp):
        with self.db():
            event = self.event(event_id)
            if event["open"] or event["rejected"] or not event["start"] < stamp < event["end"]:
                raise ValueError("Split must be inside a completed accepted visit")
            changes = {k: event[k] for k in ("area", "start", "end", "behavior", "rejected")}
            left = self.add_manual({**changes, "end": stamp}, action=f"split from {event_id}")
            right = self.add_manual({**changes, "start": stamp}, action=f"split from {event_id}")
            self.correct(event_id, {"rejected": True}, action=f"replaced by {left['id']}, {right['id']}")
            return [left, right]

    def merge(self, ids):
        if len(set(ids)) != 2:
            raise ValueError("Select two different visits")
        with self.db():
            events = [self.event(i) for i in ids]
            if any(e["open"] or e["rejected"] for e in events) or len({e["area"] for e in events}) != 1:
                raise ValueError("Merge requires completed accepted visits in the same area")
            if max(e["start"] for e in events) - min(e["end"] for e in events) > 60:
                raise ValueError("Visits more than 60 seconds apart cannot be merged")
            new = self.add_manual({"area": events[0]["area"], "start": min(e["start"] for e in events),
                                   "end": max(e["end"] for e in events), "behavior": "unknown"}, action=f"merged from {ids}")
            for event_id in ids:
                self.correct(event_id, {"rejected": True}, action=f"replaced by {new['id']}")
            return new

    def segments(self):
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM segments ORDER BY start")]

    def evidence(self, start, end, padding=5):
        return [dict(s,play_start=max(s["start"],start-padding),play_end=min(s["end"],end+padding))
                for s in self.segments() if s["start"] < end + padding and s["end"] > start - padding and (self.root / s["path"]).is_file()]

    def add_coverage(self, start, end):
        if end <= start:
            return
        with self.db() as db:
            last = db.execute("SELECT * FROM coverage ORDER BY id DESC LIMIT 1").fetchone()
            if last and start <= last["end"] + .1:
                db.execute("UPDATE coverage SET end=MAX(end,?) WHERE id=?", (end, last["id"]))
            else:
                db.execute("INSERT INTO coverage(start,end) VALUES (?,?)", (start, end))

    def coverage(self):
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT start,end FROM coverage ORDER BY start")]
