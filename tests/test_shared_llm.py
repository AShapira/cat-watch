import importlib.util
from pathlib import Path
import threading
import time

import pytest

spec = importlib.util.spec_from_file_location('shared_gateway', Path(__file__).parents[1]/'scripts/shared-llm/gateway.py')
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)


def test_shared_clients_cannot_unload_swap_model_or_reallocate_context():
    body = gateway.prepare('/api/chat', {'model': gateway.MODEL, 'keep_alive': 0, 'messages': []})
    assert body['keep_alive'] == -1
    assert body['options']['num_ctx'] == 16384
    assert body['options']['num_gpu'] == 999
    for value in [{'model': 'other:9b'}, {'options': {'num_ctx': 262144}},
                  {'options': {'num_gpu': 0}}, {'options': {'num_predict': -1}}]:
        with pytest.raises(ValueError):
            gateway.prepare('/api/chat', value)
    with pytest.raises(ValueError):
        gateway.prepare('/api/pull', {'model': gateway.MODEL})


def test_cpu_offload_or_wrong_identity_is_not_healthy():
    model = {'name': gateway.MODEL, 'digest': gateway.LOCK['model_digest'],
             'size': 10000, 'size_vram': 10000, 'context_length': 16384}
    assert gateway.resident([model])
    assert not gateway.resident([{**model, 'size_vram': 9000}])
    assert not gateway.resident([{**model, 'digest': 'changed'}])
    assert not gateway.resident([{**model, 'context_length': 4096}])


def test_catwatch_schema_constrains_explanations_without_changing_generic_agents():
    from catwatch.learning.contracts import PROMPT, ALL_LABELS
    body = {'format': 'json', 'messages': [{'role': 'system', 'content': PROMPT}]}
    fixed = gateway.prepare('/api/chat', body)
    interval = fixed['format']['properties']['intervals']['items']
    assert interval['properties']['uncertainty']['type'] == 'string'
    assert interval['properties']['evidence']['maxLength'] == 1500
    assert set(interval['properties']['label']['enum']) == set(ALL_LABELS)
    assert gateway.background(body, {})
    other = gateway.prepare('/api/chat', {'format': 'json', 'messages': [{'role': 'user', 'content': 'Hello'}]})
    assert other['format'] == 'json'


def test_interactive_queue_priority_and_timeout_release():
    admission = gateway.Admission()
    order, threads = [], []
    def request(name, priority):
        with admission.slot(priority, timeout=2):
            order.append(name)
    with admission.slot():
        for name, priority in [('background', 1), ('interactive', 0)]:
            thread = threading.Thread(target=request, args=(name, priority))
            thread.start()
            threads.append(thread)
            deadline = time.monotonic()+1
            while len(admission.queue) < len(threads) and time.monotonic() < deadline:
                time.sleep(.001)
        with pytest.raises(TimeoutError):
            with admission.slot(timeout=.01):
                pass
    for thread in threads:
        thread.join(timeout=3)
        assert not thread.is_alive()
    assert order == ['interactive', 'background']
    assert admission.queue == [] and not admission.active
