"""Immutable full-resolution review clips with an explicit source frame map."""
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import cv2

from .contracts import canonical, fingerprint


class BudgetExceeded(RuntimeError):
    pass


class CaptureResumed(RuntimeError):
    pass


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


class Corpus:
    def __init__(self, root, dataset_id, cap=100_000_000_000, floor=5_000_000_000, ffmpeg='ffmpeg'):
        self.root = Path(root).resolve()
        self.dataset_id, self.cap, self.floor, self.ffmpeg = dataset_id, cap, floor, ffmpeg
        self.root.mkdir(parents=True, exist_ok=True)
        marker = self.root / '.cat-watch-dataset'
        if marker.exists():
            if marker.read_text().strip() != dataset_id:
                raise ValueError('Dataset directory belongs to another database')
        else:
            if any(self.root.iterdir()):
                raise ValueError('Refusing to adopt a nonempty dataset directory')
            marker.write_text(dataset_id)
        for name in ('sources', 'clips', 'exports', 'temporary'):
            (self.root/name).mkdir(exist_ok=True)

    def usage(self):
        return sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file() and not p.is_symlink())

    def budget(self, additional=0):
        if self.usage() + additional > self.cap or shutil.disk_usage(self.root).free - additional < self.floor:
            raise BudgetExceeded('Dataset quota or 5 GB disk reserve reached; existing clips are preserved')

    def path(self, relative):
        path = (self.root/relative).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('Invalid dataset path')
        return path

    def preserve_source(self, path, cancelled):
        digest = sha256(path)
        destination = self.root/'sources'/f'{digest}.mp4'
        if destination.exists():
            if sha256(destination) != digest:
                raise ValueError('Stored source hash mismatch')
            return digest
        self.budget(path.stat().st_size)
        with tempfile.TemporaryDirectory(dir=self.root/'temporary') as tmp:
            output = Path(tmp)/'source.mp4'
            with path.open('rb') as source, output.open('wb') as target:
                for block in iter(lambda: source.read(1024*1024), b''):
                    if cancelled():
                        raise CaptureResumed('Capture resumed; export remains queued')
                    self.budget(len(block))
                    target.write(block)
            if sha256(output) != digest:
                raise ValueError('Source changed while copying')
            output.replace(destination)
        return digest

    def export_group(self, store, group, cancelled, publish):
        """Caller holds source leases. Publish each clip independently for crash recovery."""
        segments = group['clips']
        if not segments:
            raise FileNotFoundError('Source footage is unavailable')
        session_id = group['motions'][0]['session_id']
        metadata = {'dataset_id': self.dataset_id, 'session_id': session_id,
                    'group_id': group['id'], 'taxonomy_version': 1, 'export_version': 1,
                    'timing_version': 'segment-start-plus-source-frame-index-v1',
                    'requested_start': group['start']-5, 'requested_end': group['end']+5,
                    'calibration': store.investigation(session_id)['config_snapshot'],
                    'timing_note': 'Capture times are estimates from segment anchors and average frame cadence.'}
        encoder = None
        emitted, previous_end = 0, None
        try:
            for segment in segments:
                path = (store.root/segment['path']).resolve()
                if not path.is_relative_to(store.root.resolve()/'media') or path.is_symlink():
                    raise ValueError('Invalid source media path')
                digest = self.preserve_source(path, cancelled)
                video = cv2.VideoCapture(str(path))
                try:
                    fps = float(video.get(cv2.CAP_PROP_FPS))
                    if not math.isfinite(fps) or not 1 <= fps <= 120:
                        raise ValueError('Invalid source frame rate')
                    index = 0
                    while True:
                        ok, frame = video.read()
                        if not ok:
                            break
                        stamp = segment['start'] + index/fps
                        source_index = index
                        index += 1
                        if stamp < segment['play_start']-1e-6:
                            continue
                        if stamp >= segment['play_end']-1e-6:
                            break
                        if cancelled():
                            raise CaptureResumed('Capture resumed; export remains queued')
                        if previous_end is not None and stamp < previous_end-0.5/fps:
                            continue
                        shape = [frame.shape[1], frame.shape[0]]
                        discontinuity = previous_end is not None and abs(stamp-previous_end) > 0.5/fps
                        if encoder and (discontinuity or encoder.fps != fps or encoder.dimensions != shape or encoder.count >= math.floor(120*fps)):
                            publish(encoder.finish())
                            encoder = None
                            emitted += 1
                        if encoder is None:
                            encoder = ClipEncoder(self, metadata, fps, shape, stamp)
                        encoder.write(frame, digest, source_index, stamp)
                        previous_end = stamp + 1/fps
                finally:
                    video.release()
            if encoder:
                publish(encoder.finish())
                encoder = None
                emitted += 1
            if not emitted:
                raise FileNotFoundError('No decodable source frames in this interval')
        finally:
            if encoder:
                encoder.abort()


class ClipEncoder:
    def __init__(self, corpus, metadata, fps, dimensions, start):
        self.corpus, self.metadata, self.fps, self.dimensions = corpus, metadata, fps, dimensions
        self.count, self.mapping = 0, []
        self.start = start
        self.tmp = tempfile.TemporaryDirectory(dir=corpus.root/'temporary')
        self.path = Path(self.tmp.name)/'video.mp4'
        self.log = (Path(self.tmp.name)/'encoder.log').open('w+b')
        width, height = dimensions
        if width % 2 or height % 2:
            self.log.close()
            self.tmp.cleanup()
            raise ValueError('Source dimensions must be even for H.264; do not silently resize evidence')
        self.process = subprocess.Popen([corpus.ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error',
            '-f', 'rawvideo', '-pixel_format', 'bgr24', '-video_size', f'{width}x{height}',
            '-framerate', str(fps), '-i', 'pipe:0', '-an', '-c:v', 'libx264', '-threads', '2',
            '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(self.path)],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self.log)

    def write(self, frame, digest, source_index, stamp):
        if self.count % 32 == 0:
            self.corpus.budget(16_000_000)
        self.process.stdin.write(frame.tobytes())
        if (self.mapping and self.mapping[-1]['source_hash'] == digest
                and self.mapping[-1]['source_start_frame'] + self.count-self.mapping[-1]['start_frame'] == source_index):
            self.mapping[-1]['end_frame'] = self.count+1
        else:
            self.mapping.append({'start_frame': self.count, 'end_frame': self.count+1,
                                 'source_hash': digest, 'source_start_frame': source_index, 'capture_start': stamp})
        self.count += 1

    def finish(self):
        self.process.stdin.close()
        if self.process.wait(timeout=120) != 0:
            raise ValueError('Review encoder failed')
        self.log.close()
        cap = cv2.VideoCapture(str(self.path))
        try:
            if int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) != self.count or abs(cap.get(cv2.CAP_PROP_FPS)-self.fps) > .01:
                raise ValueError('Encoded video frame metadata differs from its source map')
        finally:
            cap.release()
        key = fingerprint({'dataset': self.metadata['dataset_id'], 'group': self.metadata['group_id'],
                           'session': self.metadata['session_id'], 'mapping': self.mapping, 'version': 1})
        manifest = dict(self.metadata, task_key=key, fps=self.fps, dimensions=self.dimensions,
                        frame_count=self.count, mapping=self.mapping, video_hash=sha256(self.path),
                        video_path=f'clips/{key}/video.mp4', capture_start=self.start,
                        capture_end=self.mapping[-1]['capture_start']+(self.mapping[-1]['end_frame']-self.mapping[-1]['start_frame'])/self.fps)
        manifest['boundary_flags'] = {'start_truncated': self.start > self.metadata['requested_start']+1/self.fps,
                                      'end_truncated': manifest['capture_end'] < self.metadata['requested_end']-1/self.fps}
        (Path(self.tmp.name)/'manifest.json').write_text(canonical(manifest))
        (Path(self.tmp.name)/'encoder.log').unlink()
        self.corpus.budget()
        destination = self.corpus.root/'clips'/key
        if destination.exists():
            saved = json.loads((destination/'manifest.json').read_text())
            if sha256(destination/'video.mp4') != saved['video_hash']:
                raise ValueError('Existing review clip failed integrity verification')
            manifest = saved
        else:
            os.replace(self.tmp.name, destination)
        self.tmp.cleanup()
        return manifest

    def abort(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        if not self.process.stdin.closed:
            self.process.stdin.close()
        self.log.close()
        self.tmp.cleanup()
