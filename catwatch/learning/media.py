"""Owned evidence import, native-pixel sampling, and bounded clip extraction."""
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import cv2
import numpy as np

from .contracts import digest
from .crop_policy import CROP_POLICY, classification_regions


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            result.update(block)
    return result.hexdigest()


def info(path):
    video = cv2.VideoCapture(str(path))
    try:
        fps = video.get(cv2.CAP_PROP_FPS)
        count = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
        width, height = int(video.get(cv2.CAP_PROP_FRAME_WIDTH)), int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if not 1 <= fps <= 120 or count < 1 or min(width, height) < 1:
            raise ValueError('Video cannot be decoded with valid timing')
        return {'fps': fps, 'frame_count': count, 'width': width, 'height': height, 'duration': count/fps}
    finally:
        video.release()


def storage_check(learning, additional=0):
    folder = learning.root / 'evidence'
    used = sum(p.stat().st_size for p in folder.rglob('*') if p.is_file()) if folder.exists() else 0
    cap = int(learning.config()['dataset_cap_gb']*1e9)
    free = shutil.disk_usage(learning.root).free
    floor = max(256_000_000, int(os.environ.get('CATWATCH_DISK_FLOOR_BYTES', '256000000')))
    ok = used + additional <= cap and free >= additional + floor
    learning.set_meta('storage', {'used_bytes': used, 'cap_bytes': cap, 'free_bytes': free, 'additions_allowed': ok})
    if not ok:
        raise ValueError('Curated evidence storage is full; protected evidence has been preserved')


def own_video(learning, path):
    path = Path(path)
    checksum = file_hash(path)
    relative = f'evidence/{checksum}.mp4'
    target = learning.safe_path(relative)
    if not target.exists():
        storage_check(learning, path.stat().st_size)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix('.partial')
        try:
            shutil.copyfile(path, temporary)
            if file_hash(temporary) != checksum:
                raise ValueError('Source changed while copying')
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return relative, checksum


def add_video(learning, path, *, start, group_key, polygons, source_hashes=None, provenance=None):
    metadata = info(path)
    if metadata['duration'] > 60:
        raise ValueError('Split source videos into short clips before import')
    relative, checksum = own_video(learning, path)
    overrides = learning.meta('classification_crop_overrides', {})
    regions = classification_regions(polygons, metadata['width'], metadata['height'], .5, overrides)
    if not regions:
        # Local context review remains possible; full frames cannot be exported to cloud.
        regions = [{'areas': [], 'box': [0, 0, metadata['width'], metadata['height']]}]
    result = []
    for region in regions:
        ident = digest({'video': checksum, 'crop': region['box'],
                        'areas': region['areas'], 'version': 2})
        manifest = {'id': ident, 'video': relative, 'video_hash': checksum, 'start': start,
                    'duration': metadata['duration'], 'fps': metadata['fps'], 'frames': metadata['frame_count'],
                    'width': metadata['width'], 'height': metadata['height'], 'crop': region['box'],
                    'areas': region['areas'], 'group_key': group_key,
                    'crop_policy': CROP_POLICY,
                    'source_hashes': sorted(set(source_hashes or [checksum])), 'provenance': provenance or {},
                    'timing_note': 'Capture times are estimated; source frame cadence determines clip intervals.'}
        for area in region['areas']:
            if area in overrides and polygons[area] == overrides[area]['polygon']:
                manifest.setdefault('classification_crop_overrides', {})[area] = overrides[area]
        learning.add_clip(manifest)
        result.append(ident)
    return result


def import_prepared(learning, root):
    root = Path(root).resolve()
    if not (root / '.cat-watch-dataset').is_file():
        raise ValueError('Prepared dataset ownership marker is missing')
    count = 0
    for path in sorted((root / 'clips').glob('*/manifest.json')):
        key = 'import:' + str(path)
        if learning.meta(key):
            continue
        manifest = json.loads(path.read_text())
        video = (root / manifest['video_path']).resolve()
        if not video.is_relative_to(root) or not video.is_file():
            raise ValueError('Prepared clip is missing or outside the dataset')
        if file_hash(video) != manifest['video_hash']:
            raise ValueError('Prepared clip checksum differs from its manifest')
        ids = add_video(learning, video, start=manifest['capture_start'],
                        group_key=f"legacy:{manifest['dataset_id']}:{manifest['group_id']}",
                        polygons=manifest['calibration']['polygons'],
                        source_hashes=[m['source_hash'] for m in manifest.get('mapping', [])],
                        provenance={'kind': 'label-studio', 'original_manifest': manifest})
        learning.set_meta(key, ids)
        count += len(ids)
    return count


def sample(learning, clip, *, count=16, start=0, end=None):
    m = clip['manifest']
    end = clip['duration'] if end is None else min(end, clip['duration'])
    if not 1 <= count <= 64 or start < 0 or end <= start:
        raise ValueError('Invalid sampling window')
    video = cv2.VideoCapture(str(learning.safe_path(m['video'])))
    x1, y1, x2, y2 = m['crop']
    frames = []
    try:
        indexes = np.linspace(int(start*m['fps']), min(m['frames']-1, math.ceil(end*m['fps'])-1), count).astype(int)
        # Seek once, then decode forward. Repeated seeks re-decode the same GOP
        # for every sampled frame and can dominate background CPU time.
        first, last = int(indexes[0]), int(indexes[-1])
        if first:
            video.set(cv2.CAP_PROP_POS_FRAMES, first)
        wanted = {int(index): int(np.count_nonzero(indexes == index)) for index in indexes}
        for index in range(first, last+1):
            if not video.grab():
                raise ValueError('Missing source frame; sampling cannot fill recording gaps')
            if index not in wanted:
                continue
            ok, frame = video.retrieve()
            if not ok:
                raise ValueError('Missing source frame; sampling cannot fill recording gaps')
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                raise ValueError('Saved crop is outside the source frame')
            frames.extend((float(index/m['fps']), crop) for _ in range(wanted[index]))
    finally:
        video.release()
    return frames


def jpeg(frame):
    ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise ValueError('Image encoding failed')
    return encoded.tobytes()


def outbound_crop(manifest):
    """A named area must remain a crop, rather than the whole camera image."""
    x1, y1, x2, y2 = manifest['crop']
    return bool(manifest['areas']) and (x2-x1)*(y2-y1) < .8*manifest['width']*manifest['height']


def extract(learning, store, payload):
    """Extract only contiguous available sources; never concatenate across a gap."""
    a, b = payload['start'], payload['end']
    segments = [s for s in store.segments() if s['end'] > a and s['start'] < b]
    segments.sort(key=lambda s: s['start'])
    if not segments:
        raise ValueError('Source evidence has expired')
    covered = a
    sources = []
    for s in segments:
        if s['start'] > covered + .2:
            raise ValueError('Recording gap within requested clip')
        path = (store.root / s['path']).resolve()
        if not path.is_relative_to(store.root.resolve()) or not path.is_file():
            raise ValueError('Source evidence is missing')
        covered = max(covered, s['end'])
        sources.append(path)
    if covered < b-.2:
        raise ValueError('Waiting for clip post-roll')
    storage_check(learning, 64_000_000)
    with tempfile.TemporaryDirectory(prefix='catwatch-extract-') as folder:
        listing, output = Path(folder)/'sources.txt', Path(folder)/'clip.mp4'
        # Source paths are confined to application storage. Escape concat syntax.
        listing.write_text(''.join("file '"+str(p).replace("'", "'\\''")+"'\n" for p in sources))
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-threads', '2',
                        '-filter_threads', '1', '-f', 'concat', '-safe', '0', '-i', str(listing),
                        '-ss', str(max(0, a-segments[0]['start'])), '-t', str(b-a), '-an',
                        '-c:v', 'libx264', '-threads', '2', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p',
                        '-movflags', '+faststart', '-y', str(output)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        return add_video(learning, output, start=a, group_key=payload['group_key'],
                         polygons=payload.get('classification_original_polygons', payload['polygons']),
                         source_hashes=[file_hash(p) for p in sources],
                         provenance={'kind': payload.get('kind', 'motion'), 'session_id': payload['session_id'],
                                     'source_intervals': [[s['start'], s['end']] for s in segments]})
