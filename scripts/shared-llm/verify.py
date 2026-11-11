"""Bounded local synthetic API checks; saves no camera images or private answers."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import urllib.request

BASE = 'http://127.0.0.1:11434'
MODEL = 'qwen3.5:9b'


def call(path, body=None, stream=False):
    req = urllib.request.Request(BASE+path, data=None if body is None else json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=300) as response:
        return response.read().decode() if stream else json.load(response)


def verify(destination):
    started = time.monotonic()
    deadline = started+60
    while True:
        try:
            if call('/health').get('ready'):
                break
        except OSError:
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError('Shared GPU service did not become ready within 60 seconds')
        time.sleep(1)
    native = call('/api/chat', {'model': MODEL, 'stream': False, 'keep_alive': 0,
        'format': 'json', 'options': {'num_predict': 64, 'temperature': 0},
        'messages': [{'role': 'user', 'content': 'Return only the JSON object {"status":"ok"}.'}]})
    assert json.loads(native['message']['content']) == {'status': 'ok'}
    tool = call('/v1/chat/completions', {'model': MODEL, 'max_tokens': 128,
        'temperature': 0, 'messages': [{'role': 'user', 'content': 'Call the echo_value tool with value hello. Do not answer in prose.'}],
        'tools': [{'type': 'function', 'function': {'name': 'echo_value',
            'description': 'A synthetic test tool. No actual tool execution takes place.',
            'parameters': {'type': 'object', 'properties': {'value': {'type': 'string'}}, 'required': ['value']}}}]})
    function = tool['choices'][0]['message']['tool_calls'][0]['function']
    assert function['name'] == 'echo_value' and json.loads(function['arguments']) == {'value': 'hello'}
    stream = call('/v1/chat/completions', {'model': MODEL, 'stream': True, 'max_tokens': 32,
        'temperature': 0, 'messages': [{'role': 'user', 'content': 'Reply with exactly READY.'}]}, stream=True)
    assert 'data: [DONE]' in stream
    chunks = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith('data: {')]
    assert 'READY' in ''.join(c['choices'][0].get('delta', {}).get('content') or '' for c in chunks if c.get('choices'))
    ps = call('/api/ps')['models']
    assert len(ps) == 1 and ps[0]['name'] == MODEL and ps[0]['size_vram'] >= ps[0]['size']
    record = {'checked_at': datetime.now(timezone.utc).isoformat(), 'elapsed_seconds': round(time.monotonic()-started, 2),
              'native_json': True, 'openai_tool_call': True, 'openai_streaming': True,
              'keep_alive_zero_overridden': True, 'model_after': ps[0],
              'note': 'Three synthetic local requests. Tool call parsed only; no tool was executed. Not a quality benchmark.'}
    destination.write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps(record), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, required=True)
    verify(parser.parse_args().evidence)
