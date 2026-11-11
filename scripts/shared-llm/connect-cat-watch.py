"""Connect the running labeler through its supported API; never restart capture."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import urllib.request

BASE = 'http://127.0.0.1:8765'
MODEL_API = 'http://127.0.0.1:11434'
LOCK = json.loads(Path(__file__).with_name('model-lock.json').read_text())


def request(url, body=None, token=None, method=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['x-catwatch-token'] = token
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                 headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def connect(path):
    ready = request(MODEL_API+'/health')
    if not ready['ready'] or ready['model'] != LOCK['model']:
        raise SystemExit('Shared GPU model is not ready')
    before = request(BASE+'/api/health')
    state = request(BASE+'/api/learning/status')
    if not state['config']['continuous'] or before['camera'] != 'connected':
        raise SystemExit('Restore the authorized recording session before connecting labeling')
    initial = state['counts'].get('suggestions', 0)
    token = request(BASE+'/api/session')['token']
    request(BASE+'/api/learning/settings', {'ollama_url': MODEL_API}, token, 'PUT')
    del token
    print(json.dumps({'connected': MODEL_API, 'initial_suggestions': initial,
                      'initial_detection_frames': before['frames_analyzed']}), flush=True)
    deadline = time.monotonic()+360
    while time.monotonic() < deadline:
        time.sleep(10)
        state = request(BASE+'/api/learning/status')
        health = request(BASE+'/api/health')
        print(json.dumps({'suggestions': state['counts'].get('suggestions', 0),
                          'camera': health['camera'], 'frames': health['frames_analyzed']}), flush=True)
        if state['counts'].get('suggestions', 0) > initial:
            record = {'checked_at': datetime.now(timezone.utc).isoformat(), 'model': LOCK['model'],
                      'digest': LOCK['model_digest'], 'ollama_url': state['config']['ollama_url'],
                      'gpu_residency': request(MODEL_API+'/health'),
                      'continuous': state['config']['continuous'], 'counts': state['counts'],
                      'before': {k: before.get(k) for k in ['camera', 'detector', 'frames_analyzed', 'capture_gaps']},
                      'after': {k: health.get(k) for k in ['camera', 'detector', 'frames_analyzed', 'capture_gaps', 'frame_age_seconds', 'detector_lag_seconds']}}
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record, indent=2)+'\n')
            if health['frames_analyzed'] <= before['frames_analyzed'] or health['camera'] != 'connected':
                raise SystemExit('Label produced, but sustained recording is not established')
            print('Automatic labeling and advancing recording verified.', flush=True)
            return
    raise SystemExit('Connected, but no new suggestion was verified before the deadline; inspect the worker')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, required=True)
    connect(parser.parse_args().evidence)
