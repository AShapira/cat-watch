"""Loopback-only shared Ollama API; fixed model, bounded work, GPU residency."""
from contextlib import contextmanager
import heapq
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import itertools
import json
import os
from pathlib import Path
import runpy
import socket
import threading
import time
from urllib.parse import urlsplit

LOCK = json.loads(Path(__file__).with_name('model-lock.json').read_text())
CAT_SCHEMA = json.loads(Path(__file__).with_name('catwatch-response.schema.json').read_text())
MODEL = LOCK['model']
GET_PATHS = {'/api/tags', '/api/ps', '/api/version', '/v1/models'}
INFERENCE_PATHS = {'/api/chat', '/api/generate', '/v1/chat/completions', '/v1/completions'}
MAX_BODY = 32*1024**2
STATE = {'ready': False, 'message': 'Waiting for the pinned GPU model'}
STATE_LOCK = threading.Lock()
STOP = threading.Event()


def display_policy():
    if not os.environ.get('CATWATCH_DISPLAY_STATE'):
        return None
    module = Path(__file__).with_name('performance.py')
    if not module.exists():
        module = Path(__file__).resolve().parents[2] / 'catwatch/performance.py'
    return runpy.run_path(str(module))['PerformancePolicy']()


DISPLAY = display_policy()


def cancel_on_display(conn, done, cancelled):
    """Cancel only this cat-watch request, including during image prefill."""
    upstream_socket = conn.sock
    while not done.wait(.25):
        if DISPLAY.quiet():
            cancelled.set()
            try:
                if upstream_socket:
                    upstream_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            conn.close()
            return


class Admission:
    def __init__(self, limit=16):
        self.limit, self.active = limit, False
        self.queue, self.sequence = [], itertools.count()
        self.condition = threading.Condition()

    @contextmanager
    def slot(self, priority=0, timeout=120):
        ticket = (priority, next(self.sequence))
        end = time.monotonic()+timeout
        with self.condition:
            if len(self.queue)+int(self.active) >= self.limit:
                raise TimeoutError('Local inference queue is full')
            heapq.heappush(self.queue, ticket)
            try:
                while self.active or self.queue[0] != ticket:
                    left = end-time.monotonic()
                    if left <= 0:
                        raise TimeoutError('Local inference queue wait expired')
                    self.condition.wait(left)
                heapq.heappop(self.queue)
                self.active = True
            except BaseException:
                if ticket in self.queue:
                    self.queue.remove(ticket)
                    heapq.heapify(self.queue)
                self.condition.notify_all()
                raise
        try:
            yield
        finally:
            with self.condition:
                self.active = False
                self.condition.notify_all()


ADMISSION = Admission()


def backend(path, body=None, timeout=10):
    conn = http.client.HTTPConnection('127.0.0.1', LOCK['backend_port'], timeout=timeout)
    try:
        payload = json.dumps(body).encode() if body is not None else None
        conn.request('POST' if body is not None else 'GET', path, payload, {'Content-Type': 'application/json'})
        response = conn.getresponse()
        value = json.loads(response.read())
        if response.status != 200:
            raise RuntimeError('Local runtime request failed')
        return value
    finally:
        conn.close()


def resident(models):
    model = next((m for m in models if m['name'] == MODEL), None)
    return bool(model and model.get('digest', '').removeprefix('sha256:') == LOCK['model_digest']
                and model.get('size', 0) > 0 and model.get('size_vram', 0) >= model['size']
                and model.get('context_length') == LOCK['context'])


def supervisor():
    while not STOP.is_set():
        try:
            tags = backend('/api/tags')['models']
            model = next((m for m in tags if m['name'] == MODEL), None)
            if not model or model.get('digest', '').removeprefix('sha256:') != LOCK['model_digest']:
                raise RuntimeError('Pinned model identity is unavailable')
            if model.get('details', {}).get('quantization_level') != LOCK['quantization']:
                raise RuntimeError('Unexpected quantization')
            models = backend('/api/ps')['models']
            if not resident(models):
                with STATE_LOCK:
                    STATE.update(ready=False, message='Loading the pinned model on GPU')
                with ADMISSION.slot(priority=-1):
                    backend('/api/generate', {'model': MODEL, 'keep_alive': -1, 'stream': False,
                        'options': {'num_ctx': LOCK['context'], 'num_gpu': 999}}, timeout=180)
                models = backend('/api/ps')['models']
            ready = resident(models)
            with STATE_LOCK:
                STATE.update(ready=ready, checked_at=time.time(), model=MODEL, models=models,
                             message='GPU model resident' if ready else 'Full GPU residency is not established')
        except Exception as error:
            with STATE_LOCK:
                STATE.update(ready=False, checked_at=time.time(), message=type(error).__name__+': runtime not ready')
        STOP.wait(15)


def prepare(path, value):
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object')
    if value.get('model', MODEL) != MODEL:
        raise ValueError('This shared service serves only '+MODEL)
    value = dict(value, model=MODEL)
    if path == '/api/show':
        return {'model': MODEL}
    if path not in INFERENCE_PATHS:
        raise ValueError('Endpoint is not available on this shared inference service')
    if path.startswith('/api/'):
        options = dict(value.get('options') or {})
        context = options.get('num_ctx', LOCK['context'])
        if context != LOCK['context']:
            raise ValueError('Use the shared 16384-token context; per-client context changes are disabled')
        output = options.get('num_predict', 2048)
        if type(output) is not int or not 1 <= output <= LOCK['max_output']:
            raise ValueError('Output token limit must be 1 through '+str(LOCK['max_output']))
        if options.get('num_gpu', 999) != 999:
            raise ValueError('GPU placement is managed by the shared service')
        for key in ('num_batch', 'main_gpu', 'use_mmap', 'num_thread', 'num_keep'):
            if key in options:
                raise ValueError('Runtime allocation options are managed by the shared service')
        options.update(num_ctx=LOCK['context'], num_predict=output, num_gpu=999)
        value.update(options=options, keep_alive=-1)
        value.setdefault('think', False)
        if path == '/api/chat' and catwatch_request(value) and value.get('format') == 'json':
            value['format'] = CAT_SCHEMA
    else:
        for key in ('max_tokens', 'max_completion_tokens'):
            output = value.get(key, 2048)
            if type(output) is not int or not 1 <= output <= LOCK['max_output']:
                raise ValueError('Invalid output token limit')
        if 'max_tokens' not in value and 'max_completion_tokens' not in value:
            value['max_tokens'] = 2048
        value['keep_alive'] = -1
        value.setdefault('reasoning_effort', 'none')
    return value


def catwatch_request(value):
    # Existing cat-watch client can join without restarting its recorder process.
    messages = value.get('messages', [])
    content = messages[0].get('content', '') if messages and isinstance(messages[0], dict) else ''
    return isinstance(content, str) and content.startswith('Classify only visible actions in these timestamped cat-camera crops.')


def background(value, headers):
    return headers.get('X-Local-Agent-Priority') == 'background' or catwatch_request(value)


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass  # Never persist prompts, images, authorization headers or answers.

    def reply(self, status, value):
        raw = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(raw)
        self.close_connection = True

    def forward(self, path, body=None, display_managed=False):
        conn = http.client.HTTPConnection('127.0.0.1', LOCK['backend_port'], timeout=180)
        started = False
        done, cancelled = threading.Event(), threading.Event()
        try:
            if display_managed:
                if DISPLAY.quiet():
                    self.reply(409, {'error': 'Cat-watch quiet mode; background request deferred'})
                    return
                conn.connect()
                threading.Thread(target=cancel_on_display, args=(conn, done, cancelled), daemon=True).start()
            raw = None if body is None else json.dumps(body).encode()
            conn.request('GET' if body is None else 'POST', path, raw, {'Content-Type': 'application/json'})
            response = conn.getresponse()
            self.send_response(response.status)
            self.send_header('Content-Type', response.getheader('Content-Type', 'application/json'))
            self.send_header('Connection', 'close')
            self.end_headers()
            started = True
            while chunk := response.read1(65536):
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # Closing upstream also propagates a disconnected caller.
        except Exception:
            if not started:
                self.reply(409 if cancelled.is_set() else 502,
                           {'error': 'Cat-watch quiet mode; background request deferred' if cancelled.is_set() else 'Local inference runtime unavailable'})
        finally:
            done.set()
            conn.close()
            self.close_connection = True

    def handle_request(self):
        path = urlsplit(self.path).path
        host = self.headers.get('Host', '').split(':')[0]
        if host not in ('127.0.0.1', 'localhost') or self.headers.get('Origin'):
            self.reply(403, {'error': 'Local agent API requests only'})
            return
        if self.command == 'GET':
            if path == '/health':
                with STATE_LOCK:
                    state = dict(STATE)
                self.reply(200 if state['ready'] else 503, state)
            elif path in GET_PATHS:
                self.forward(path)
            else:
                self.reply(404, {'error': 'Unknown endpoint'})
            return
        if self.command != 'POST' or path not in INFERENCE_PATHS | {'/api/show'}:
            self.reply(403, {'error': 'Model administration is disabled on the shared API'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY or self.headers.get('Transfer-Encoding'):
                self.reply(413, {'error': 'Supply a JSON request of at most 32 MiB'})
                return
            self.connection.settimeout(30)
            value = prepare(path, json.loads(self.rfile.read(length)))
        except (ValueError, TypeError, TimeoutError):
            self.reply(400, {'error': 'Invalid request or unsupported shared-service allocation settings'})
            return
        if path == '/api/show':
            self.forward(path, value)
            return
        with STATE_LOCK:
            ready = STATE['ready']
        if not ready:
            self.reply(503, {'error': 'Pinned model is not ready on GPU; retry later'})
            return
        try:
            with ADMISSION.slot(priority=1 if background(value, self.headers) else 0):
                managed = bool(DISPLAY and self.headers.get('X-Catwatch-Display-Managed') == '1')
                self.forward(path, value, display_managed=managed)
        except TimeoutError as error:
            self.reply(503, {'error': str(error)})

    do_GET = handle_request
    do_POST = handle_request
    do_DELETE = handle_request
    do_PUT = handle_request


if __name__ == '__main__':
    threading.Thread(target=supervisor, name='gpu-residency', daemon=True).start()
    server = ThreadingHTTPServer(('127.0.0.1', LOCK['public_port']), Handler)
    server.daemon_threads = True
    try:
        server.serve_forever()
    finally:
        STOP.set()
        server.server_close()
