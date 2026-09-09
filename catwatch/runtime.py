"""One RTSP reader, bounded completed segments, and offline GPU detection."""
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import urllib.parse
import uuid

from .core import VisitTracker, assign_area
from .retention import MEDIA_NAME, Retention


class Runtime:
    def __init__(self, store, credential=None):
        self.store = store
        self.credential = credential
        self.retention = Retention(store)
        self.stop = threading.Event()
        self.thread = None
        self.process = None
        self.state = {"camera": "stopped", "detector": "loading", "calibrated": False, "last_frame": None,
                      "ambiguous_frames": 0, "message": "Starting", "gpu": None}
        self.frame = None
        self.detections = []
        self.last_sample = None
        self.tracker = VisitTracker(store)
        self.media = store.root / "media"
        self.media.mkdir(exist_ok=True)

    def start(self):
        self.store.recover()
        self.thread = threading.Thread(target=self.run, name="catwatch-monitor", daemon=True)
        self.thread.start()

    def shutdown(self):
        self.stop.set()
        self.stop_capture()
        if self.thread:
            self.thread.join(timeout=25)

    def stop_capture(self):
        process = self.process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)

    def load_model(self):
        os.environ["YOLO_CONFIG_DIR"] = "/tmp/catwatch-yolo"
        Path(os.environ["YOLO_CONFIG_DIR"]).mkdir(exist_ok=True)
        import torch
        from ultralytics import YOLO, settings
        settings.update({"sync": False})
        weights = Path("/opt/models/yolo11n.pt")
        if not weights.is_file():
            raise RuntimeError("Packaged model missing; rebuild the image")
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable; run the Windows foundation TestGpu check")
        self.model = YOLO(str(weights))
        import numpy as np
        self.model.predict(np.zeros((640, 640, 3), dtype=np.uint8), device=0, verbose=False)
        self.state.update(detector="ready", gpu=torch.cuda.get_device_name(0))

    def run(self):
        try:
            self.load_model()
        except Exception:
            self.state.update(detector="failed", message="GPU/model initialization failed; run Check and rebuild if needed")
            return
        if self.credential is None:
            self.state.update(camera="stopped", message="Camera credentials were not supplied")
            return
        # Recover only exact generated leftovers. Unregistered segments are incomplete evidence.
        known = {s["path"] for s in self.store.segments()}
        for path in self.media.iterdir():
            if MEDIA_NAME.fullmatch(path.name) and str(path.relative_to(self.store.root)) not in known and not path.is_symlink():
                path.unlink(missing_ok=True)
        while not self.stop.is_set():
            try:
                if not self.retention.maintain():
                    self.state.update(camera="paused", message="Storage reserve unavailable; recording paused")
                    self.stop.wait(5)
                    continue
                self.capture_session()
            except Exception:
                # Never log exception text: decoder errors may contain the authenticated URL.
                self.state.update(camera="disconnected", message="Capture or analysis failed; reconnecting in 5 seconds")
            finally:
                self.stop_capture()
                self.tracker.interrupt()
                self.last_sample = None
            self.stop.wait(5)
        self.state.update(camera="stopped", message="Monitoring stopped")

    def capture_session(self):
        c = self.credential
        host = c["ip"]
        import ipaddress
        ipaddress.IPv4Address(host)
        source = f"rtsp://{urllib.parse.quote(c['username'], safe='')}:{urllib.parse.quote(c['password'], safe='')}@{host}:554/stream1"
        session = uuid.uuid4().hex
        manifest = self.store.root / "segments.csv"
        manifest.write_text("")
        pattern = str(self.media / (session + "-%06d.mp4"))
        # Keep camera-relative PTS for segmentation. Feeding epoch PTS to the segment
        # muxer makes its initial segment start at zero and breaks segment durations.
        # Anchor the relative timeline to the first completed file's modification time.
        args = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-rtsp_transport", "tcp",
                "-timeout", "15000000", "-i", source,
                "-map", "0:v:0", "-an", "-c:v", "copy", "-f", "segment", "-segment_time", "5",
                "-segment_format", "mp4", "-segment_format_options", "movflags=+faststart",
                "-reset_timestamps", "1", "-segment_list", str(manifest), "-segment_list_type", "csv",
                "-segment_list_size", "20", pattern]
        self.process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.state.update(camera="connecting", message="Waiting for the first complete video segment")
        seen = set()
        epoch = None
        last_segment = time.monotonic()
        last_quota = 0
        try:
            while not self.stop.wait(.5):
                if self.process.poll() is not None:
                    raise RuntimeError("Recorder exited")
                now = time.monotonic()
                if now - last_quota >= 2:
                    last_quota = now
                    if not self.retention.maintain():
                        self.state.update(camera="paused", message="Storage limit reached; recording paused")
                        return
                    # Bound an abnormal keyframe interval / stalled active segment.
                    if any(p.stat().st_size > 32_000_000 for p in self.media.glob(session + "-*.mp4") if str(p) not in seen):
                        raise RuntimeError("Segment exceeded reserved size")
                rows = list(csv.reader(io.StringIO(manifest.read_text())))
                for row in rows:
                    if len(row) != 3:
                        continue
                    name, a, b = row
                    path = self.media / Path(name).name
                    if str(path) in seen or not path.is_file():
                        continue
                    relative_start, relative_end = float(a), float(b)
                    if epoch is None:
                        epoch = path.stat().st_mtime - relative_end
                    start, end = epoch + relative_start, epoch + relative_end
                    if not time.time() - 120 < start <= end <= time.time() + 10:
                        raise RuntimeError("Unexpected recorder timestamps")
                    seen.add(str(path))
                    self.store.add_segment(str(path.relative_to(self.store.root)), start, end, path.stat().st_size)
                    self.analyze(path, start, end)
                    last_segment = time.monotonic()
                if now - last_segment > 30:
                    raise RuntimeError("No new segment in 30 seconds")
        finally:
            self.stop_capture()
            # Do not expose possibly unfinished MP4 files as evidence after interruption.
            for path in self.media.glob(session + "-*.mp4"):
                if str(path) not in seen and not path.is_symlink():
                    path.unlink(missing_ok=True)

    def analyze(self, path, start, end):
        import cv2
        config = self.store.config()
        if getattr(self, "last_config", None) != config:
            self.tracker.interrupt()
            self.last_sample = None
            self.last_config = config
            self.tracker = VisitTracker(self.store, config["enter_seconds"], config["leave_seconds"])
        self.state["calibrated"] = bool(config["polygons"])
        video = cv2.VideoCapture(str(path))
        offset = 0.0
        try:
            while offset < end - start and not self.stop.is_set():
                video.set(cv2.CAP_PROP_POS_MSEC, offset * 1000)
                ok, frame = video.read()
                if not ok:
                    break
                stamp = start + offset
                results = self.model.predict(frame, classes=[15], conf=config["confidence"], device=0, imgsz=640, verbose=False)[0]
                height, width = frame.shape[:2]
                boxes = results.boxes.xyxy.cpu().tolist()
                self.detections = [{"box": [a/width,b/height,c/width,d/height],
                                    "area": assign_area(config["polygons"], ((a+c)/2/width,d/height))} for a,b,c,d in boxes]
                success, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if success:
                    self.frame = jpeg.tobytes()
                self.state.update(last_frame=stamp, camera="connected", message="Monitoring" if config["polygons"] else "Draw the three areas to start visit counting")
                if config["polygons"]:
                    if self.last_sample is not None and stamp - self.last_sample > 1.5:
                        self.tracker.interrupt()
                        self.last_sample = None
                    if len(boxes) > 1:
                        self.state["ambiguous_frames"] += 1
                        self.tracker.interrupt()
                        self.last_sample = None
                    else:
                        if self.last_sample is not None:
                            self.store.add_coverage(self.last_sample, stamp)
                        self.tracker.observe(stamp, self.detections[0]["area"] if boxes else None)
                        self.last_sample = stamp
                offset += 1 / config["sample_fps"]
        finally:
            video.release()
