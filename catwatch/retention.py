"""Quota enforcement is confined to generated media in the owned data directory."""
import re
import shutil
import time

MEDIA_NAME = re.compile(r"^[a-f0-9]{32}-[0-9]{6}\.mp4$")


class Retention:
    def __init__(self, store, reserve_bytes=64_000_000, disk_floor=256_000_000):
        self.store = store
        self.reserve = reserve_bytes
        self.disk_floor = disk_floor
        self.leases = {}
        self.last = {}

    def usage(self):
        return sum(p.stat().st_size for p in self.store.root.rglob("*") if p.is_file() and not p.is_symlink())

    def delete(self, segment):
        path = self.store.root / segment["path"]
        if path.parent != self.store.root / "media" or not MEDIA_NAME.fullmatch(path.name) or path.is_symlink():
            raise ValueError("Refusing to remove an unowned media path")
        if self.leases.get(segment["id"], 0):
            return False
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return False
        with self.store.db() as db:
            db.execute("DELETE FROM segments WHERE id=?", (segment["id"],))
        return True

    def maintain(self, now=None):
        now = time.time() if now is None else now
        with self.store.lock:
            config = self.store.config()
            cap = int(config["storage_cap_gb"] * 1_000_000_000)
            segments = self.store.segments()
            events = [e for e in self.store.events() if not e["rejected"]]
            # Keep enough rolling history for entry debounce, exit debounce and padding.
            cutoff = now - max(30, config["enter_seconds"] + config["leave_seconds"] + 20)
            protected = set()
            for segment in segments:
                matches = not segment["retained"] and any(e["start"] - 10 <= segment["end"] and e["end"] + 10 >= segment["start"] for e in events)
                if matches:
                    with self.store.db() as db:
                        db.execute("UPDATE segments SET retained=1 WHERE id=?", (segment["id"],))
                    segment["retained"] = 1
                # Recent segments are protected; older parts of a long open visit can expire.
                if segment["end"] >= cutoff:
                    protected.add(segment["id"])
                if not segment["retained"] and segment["id"] not in protected:
                    self.delete(segment)
            used = self.usage()
            free = shutil.disk_usage(self.store.root).free
            for segment in self.store.segments():
                if used + self.reserve <= cap and free >= self.disk_floor + self.reserve:
                    break
                if segment["id"] not in protected and self.delete(segment):
                    used = self.usage()
                    free = shutil.disk_usage(self.store.root).free
            ok = used + self.reserve <= cap and free >= self.disk_floor + self.reserve
            self.last = {"used_bytes": used, "cap_bytes": cap, "reserve_bytes": self.reserve,
                         "free_bytes": free, "recording_allowed": ok}
            return ok
