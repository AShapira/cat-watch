"""Quota enforcement is confined to generated media in the owned data directory."""
import os
import re
import shutil
import time

MEDIA_NAME = re.compile(r"^[a-f0-9]{32}-[0-9]{6}\.mp4$")


class Retention:
    def __init__(self, store, reserve_bytes=64_000_000, disk_floor=256_000_000):
        self.store = store
        self.reserve = reserve_bytes
        self.disk_floor = max(disk_floor, int(os.environ.get('CATWATCH_DISK_FLOOR_BYTES', str(disk_floor))))
        self.leases = {}
        self.last = {}
        self.deleted_bytes = 0

    def usage(self):
        # Reuse directory-entry metadata on the Windows mount and do not descend
        # into the independently budgeted learning tree or follow symlinks.
        total, pending = 0, [self.store.root]
        while pending:
            folder = pending.pop()
            with os.scandir(folder) as entries:
                for entry in entries:
                    if folder == self.store.root and entry.name == 'learning':
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except FileNotFoundError:
                        # A completed temporary file can disappear during a scan.
                        continue
        return total

    def delete(self, segment):
        self.deleted_bytes = 0
        path = self.store.root / segment["path"]
        if path.parent != self.store.root / "media" or not MEDIA_NAME.fullmatch(path.name) or path.is_symlink():
            raise ValueError("Refusing to remove an unowned media path")
        with self.store.db() as db:
            pinned = db.execute('SELECT 1 FROM protected_segments WHERE segment_id=?',(segment['id'],)).fetchone()
        if pinned or self.leases.get(segment["id"], 0):
            return False
        try:
            try:
                removed_size = path.stat().st_size
            except FileNotFoundError:
                removed_size = 0
            path.unlink(missing_ok=True)
        except OSError:
            return False
        with self.store.db() as db:
            db.execute("DELETE FROM segments WHERE id=?", (segment["id"],))
        self.deleted_bytes = removed_size
        return True

    def maintain(self, now=None):
        now = time.time() if now is None else now
        # File enumeration can take seconds over the Windows mount. Readers and
        # detector persistence must remain available while it runs. The recording
        # reserve covers the bounded active segment during this point-in-time scan.
        used = self.usage()
        continuous = bool(getattr(self, 'learning', None) and self.learning.config()['continuous'])
        with self.store.lock:
            config = self.store.config()
            cap = int(config["storage_cap_gb"] * 1_000_000_000)
            segments = self.store.segments()
            events = [e for e in self.store.events() if not e["rejected"]] + self.store.investigation_intervals()
            # Keep enough rolling history for entry debounce, exit debounce and padding.
            investigation = self.store.investigation()
            investigating = investigation and now < investigation['end']+120
            cutoff = now - max(120 if investigating else 30, config["enter_seconds"] + config["leave_seconds"] + 10)
            with self.store.db() as db:
                protected = {r[0] for r in db.execute('SELECT segment_id FROM protected_segments')}
                deferred_intervals = [dict(r) for r in db.execute("SELECT m.start,m.end FROM motions m JOIN investigations i ON m.session_id=i.id WHERE json_extract(i.settings,'$.analysis_mode')='deferred'")]
            for segment in segments:
                if segment['id'] not in protected and any(e['start']-5<=segment['end'] and e['end']+5>=segment['start'] for e in deferred_intervals):
                    with self.store.db() as db:
                        db.execute("INSERT OR IGNORE INTO protected_segments VALUES (?,'deferred investigation evidence')",(segment['id'],))
                    protected.add(segment['id'])
                matches = not segment["retained"] and any(e["start"] - 5 <= segment["end"] and e["end"] + 5 >= segment["start"] for e in events)
                if matches:
                    with self.store.db() as db:
                        db.execute("UPDATE segments SET retained=1 WHERE id=?", (segment["id"],))
                    segment["retained"] = 1
                # Recent segments are protected; older parts of a long open visit can expire.
                if segment["end"] >= cutoff:
                    protected.add(segment["id"])
                if not segment["retained"] and segment["id"] not in protected and (not continuous or segment['end'] < now-86400):
                    if self.delete(segment):
                        used = max(0, used-self.deleted_bytes)
            free = shutil.disk_usage(self.store.root).free
            for segment in self.store.segments():
                if used + self.reserve <= cap and free >= self.disk_floor + self.reserve:
                    break
                if segment["id"] not in protected and self.delete(segment):
                    used = max(0, used-self.deleted_bytes)
                    free = shutil.disk_usage(self.store.root).free
            ok = used + self.reserve <= cap and free >= self.disk_floor + self.reserve
            self.last = {"used_bytes": used, "cap_bytes": cap, "reserve_bytes": self.reserve,
                         "free_bytes": free, "recording_allowed": ok, "protected_segments":len(protected)}
            return ok
