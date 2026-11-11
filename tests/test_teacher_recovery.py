from types import SimpleNamespace
import sys
import subprocess
import time

import pytest

from catwatch.learning import cloud, training
from catwatch.learning.worker import Agent


@pytest.mark.parametrize('fails', [False, True])
def test_teacher_replaces_stale_status_after_recovery(tmp_path, monkeypatch, fails):
    runtime = SimpleNamespace(retention=SimpleNamespace(), state={})
    agent = Agent(SimpleNamespace(root=tmp_path), runtime)
    agent.local_ready = True
    agent.next_local_probe = time.time()+600
    agent.store.configure({'training': False})
    agent.store.set_meta('heavy_worker', {'state': 'waiting', 'message': 'Local Qwen is unavailable'})
    agent.store.enqueue('label', 'fixture', {'clip_id': 'fixture'})
    monkeypatch.setattr(training, 'gpu_free_mib', lambda: 10000)
    monkeypatch.setattr(cloud, 'dispatch_one', lambda store: None)

    def label(clip_id):
        agent.stop.set()
        if fails:
            raise ValueError('fixture invalid response')
        return {'status': 'suggestion'}

    monkeypatch.setattr(agent, 'label', label)
    agent.heavy()
    status = agent.store.meta('heavy_worker')
    assert status['state'] == ('waiting' if fails else 'running')
    assert 'unavailable' not in status['message']
    assert ('could not be completed' if fails else 'ready') in status['message']


def test_shared_gpu_capacity_uses_conservative_host_reading(monkeypatch):
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(cuda=SimpleNamespace(
        is_available=lambda: True, mem_get_info=lambda: (14599*1024**2, 16303*1024**2))))
    monkeypatch.setattr(training.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout='6539\n'))
    assert training.gpu_free_mib() == 6539
    monkeypatch.setattr(training.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout='N/A\n'))
    assert training.gpu_free_mib() == 0

    def unavailable(*args, **kwargs):
        raise subprocess.TimeoutExpired('nvidia-smi', 5)

    monkeypatch.setattr(training.subprocess, 'run', unavailable)
    assert training.gpu_free_mib() == 0
