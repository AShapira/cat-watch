import json
from types import SimpleNamespace
import threading
import time

import pytest

from catwatch.performance import PerformancePolicy
from catwatch.learning.store import LearningStore
from catwatch.learning.worker import Agent


@pytest.mark.parametrize('state,age,quiet', [('on', 0, True), ('dimmed', 0, True),
    ('off', 0, False), ('off', 21, True), ('off', -10, True), ('unknown', 0, True)])
def test_only_fresh_screen_off_admits_heavy_work(tmp_path, state, age, quiet):
    p = tmp_path/'state.json'
    p.write_text(json.dumps({'schema': 1, 'display': state, 'updated_unix': time.time()-age}))
    assert PerformancePolicy(str(p)).quiet() is quiet


@pytest.mark.parametrize('body', [None, '{', 'null', '[]', '{}',
    '{"schema":1,"display":"off","updated_unix":"NaN"}'])
def test_signal_failures_are_quiet(tmp_path, body):
    p = tmp_path/'state.json'
    if body is not None:
        p.write_text(body)
    assert PerformancePolicy(str(p)).quiet()


def test_pause_is_enforced_even_if_database_previously_enabled_training(tmp_path, monkeypatch):
    store = LearningStore(tmp_path)
    monkeypatch.setenv('CATWATCH_TRAINING_PAUSED', '1')
    assert not store.config()['training']
    with pytest.raises(ValueError, match='paused'):
        store.configure({'training': True})


def test_quiet_worker_leaves_jobs_unclaimed_and_training_paused(tmp_path, monkeypatch):
    monkeypatch.setenv('CATWATCH_DISPLAY_STATE', str(tmp_path/'missing'))
    runtime = SimpleNamespace(retention=SimpleNamespace(), state={})
    agent = Agent(SimpleNamespace(root=tmp_path), runtime)
    agent.store.enqueue('label', 'test', {'clip_id': 'fixture'})
    class OneCycle:
        stopped = False
        def is_set(self): return self.stopped
        def wait(self, seconds): self.stopped = True
    agent.stop = OneCycle()
    agent.heavy()
    assert agent.store.jobs()[0]['state'] == 'queued'
    assert agent.store.jobs()[0]['attempts'] == 0
    assert agent.store.meta('pause_training') is True
    assert agent.store.meta('heavy_worker')['state'] == 'quiet'


def test_mode_changes_do_not_exhaust_job_retries(tmp_path):
    store = LearningStore(tmp_path)
    store.enqueue('label', 'test', {})
    for _ in range(5):
        job = store.claim('label', now=time.time()+100)
        store.defer(job['id'])
    assert store.jobs()[0]['attempts'] == 0
    assert store.jobs()[0]['state'] == 'queued'


def test_screen_on_cancels_admitted_upstream_request(monkeypatch):
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1]/'scripts/shared-llm/gateway.py'
    spec = importlib.util.spec_from_file_location('quiet_gateway', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'DISPLAY', SimpleNamespace(quiet=lambda: True))
    calls = []
    connection = SimpleNamespace(sock=SimpleNamespace(shutdown=lambda how: calls.append('shutdown')),
                                 close=lambda: calls.append('close'))
    cancelled = threading.Event()
    module.cancel_on_display(connection, threading.Event(), cancelled)
    assert cancelled.is_set() and calls == ['shutdown', 'close']


def test_gateway_rejects_managed_request_when_screen_on_without_backend(monkeypatch):
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1]/'scripts/shared-llm/gateway.py'
    spec = importlib.util.spec_from_file_location('quiet_gate_reject', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'DISPLAY', SimpleNamespace(quiet=lambda: True))
    handler = object.__new__(module.Handler)
    replies = []
    handler.reply = lambda status, body: replies.append((status, body))
    handler.forward('/api/chat', {}, display_managed=True)
    assert replies[0][0] == 409


def test_forward_sampling_preserves_indexes_crops_and_duplicate_samples(tmp_path):
    import cv2
    import numpy as np
    from catwatch.learning.media import sample
    path = tmp_path/'fixture.avi'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (64, 64))
    for index in range(30):
        writer.write(np.full((64, 64, 3), index*7, dtype=np.uint8))
    writer.release()
    store = SimpleNamespace(safe_path=lambda relative: tmp_path/relative)
    clip = {'duration': 3, 'manifest': {'video': path.name, 'fps': 10, 'frames': 30, 'crop': [4, 6, 40, 42]}}
    for start, end, count in [(0, 3, 16), (1, 2, 16), (2.8, 3, 16)]:
        expected = []
        capture = cv2.VideoCapture(str(path))
        for index in np.linspace(int(start*10), min(29, int(np.ceil(end*10))-1), count).astype(int):
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            assert ok
            expected.append((index/10, frame[6:42, 4:40]))
        capture.release()
        actual = sample(store, clip, start=start, end=end, count=count)
        assert len(actual) == count
        for (stamp, frame), (reference_stamp, reference) in zip(actual, expected):
            assert stamp == reference_stamp and np.array_equal(frame, reference)


def test_direct_training_entrypoint_stops_before_loading_models(tmp_path, monkeypatch):
    from catwatch.learning.training import train
    monkeypatch.setenv('CATWATCH_TRAINING_PAUSED', '1')
    result = train(tmp_path/'absent', 'no-dataset')
    assert result['paused'] and 'deployment policy' in result['reason']
    assert not (tmp_path/'absent').exists()


def test_detector_spaces_a_source_burst_instead_of_discarding_it(tmp_path):
    from catwatch.runtime import Runtime
    from catwatch.store import Store
    runtime = Runtime(Store(tmp_path))
    runtime.performance = SimpleNamespace(status=lambda: {'detector_fps': 2})
    runtime.model = object()
    calls = []
    def detect(frame, stamp):
        calls.append((stamp, time.monotonic()))
        if len(calls) == 3:
            runtime.stop.set()
    runtime.detect = detect
    for i in range(3):
        runtime.queue_detection_frame((100+i*.5, object(), 'fixture'))
    thread = threading.Thread(target=runtime.detector_worker)
    thread.start()
    thread.join(timeout=3)
    runtime.stop.set()
    thread.join(timeout=1)
    assert len(calls) == 3
    assert calls[-1][1]-calls[0][1] >= .9
    assert [stamp for stamp, _ in calls] == [100, 100.5, 101]
    assert runtime.state['dropped_detection_frames'] == 0


def test_restart_preserves_unregistered_recording_tail(tmp_path):
    from catwatch.runtime import Runtime
    from catwatch.store import Store
    store = Store(tmp_path)
    store.investigation = lambda: {'active': True}
    runtime = Runtime(store, {'ip': 'fixture'})
    original = runtime.media/('a'*32+'-000001.mp4')
    original.write_bytes(b'unregistered recording tail')
    runtime.stop.set()
    runtime.run()
    assert not original.exists()
    assert (tmp_path/'recovery-media'/original.name).read_bytes() == b'unregistered recording tail'
