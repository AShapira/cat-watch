"""Explicit, immutable approvals for bounded outbound image batches."""
import base64
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
import os
import time

import httpx

from .contracts import PROMPT, PROMPT_VERSION, canonical, digest, normalize, number
from .media import jpeg, outbound_crop, sample

ENDPOINT = 'https://api.openai.com/v1/chat/completions'


def policies():
    """An operator-pinned model/price allowlist; absent means no cloud providers."""
    path = os.environ.get('CATWATCH_CLOUD_POLICY_FILE')
    if not path:
        return {}
    with open(path) as stream:
        raw = json.load(stream)
    valid = {}
    for model, policy in raw.items():
        if (not isinstance(model, str) or len(model) > 120 or
            not isinstance(policy, dict) or policy.get('provider') != 'openai' or
            not str(policy.get('source', '')).startswith(('https://developers.openai.com/', 'https://platform.openai.com/'))):
            raise ValueError('Cloud models require a pinned official pricing source')
        number(policy.get('context_tokens'), 1, 10_000_000)
        number(policy.get('input_usd_per_million'), .001, 1000)
        number(policy.get('output_usd_per_million'), .001, 1000)
        number(policy.get('valid_until'), 0, 1e12)
        if policy['valid_until'] > time.time():
            valid[model] = policy
    return valid


def request_ceiling(policy):
    # Reserve an entire model context at uncached rates, plus all possible output.
    # This is deliberately more conservative than an estimated image token count.
    return int((Decimal(str(policy['context_tokens']))*Decimal(str(policy['input_usd_per_million'])) +
                Decimal(1024)*Decimal(str(policy['output_usd_per_million']))).to_integral_value(rounding=ROUND_CEILING))


def propose(store, body):
    model = body.get('model')
    policy = policies().get(model)
    if not policy:
        raise ValueError('No current, priced cloud model is configured')
    items = body.get('items')
    if not isinstance(items, list) or not 1 <= len(items) <= 20:
        raise ValueError('Choose 1–20 clips')
    budget = number(body.get('budget_usd', 5), .01, 5)
    purpose = body.get('purpose', 'Resolve uncertain cat behaviors')
    if not isinstance(purpose, str) or not 1 <= len(purpose) <= 500:
        raise ValueError('State the purpose of this batch')
    prepared = []
    for item in items:
        clip = store.clip(item['clip_id'])
        if not outbound_crop(clip['manifest']):
            raise ValueError('Cloud review requires an area crop smaller than 80% of the camera frame')
        a = number(item.get('start', 0), 0, clip['duration'])
        b = number(item.get('end', min(a+8, clip['duration'])), a, clip['duration'])
        if not 0 < b-a <= 8:
            raise ValueError('Cloud clips are limited to eight seconds')
        images = []
        for stamp, frame in sample(store, clip, count=min(16, max(1, int((b-a)*2))), start=a, end=b):
            data = jpeg(frame)
            checksum = hashlib.sha256(data).hexdigest()
            relative = f'cloud/images/{checksum}.jpg'
            path = store.safe_path(relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_bytes(data)
            images.append({'time': stamp-a, 'hash': checksum, 'path': relative})
        prepared.append({'clip_id': clip['id'], 'start': a, 'end': b, 'images': images})
    ceiling = request_ceiling(policy)
    micros = int(Decimal(str(budget))*1_000_000)
    if ceiling*len(prepared) > micros:
        raise ValueError('Worst-case request cost exceeds this budget; select fewer clips or a cheaper approved model')
    manifest = {'provider': 'openai', 'endpoint': ENDPOINT, 'model': model, 'policy': policy,
                'purpose': purpose, 'items': prepared, 'max_images': sum(len(i['images']) for i in prepared),
                'budget_micros': micros, 'request_ceiling_micros': ceiling, 'max_output_tokens': 1024,
                'prompt': PROMPT, 'prompt_version': PROMPT_VERSION, 'store': False}
    ident = digest([manifest, time.time_ns()])
    with store.db() as db:
        db.execute('INSERT INTO cloud_batches(id,created,expires,state,manifest) VALUES (?,?,?,?,?)',
                   (ident, time.time(), min(time.time()+86400, policy['valid_until']), 'proposed', canonical(manifest)))
    return batch(store, ident)


def batch(store, ident):
    with store.db() as db:
        row = db.execute('SELECT * FROM cloud_batches WHERE id=?', (ident,)).fetchone()
        if row is None:
            raise KeyError(ident)
        result = dict(row, manifest=json.loads(row['manifest']), fingerprint=digest(json.loads(row['manifest'])))
        result['requests'] = [dict(r) for r in db.execute('SELECT item,state,reserved_micros FROM cloud_requests WHERE batch_id=?', (ident,))]
    return result


def approve(store, ident, fingerprint):
    with store.db() as db:
        row = db.execute('SELECT * FROM cloud_batches WHERE id=?', (ident,)).fetchone()
        if row is None:
            raise KeyError(ident)
        if row['state'] != 'proposed' or row['expires'] <= time.time():
            raise ValueError('Only an unexpired proposal can be approved')
        if fingerprint != digest(json.loads(row['manifest'])):
            raise ValueError('The outgoing batch changed; inspect it again')
        db.execute("UPDATE cloud_batches SET state='approved' WHERE id=?", (ident,))
    return batch(store, ident)


def revoke(store, ident):
    with store.db() as db:
        db.execute("UPDATE cloud_batches SET state='revoked' WHERE id=?", (ident,))
    return batch(store, ident)


def dispatch_one(store, *, transport=None):
    token = os.environ.get('CATWATCH_OPENAI_API_KEY')
    if not token:
        return False
    with store.db() as db:
        row = db.execute("SELECT * FROM cloud_batches WHERE state='approved' ORDER BY created LIMIT 1").fetchone()
        if row is None:
            return False
        if row['expires'] <= time.time():
            db.execute("UPDATE cloud_batches SET state='expired' WHERE id=?", (row['id'],))
            return False
        manifest = json.loads(row['manifest'])
        if policies().get(manifest['model']) != manifest['policy']:
            db.execute("UPDATE cloud_batches SET state='policy_changed' WHERE id=?", (row['id'],))
            return False
        used = {r[0] for r in db.execute('SELECT item FROM cloud_requests WHERE batch_id=?', (row['id'],))}
        pending = [n for n in range(len(manifest['items'])) if n not in used]
        if not pending:
            unknown = db.execute("SELECT 1 FROM cloud_requests WHERE batch_id=? AND state IN ('unknown','sending','failed')", (row['id'],)).fetchone()
            db.execute('UPDATE cloud_batches SET state=? WHERE id=?', ('needs_attention' if unknown else 'complete', row['id']))
            return False
        index = pending[0]
        item = manifest['items'][index]
        ceiling = manifest['request_ceiling_micros']
        if row['reserved_micros']+ceiling > manifest['budget_micros']:
            db.execute("UPDATE cloud_batches SET state='exhausted' WHERE id=?", (row['id'],))
            return False
        content = [{'type': 'text', 'text': f"Clip duration {item['end']-item['start']:.3f} seconds. Return JSON."}]
        for frame in item['images']:
            data = store.safe_path(frame['path']).read_bytes()
            if hashlib.sha256(data).hexdigest() != frame['hash']:
                db.execute("UPDATE cloud_batches SET state='payload_changed' WHERE id=?", (row['id'],))
                return False
            content.extend([{'type': 'text', 'text': f"Frame at {frame['time']:.3f}s"},
                            {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,'+base64.b64encode(data).decode(), 'detail': 'high'}}])
        # Durable reservation precedes network activity. Unknown outcomes consume the
        # entire reservation and are never retried automatically.
        db.execute('INSERT INTO cloud_requests VALUES (?,?,?,?,NULL)', (row['id'], index, 'sending', ceiling))
        db.execute('UPDATE cloud_batches SET reserved_micros=reserved_micros+? WHERE id=?', (ceiling, row['id']))
    try:
        with httpx.Client(timeout=180, follow_redirects=False, transport=transport) as client:
            response = client.post(ENDPOINT, headers={'Authorization': 'Bearer '+token}, json={
                'model': manifest['model'], 'store': False, 'max_completion_tokens': 1024,
                'response_format': {'type': 'json_object'},
                'messages': [{'role': 'system', 'content': manifest['prompt']}, {'role': 'user', 'content': content}]})
            response.raise_for_status()
            result = response.json()
        ann = normalize(json.loads(result['choices'][0]['message']['content']), item['end']-item['start'], proposal=True)
        for interval in ann['intervals']:
            interval['start'] += item['start']; interval['end'] += item['start']
        store.prediction(item['clip_id'], ann, {'provider': 'openai', 'model': manifest['model'],
                         'prompt_version': PROMPT_VERSION, 'batch_id': row['id'], 'response_id': result.get('id', '')})
        state, saved = 'complete', {'usage': result.get('usage'), 'response_id': result.get('id')}
    except Exception:
        state, saved = 'unknown', {'message': 'Request outcome or response validation needs review; no automatic retry'}
    with store.db() as db:
        db.execute('UPDATE cloud_requests SET state=?,result=? WHERE batch_id=? AND item=?',
                   (state, canonical(saved), row['id'], index))
    return True
