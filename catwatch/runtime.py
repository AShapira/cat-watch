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
import queue

from .core import VisitTracker, assign_area
from .retention import MEDIA_NAME, Retention
from .motion import MotionDetector, MotionTracker


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
        self.segment_queue = queue.Queue(maxsize=24)
        self.frame_queue = queue.Queue(maxsize=16)
        self.workers = []
        self.gpu_lock = threading.Lock()
        self.state.update(motion_analysis='starting', video_description='not configured',
                          detector_comparison='idle', frames_analyzed=0, cat_frames=0,
                          dropped_detection_frames=0, capture_gaps=0, motion_frames=0,
                          source=None, motion_lag_seconds=None)

    def start(self):
        self.store.recover()
        from .analysis import AnalysisWorker
        for target, name in [(self.motion_worker,'motion'), (self.detector_worker,'detector'),
                             (AnalysisWorker(self,'detector_comparison').run,'comparison'),
                             (AnalysisWorker(self,'video_description').run,'description')]:
            worker = threading.Thread(target=target,name='catwatch-'+name,daemon=True)
            worker.start()
            self.workers.append(worker)
        self.thread = threading.Thread(target=self.run, name="catwatch-monitor", daemon=True)
        self.thread.start()

    def shutdown(self):
        self.stop.set()
        self.stop_capture()
        if self.thread:
            self.thread.join(timeout=25)
        for worker in self.workers:
            worker.join(timeout=5)

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
                self.state['capture_gaps'] += 1
                self.store.observation(time.time(),'capture_gap',{'reason':'recorder interrupted'})
            finally:
                self.stop_capture()
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
                    self.store.queue_completed_motions()
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
                    with self.store.lock:
                        self.store.add_segment(str(path.relative_to(self.store.root)), start, end, path.stat().st_size)
                        sid = self.store.segment_id(str(path.relative_to(self.store.root)))
                        self.retention.leases[sid] = self.retention.leases.get(sid,0)+1
                    try:
                        self.segment_queue.put_nowait((path,start,end,sid,session))
                    except queue.Full:
                        with self.store.lock:
                            self.retention.leases[sid] -= 1
                        self.state['capture_gaps'] += 1
                        self.store.observation(start,'motion_gap',{'reason':'motion queue full','end':end})
                        # Preserve unanalyzed footage as explicit interrupted evidence.
                        investigation = self.store.investigation()
                        if investigation and investigation['start'] <= start < investigation['end']:
                            mid = self.store.open_motion(investigation['id'],start,0)
                            self.store.update_motion(mid,end,0)
                            self.store.close_motion(mid,True)
                    last_segment = time.monotonic()
                    self.state.update(camera='connected',message='Capturing')
                if now - last_segment > 30:
                    raise RuntimeError("No new segment in 30 seconds")
        finally:
            self.stop_capture()
            # Do not expose possibly unfinished MP4 files as evidence after interruption.
            for path in self.media.glob(session + "-*.mp4"):
                if str(path) not in seen and not path.is_symlink():
                    path.unlink(missing_ok=True)

    def motion_worker(self):
        import cv2
        motion = tracker = None
        identity = None
        last_preview = 0
        while not self.stop.is_set():
            try:
                path,start,end,sid,capture_id = self.segment_queue.get(timeout=.5)
            except queue.Empty:
                if tracker and time.time() >= tracker.session['end']+10:
                    tracker.interrupt(False)
                continue
            video = cv2.VideoCapture(str(path))
            try:
                investigation = self.store.investigation()
                current_identity = (capture_id, investigation['id'] if investigation else None,
                                    json.dumps(investigation['settings'],sort_keys=True) if investigation else None)
                if current_identity != identity:
                    if tracker:
                        tracker.interrupt()
                    motion = MotionDetector(investigation['settings']) if investigation else None
                    tracker = MotionTracker(self.store,investigation) if investigation else None
                    identity = current_identity
                elif tracker:
                    tracker.session = investigation
                fps = video.get(cv2.CAP_PROP_FPS)
                if not 1 <= fps <= 120:
                    raise ValueError('Invalid source frame rate')
                self.state['source'] = {'width':int(video.get(cv2.CAP_PROP_FRAME_WIDTH)),
                                        'height':int(video.get(cv2.CAP_PROP_FRAME_HEIGHT)), 'fps':round(fps,2)}
                index = 0
                while not self.stop.is_set():
                    ok,frame = video.read()
                    if not ok:
                        break
                    # Source PTS occasionally arrive in bursts; frame-index time
                    # keeps the motion debounce at the source's average cadence.
                    stamp = min(end,start+index/fps)
                    index += 1
                    if tracker and start <= investigation['end']+20:
                        score = motion.observe(frame)
                        tracker.observe(stamp,score)
                        self.state['motion_score'] = score
                    self.state['motion_frames'] += 1
                    self.state.update(motion_analysis='ready',motion_lag_seconds=round(time.time()-stamp,1))
                    if stamp-last_preview >= .49:
                        success,jpeg = cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,80])
                        if success:
                            self.frame = jpeg.tobytes()
                        self.state['last_frame'] = stamp
                        last_preview = stamp
                        try:
                            self.frame_queue.put_nowait((stamp,frame.copy(),capture_id))
                        except queue.Full:
                            self.state['dropped_detection_frames'] += 1
                            self.store.observation(stamp,'detector_gap',{'reason':'frame queue full'})
                if index == 0:
                    raise ValueError('Empty video segment')
            except Exception:
                self.state['motion_analysis'] = 'failed segment; retrying next segment'
                self.store.observation(start,'motion_gap',{'reason':'decode or motion analysis failed','end':end})
                if tracker:
                    tracker.interrupt()
                investigation = self.store.investigation()
                if investigation and investigation['start'] <= start < investigation['end']:
                    mid = self.store.open_motion(investigation['id'],start,0)
                    self.store.update_motion(mid,end,0)
                    self.store.close_motion(mid,True)
            finally:
                video.release()
                with self.store.lock:
                    self.retention.leases[sid] -= 1
                self.segment_queue.task_done()
        if tracker:
            tracker.interrupt()

    def detector_worker(self):
        try:
            self.load_model()
        except Exception:
            self.state['detector'] = 'failed'
            return
        capture_identity = None
        while not self.stop.is_set():
            try:
                stamp,frame,capture_id = self.frame_queue.get(timeout=.5)
            except queue.Empty:
                continue
            try:
                if capture_identity != capture_id:
                    self.tracker.interrupt()
                    self.last_sample = None
                    capture_identity = capture_id
                self.detect(frame,stamp)
            except Exception:
                self.state['detector'] = 'failed frame; retrying'
                self.tracker.interrupt()
                self.last_sample = None
                self.store.observation(stamp,'detector_gap',{'reason':'inference failed'})
            finally:
                self.frame_queue.task_done()
        self.tracker.interrupt()

    def detect(self, frame, stamp):
        config = self.store.config()
        if getattr(self, "last_config", None) != config:
            self.tracker.interrupt()
            self.last_sample = None
            self.last_config = config
            self.tracker = VisitTracker(self.store, config["enter_seconds"], config["leave_seconds"])
        self.state["calibrated"] = bool(config["polygons"])
        with self.gpu_lock:
            results = self.model.predict(frame, conf=.1, device=0, imgsz=640, verbose=False)[0]
        height,width = frame.shape[:2]
        self.detections = []
        for box,confidence,cls in zip(results.boxes.xyxy.cpu().tolist(),results.boxes.conf.cpu().tolist(),results.boxes.cls.cpu().tolist()):
            a,b,c,d = box
            self.detections.append({'box':[a/width,b/height,c/width,d/height], 'confidence':confidence,
                                    'class_id':int(cls),'label':results.names[int(cls)],
                                    'area':assign_area(config['polygons'],((a+c)/2/width,d/height))})
        cats = [d for d in self.detections if d['class_id']==15 and d['confidence']>=config['confidence']]
        reason = 'no_cat_above_threshold' if not cats else 'multiple_cats' if len(cats)>1 else 'outside_or_overlapping_areas' if cats[0]['area'] is None else 'area_presence'
        if not config['polygons']:
            reason = 'areas_unconfigured'
        elif self.last_sample is not None and stamp-self.last_sample>1.5:
            self.tracker.interrupt()
            self.last_sample = None
            reason = 'sample_gap'
        if config['polygons']:
            if len(cats)>1:
                self.state['ambiguous_frames'] += 1
                self.tracker.interrupt()
                self.last_sample = None
            else:
                if self.last_sample is not None:
                    self.store.add_coverage(self.last_sample,stamp)
                self.tracker.observe(stamp,cats[0]['area'] if cats else None)
                self.last_sample = stamp
        self.state['frames_analyzed'] += 1
        self.state['cat_frames'] += bool(cats)
        self.state.update(detector='ready', detection_stamp=stamp, detector_lag_seconds=round(time.time()-stamp,1),message='Monitoring')
        investigation = self.store.investigation()
        if investigation and investigation['start'] <= stamp <= investigation['end']:
            self.store.observation(stamp,'detection',{'detections':self.detections,'reason':reason,
                'model':'yolo11n','imgsz':640,'threshold':config['confidence'],
                'entry_progress':{area:{'seconds':p.last-p.first,'event_id':p.event_id} for area,p in self.tracker.states.items()}},investigation['id'])
