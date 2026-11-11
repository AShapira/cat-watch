"""One authorized cloud comparison, with durable reservations and no automatic retries.

This runner has its own ledger. It never changes human decisions, training data,
the recording session, or the production teacher's latest prediction.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
import base64
import csv
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time

import httpx

from .contracts import ALL_LABELS, PROMPT, canonical, coarse, digest, normalize
from .media import file_hash, jpeg, outbound_crop, sample

AUTHORIZATION = '2026-11-03-pro-credit-comparison'
BUDGET = 20_000_000  # USD microdollars, one non-renewing authorization.
ENDPOINT = 'https://api.openai.com/v1'
MODEL_DIGEST = '6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7'
MAX_INPUT = 65_536
POLICIES = {
    'gpt-6.1-sol': {'effort': 'medium', 'output_limit': 4096, 'input_rate': '2',
                   'cached_rate': '0.10', 'output_rate': '10', 'maximum_input_rate': '5'},
    'gpt-6-astra': {'effort': 'high', 'output_limit': 8192, 'input_rate': '10',
                  'cached_rate': '1', 'output_rate': '50', 'maximum_input_rate': '25'},
}
PRICE_SOURCE = 'https://developers.openai.com/api/docs/pricing'
CACHE_SOURCE = 'https://developers.openai.com/api/docs/guides/prompt-caching'
COMPARE_PROMPT = PROMPT + '''
Evidence and uncertainty must be strings; use an empty string when appropriate.
For multiple_cats or uncertain_presence, use only unclear or no_cat intervals.
Do not guess unseen behavior. Do not infer a duration from repeated frames.
The timestamps are relative to this clip. Use only the supplied duration bounds.
'''


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def micros(tokens, rate):
    return int((Decimal(tokens)*Decimal(rate)).to_integral_value(rounding=ROUND_CEILING))


def limits(manifest, model):
    """Only explicitly frozen lower token caps may differ from pinned policy."""
    policies = manifest.get('policies', {})
    if set(policies) != set(POLICIES):
        raise ValueError('Pricing or models changed; authorization cannot be reused')
    for name, base in POLICIES.items():
        policy = policies[name]
        if set(policy) != set(base) or any(policy[k] != base[k] for k in base if k != 'output_limit'):
            raise ValueError('Pricing or effort changed; authorization cannot be reused')
        if type(policy['output_limit']) is not int or not 1 <= policy['output_limit'] <= base['output_limit']:
            raise ValueError('Output limit may only be reduced in a new frozen manifest')
    maximum = manifest.get('max_input_tokens')
    if type(maximum) is not int or not 1 <= maximum <= MAX_INPUT:
        raise ValueError('Input limit may only be reduced in a new frozen manifest')
    return policies[model], maximum


def reservation_for(model, *, manifest=None):
    if model == 'qwen3.5:9b':
        return 0
    p, maximum = limits(manifest, model) if manifest is not None else (POLICIES[model], MAX_INPUT)
    return 2*micros(maximum, p['maximum_input_rate'])+micros(p['output_limit'], p['output_rate'])


def cache_categories(usage):
    details = usage.get('input_tokens_details') or {}
    cached, writes = details.get('cached_tokens', 0), details.get('cache_write_tokens', 0)
    split = details.get('cache_write_tokens_details')
    # No cache options or explicit breakpoints are sent by this campaign, so
    # the documented 30m default applies when the response omits the TTL split.
    short, long = (writes, 0) if not split else (split.get('ttl_30m_tokens', 0), split.get('ttl_12h_tokens', 0))
    if any(type(n) is not int or n < 0 for n in (cached, writes, short, long)):
        raise ValueError('Invalid cache usage')
    if short+long != writes or cached+writes > usage['input_tokens']:
        raise ValueError('Cache token categories do not reconcile')
    return cached, short, long


def estimate_usage(usage, model, *, manifest=None):
    p, maximum = limits(manifest, model) if manifest is not None else (POLICIES[model], MAX_INPUT)
    inputs, outputs = usage['input_tokens'], usage['output_tokens']
    if type(inputs) is not int or type(outputs) is not int or not 0 <= inputs <= maximum or not 0 <= outputs <= p['output_limit']:
        raise ValueError('Unexpected token usage; reservation retained')
    cached, short, long = cache_categories(usage)
    # Cache writes replace the ordinary input rate; they are not a surcharge.
    return (micros(inputs-cached-short-long, p['input_rate'])+micros(cached, p['cached_rate'])
            +micros(short, Decimal(p['input_rate'])*Decimal('1.25'))
            +micros(long, p['maximum_input_rate'])+micros(outputs, p['output_rate']))


def schema(duration):
    interval = {'type': 'object', 'additionalProperties': False,
        'required': ['start', 'end', 'label', 'evidence', 'uncertainty'],
        'properties': {'start': {'type': 'number', 'minimum': 0, 'maximum': duration},
            'end': {'type': 'number', 'minimum': 0, 'maximum': duration},
            'label': {'type': 'string', 'enum': list(ALL_LABELS)},
            'evidence': {'type': 'string', 'maxLength': 1500},
            'uncertainty': {'type': 'string', 'maxLength': 1500}}}
    return {'type': 'object', 'additionalProperties': False,
        'required': ['subject', 'quality', 'intervals'], 'properties': {
            'subject': {'type': 'string', 'enum': ['single_cat', 'no_cat', 'multiple_cats', 'uncertain_presence']},
            'quality': {'type': 'array', 'items': {'type': 'string', 'enum': ['occlusion', 'blur', 'poor_lighting', 'truncated_activity']}},
            'intervals': {'type': 'array', 'minItems': 1, 'maxItems': 32, 'items': interval}}}


class Ledger:
    def __init__(self, path, *, authorization=AUTHORIZATION, clip_limit=10, allowed_models=None):
        self.authorization = authorization
        self.clip_limit = clip_limit
        self.allowed_models = set(allowed_models or (*POLICIES, "qwen3.5:9b"))
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS authorization (
                    id TEXT PRIMARY KEY, created REAL NOT NULL, expires REAL NOT NULL,
                    budget INTEGER NOT NULL, manifest TEXT NOT NULL, fingerprint TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY, authorization TEXT NOT NULL, clip_id TEXT NOT NULL,
                    model TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL,
                    reservation INTEGER NOT NULL, accounted INTEGER NOT NULL,
                    estimate INTEGER, body TEXT NOT NULL,
                    UNIQUE(authorization,clip_id,model));
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def authorize(self, manifest):
        fingerprint = digest(manifest)
        with self.db() as db:
            prior = db.execute('SELECT * FROM authorization WHERE id=?', (self.authorization,)).fetchone()
            if prior:
                if prior['fingerprint'] != fingerprint:
                    raise ValueError('Authorization already exists; do not reset or replace the budget')
                return
            if manifest['budget_micros'] != BUDGET or manifest['authorization'] != self.authorization:
                raise ValueError('Unexpected authorization or budget')
            if not 1 <= len(manifest['items']) <= self.clip_limit or len({i['clip_id'] for i in manifest['items']}) != len(manifest['items']):
                raise ValueError('Distinct clips within the campaign limit must be frozen')
            db.execute('INSERT INTO authorization VALUES (?,?,?,?,?,?)',
                       (self.authorization, time.time(), manifest['expires_epoch'], BUDGET, canonical(manifest), fingerprint))

    def manifest(self):
        with self.db() as db:
            row = db.execute('SELECT * FROM authorization WHERE id=?', (self.authorization,)).fetchone()
            if not row:
                raise ValueError('Prepare the explicit authorized comparison first')
            value = json.loads(row['manifest'])
            if digest(value) != row['fingerprint']:
                raise ValueError('Authorization fingerprint changed')
            return value

    def requests(self):
        with self.db() as db:
            return [dict(r, body=json.loads(r['body'])) for r in db.execute(
                'SELECT * FROM requests WHERE authorization=? ORDER BY created', (self.authorization,))]

    def reserve(self, clip_id, model, reservation):
        if model not in self.allowed_models:
            raise ValueError('Model is not authorized')
        with self.db() as db:
            auth = db.execute('SELECT * FROM authorization WHERE id=?', (self.authorization,)).fetchone()
            if not auth or auth['expires'] <= time.time():
                raise ValueError('Authorization expired or missing')
            manifest = json.loads(auth['manifest'])
            if model != 'qwen3.5:9b' and model not in manifest.get('dispatch_models', POLICIES):
                raise ValueError('Model is not authorized by the frozen manifest')
            if type(reservation) is not int or reservation != reservation_for(model, manifest=manifest):
                raise ValueError('Invalid reservation')
            if digest(manifest) != auth['fingerprint'] or clip_id not in {i['clip_id'] for i in manifest['items']}:
                raise ValueError('Clip is not in the approved immutable manifest')
            if db.execute('SELECT 1 FROM requests WHERE authorization=? AND clip_id=? AND model=?',
                          (self.authorization, clip_id, model)).fetchone():
                return None  # Includes unknown/failed attempts: never automatically resend.
            if model == 'gpt-6-astra' and db.execute('SELECT COUNT(*) FROM requests WHERE authorization=? AND model=?',
                                                   (self.authorization, model)).fetchone()[0] >= 5:
                raise ValueError('Astra request limit reached')
            used = db.execute('SELECT COALESCE(SUM(accounted),0) FROM requests').fetchone()[0]
            if used+reservation > auth['budget']:
                raise ValueError('The $20 authorization cannot cover another worst-case request')
            ident = digest([self.authorization, clip_id, model])
            db.execute('INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?,?)',
                (ident, self.authorization, clip_id, model, 'sending', time.time(), reservation, reservation,
                 None, canonical({'started_at': now_iso()})))
            return ident

    def finish(self, ident, state, body, *, accounted=None, estimate=None):
        with self.db() as db:
            row = db.execute('SELECT * FROM requests WHERE id=?', (ident,)).fetchone()
            if not row or row['state'] != 'sending':
                raise ValueError('Only an in-flight request can be settled')
            amount = row['reservation'] if accounted is None else accounted
            if type(amount) is not int or amount < 0 or amount > row['reservation']:
                raise ValueError('Usage exceeded the reservation; stop and reconcile billing')
            db.execute('UPDATE requests SET state=?,accounted=?,estimate=?,body=? WHERE id=?',
                       (state, amount, estimate, canonical(body), ident))

    def totals(self):
        rows = self.requests()
        with self.db() as db:
            all_rows = db.execute('SELECT accounted,estimate FROM requests').fetchall()
        return {'budget_usd': BUDGET/1e6,
                'inference_estimate_usd': round(sum(r['estimate'] or 0 for r in all_rows)/1e6, 6),
                'conservative_accounted_usd': round(sum(r['accounted'] for r in all_rows)/1e6, 6),
                'remaining_authorized_usd': round((BUDGET-sum(r['accounted'] for r in all_rows))/1e6, 6),
                'unknown_or_in_flight': sum(r['state'] in ('unknown', 'sending') for r in rows),
                'cloud_requests': sum(r['model'] in POLICIES for r in rows),
                'note': 'Token-rate estimate, not an invoice. Conservative accounting includes a token-count allowance and highest cache-write input rates; unknown outcomes retain full reservations.'}

    def reconcile_estimates(self):
        """Correct saved usage estimates offline; preserve exposure and an audit trail."""
        changed = 0
        with self.db() as db:
            rows = db.execute('SELECT * FROM requests WHERE authorization=?', (self.authorization,)).fetchall()
            if any(r['model'] in POLICIES and r['state'] == 'sending' for r in rows):
                raise ValueError('Wait for cloud dispatch to stop before reconciling')
            for row in rows:
                if row['model'] not in POLICIES or row['state'] not in ('complete', 'invalid'):
                    continue
                body = json.loads(row['body'])
                estimate = estimate_usage(body['usage'], row['model'])
                if estimate > row['accounted']:
                    raise ValueError('Corrected estimate exceeds conservative exposure; investigate')
                if estimate == row['estimate']:
                    continue
                body.setdefault('accounting_revisions', []).append({'checked_at': now_iso(),
                    'previous_estimate_micros': row['estimate'], 'corrected_estimate_micros': estimate,
                    'reason': 'Include returned cache-write tokens at documented TTL rates; missing TTL split uses the request default 30m',
                    'source': CACHE_SOURCE})
                db.execute('UPDATE requests SET estimate=?,body=? WHERE id=?', (estimate, canonical(body), row['id']))
                changed += 1
        return changed


class Evidence:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def safe_path(self, relative):
        path = (self.root/relative).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('Evidence path is outside the owned directory')
        return path


def read_clips(root):
    with sqlite3.connect('file:'+str(Path(root)/'agent.sqlite3')+'?mode=ro', uri=True, timeout=20) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute('SELECT * FROM clips ORDER BY start,id').fetchall()
    return [dict(r, **{k: json.loads(r[k]) if r[k] else None for k in ('manifest', 'prediction', 'decision')}) for r in rows]


def prepare(root, ledger):
    try:
        return ledger.manifest()
    except ValueError as error:
        if str(error) != 'Prepare the explicit authorized comparison first':
            raise
    evidence = Evidence(root)
    clips = read_clips(root)
    eligible = [c for c in clips if 6 <= c['duration'] <= 8.01 and outbound_crop(c['manifest'])
                and evidence.safe_path(c['manifest']['video']).is_file()
                and (c['decision'] or c['bucket'] != 'evaluation')]
    # Human references first; one clip per source episode prevents trivial duplicates.
    selected, groups, used_labels = [], set(), set()
    def overlaps(c):
        return any(c['start'] < other['start']+other['duration'] and other['start'] < c['start']+c['duration'] for other in selected)
    for c in sorted(eligible, key=lambda c: (not bool(c['decision']), c['start'], c['id'])):
        if not c['decision'] or c['group_key'] in groups or overlaps(c):
            continue
        selected.append(c); groups.add(c['group_key'])
        if len(selected) == 10:
            break
    remaining = [c for c in eligible if not c['decision'] and c['group_key'] not in groups and not overlaps(c)]
    while len(selected) < 10 and remaining:
        def key(c):
            labels = {coarse(i['label']) for i in (c['prediction'] or {}).get('intervals', [])}
            return (not bool(labels-used_labels), not bool(labels & {'eating', 'drinking', 'litter_activity'}), -c['start'], c['id'])
        c = min(remaining, key=key)
        selected.append(c); groups.add(c['group_key'])
        used_labels.update(coarse(i['label']) for i in (c['prediction'] or {}).get('intervals', []))
        remaining = [r for r in remaining if r['group_key'] not in groups and not overlaps(r)]
    if not selected:
        raise ValueError('No suitable 6–8 second cropped clips available')
    folder = evidence.safe_path('comparisons/'+AUTHORIZATION)
    folder.mkdir(parents=True, exist_ok=True)
    items = []
    for c in selected:
        m = c['manifest']
        if file_hash(evidence.safe_path(m['video'])) != m['video_hash']:
            raise ValueError('Source clip changed')
        duration = min(8., math.floor(c['duration']*1000)/1000)
        frames = []
        for stamp, frame in sample(evidence, c, count=16, start=0, end=duration):
            data = jpeg(frame); sha = hashlib.sha256(data).hexdigest()
            relative = f'comparisons/{AUTHORIZATION}/images/{sha}.jpg'
            path = evidence.safe_path(relative); path.parent.mkdir(exist_ok=True)
            path.write_bytes(data)
            frames.append({'time': round(stamp, 6), 'path': relative, 'sha256': sha,
                           'width': frame.shape[1], 'height': frame.shape[0]})
        items.append({'clip_id': c['id'], 'duration': duration, 'frames': frames,
            'group_key': c['group_key'], 'day': c['day'], 'areas': m['areas'],
            'human_reference': c['decision'], 'human_version': c['version'],
            'selection': 'human_reviewed' if c['decision'] else 'local_proposal_stratified',
            'source_video_hash': m['video_hash']})
    manifest = {'authorization': AUTHORIZATION, 'budget_micros': BUDGET,
        'created_at': now_iso(), 'expires_epoch': time.time()+6*3600,
        'authority': 'User authorized up to USD 20 total from current-cycle credits for the proposed models, cost logging and comparison with local Qwen.',
        'reported_cycle_credit_usd': 39, 'automatic_renewal': False,
        'max_sol_requests': 10, 'max_astra_requests': 5, 'max_frames_per_request': 16,
        'max_input_tokens': MAX_INPUT, 'policies': POLICIES, 'price_source': PRICE_SOURCE,
        'price_checked_date': '2026-11-03', 'prompt': COMPARE_PROMPT,
        'prompt_version': 'paired-visible-actions-1', 'local_model': 'qwen3.5:9b',
        'local_digest': MODEL_DIGEST, 'items': items}
    ledger.authorize(manifest)
    (folder/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return manifest


def frame_payload(root, item):
    evidence = Evidence(root)
    images = []
    for f in item['frames']:
        raw = evidence.safe_path(f['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != f['sha256']:
            raise ValueError('Prepared outgoing frame changed; nothing sent')
        images.append(base64.b64encode(raw).decode())
    return images


def local_one(root, ledger, item, *, client=None):
    images = frame_payload(root, item)
    ident = ledger.reserve(item['clip_id'], 'qwen3.5:9b', 0)
    if not ident:
        return
    started = time.monotonic()
    try:
        with client or httpx.Client(timeout=240, trust_env=False) as connection:
            ps = connection.get('http://127.0.0.1:11434/api/ps'); ps.raise_for_status()
            if not any(m.get('digest') == MODEL_DIGEST and m.get('size_vram', 0) >= m['size'] for m in ps.json()['models']):
                raise ValueError('Pinned local model is not fully GPU resident')
            response = connection.post('http://127.0.0.1:11434/api/chat',
                headers={'X-Local-Agent-Priority': 'background'}, json={
                    'model': 'qwen3.5:9b', 'think': False, 'stream': False,
                    'format': schema(item['duration']),
                    'options': {'num_ctx': 16384, 'num_predict': 4096, 'temperature': 0},
                    'messages': [{'role': 'system', 'content': ledger.manifest()['prompt']},
                        {'role': 'user', 'content': f"Duration {item['duration']}s; frame times: {[f['time'] for f in item['frames']]}", 'images': images}]})
            response.raise_for_status(); data = response.json()
            ps = connection.get('http://127.0.0.1:11434/api/ps'); ps.raise_for_status()
            if not any(m.get('digest') == MODEL_DIGEST and m.get('size_vram', 0) >= m['size'] for m in ps.json()['models']):
                raise ValueError('Pinned local model residency changed during comparison')
        annotation = normalize(json.loads(data['message']['content']), item['duration'], proposal=True)
        ledger.finish(ident, 'complete', {'annotation': annotation, 'elapsed_seconds': round(time.monotonic()-started, 3),
            'digest': MODEL_DIGEST, 'prompt_eval_count': data.get('prompt_eval_count'), 'eval_count': data.get('eval_count')}, accounted=0, estimate=0)
    except Exception as error:
        ledger.finish(ident, 'failed', {'error_type': type(error).__name__, 'elapsed_seconds': round(time.monotonic()-started, 3)}, accounted=0, estimate=0)


def cloud_body(manifest, item, model, images):
    p, _ = limits(manifest, model)
    content = [{'type': 'input_text', 'text': f"Duration {item['duration']}s. Frame times are relative to this clip."}]
    for f, image in zip(item['frames'], images):
        content += [{'type': 'input_text', 'text': f"{f.get('view', 'Frame')} at {f['time']:.6f}s"},
                    {'type': 'input_image', 'image_url': 'data:image/jpeg;base64,'+image, 'detail': 'high'}]
    return {'model': model, 'instructions': manifest['prompt'],
        'input': [{'role': 'user', 'content': content}], 'store': False,
        'reasoning': {'effort': p['effort'], 'mode': 'standard'},
        'service_tier': 'default', 'max_output_tokens': p['output_limit'],
        'text': {'format': {'type': 'json_schema', 'name': 'cat_behavior', 'strict': True,
                            'schema': schema(item['duration'])}}, 'truncation': 'disabled'}


def cloud_one(root, ledger, item, model, key, *, client=None):
    manifest = ledger.manifest()
    p, maximum = limits(manifest, model)
    if not isinstance(key, str) or not key.strip():
        raise ValueError('A project API key is required')
    body = cloud_body(manifest, item, model, frame_payload(root, item))
    # Reserve input twice, covering both preflight and generation, at the highest
    # documented cache-write rate. A counting allowance is retained even though
    # it is not an inference response. This is deliberately above the estimate.
    ceiling = reservation_for(model, manifest=manifest)
    ident = ledger.reserve(item['clip_id'], model, ceiling)
    if not ident:
        return
    started = time.monotonic(); counted = None
    try:
        with client or httpx.Client(timeout=240, follow_redirects=False, trust_env=False) as connection:
            headers = {'Authorization': 'Bearer '+key, 'Content-Type': 'application/json'}
            count_body = {k: body[k] for k in ('model', 'instructions', 'input', 'text', 'reasoning')}
            response = connection.post(ENDPOINT+'/responses/input_tokens', headers=headers, json=count_body)
            if response.status_code != 200:
                ledger.finish(ident, 'unknown', {'phase': 'token_count', 'http_status': response.status_code})
                return
            counted = response.json()['input_tokens']
            if type(counted) is not int or not 0 < counted <= maximum:
                ledger.finish(ident, 'blocked_input_limit', {'input_tokens': counted})
                return
            response = connection.post(ENDPOINT+'/responses', headers={**headers, 'Idempotency-Key': ident}, json=body)
            if response.status_code != 200:
                ledger.finish(ident, 'unknown', {'phase': 'generation', 'http_status': response.status_code, 'counted_input_tokens': counted})
                return
            data = response.json()
        usage = data['usage']; inputs, outputs = usage['input_tokens'], usage['output_tokens']
        estimate = estimate_usage(usage, model, manifest=manifest)
        accounted = micros(counted+inputs, p['maximum_input_rate'])+micros(outputs, p['output_rate'])
        answer = ''.join(c.get('text', '') for output in data.get('output', []) if output.get('type') == 'message'
                         for c in output.get('content', []) if c.get('type') == 'output_text')
        result = {'response_id': data.get('id'), 'returned_model': data.get('model'),
            'reasoning_effort': p['effort'], 'usage': usage, 'counted_input_tokens': counted,
            'elapsed_seconds': round(time.monotonic()-started, 3), 'finished_at': now_iso(),
            'service_tier': data.get('service_tier'), 'provider_status': data.get('status')}
        try:
            if data.get('status') != 'completed':
                raise ValueError('Provider response incomplete')
            result['annotation'] = normalize(json.loads(answer), item['duration'], proposal=True)
            state = 'complete'
        except (ValueError, TypeError, KeyError):
            state = 'invalid'; result['validation'] = 'No usable annotation; preserved usage without retry'
        ledger.finish(ident, state, result, accounted=accounted, estimate=estimate)
    except Exception as error:
        # Ambiguous failures never release money or trigger an automatic retry.
        ledger.finish(ident, 'unknown', {'error_type': type(error).__name__, 'counted_input_tokens': counted,
                      'elapsed_seconds': round(time.monotonic()-started, 3)})


def agreement(reference, prediction):
    """Duration-weighted coarse-label agreement; unlabeled/unclear reference is excluded."""
    if not reference or not prediction:
        return None
    seconds = matched = 0.
    for a in reference['intervals']:
        label = coarse(a['label'])
        if label == 'unclear':
            continue
        seconds += a['end']-a['start']
        for b in prediction['intervals']:
            if coarse(b['label']) == label:
                matched += max(0., min(a['end'], b['end'])-max(a['start'], b['start']))
    return {'reference_seconds': round(seconds, 6), 'matched_seconds': round(matched, 6),
            'agreement': round(matched/seconds, 6) if seconds else None}


def choose_astra(ledger):
    rows = {(r['clip_id'], r['model']): r['body'].get('annotation') for r in ledger.requests()}
    items = ledger.manifest()['items']
    def rank(item):
        local, sol = [rows.get((item['clip_id'], m)) for m in ('qwen3.5:9b', 'gpt-6.1-sol')]
        value = agreement(local, sol)
        return (value['agreement'] if value and value['agreement'] is not None else -1, item['clip_id'])
    return sorted(items, key=rank)[:min(5, len(items))]


def human_metrics(items, found, model):
    """Include failed/missing labels as zero coverage within an attempted subset."""
    seconds = matched = covered = 0.
    independent_seconds = independent_matched = 0.
    for item in items:
        reference = item['human_reference']
        request = found.get((item['clip_id'], model))
        if not reference or not request:
            continue
        annotation = request['body'].get('annotation')
        value = agreement(reference, annotation or {'intervals': []})
        if not value:
            continue
        seconds += value['reference_seconds']; matched += value['matched_seconds']
        if annotation:
            covered += value['reference_seconds']
        if reference.get('independent'):
            independent_seconds += value['reference_seconds']; independent_matched += value['matched_seconds']
    return {'human_reference_seconds': round(seconds, 3),
        'human_label_agreement': round(matched/seconds, 4) if seconds else None,
        'valid_output_reference_coverage': round(covered/seconds, 4) if seconds else None,
        'independent_reference_seconds': round(independent_seconds, 3),
        'independent_label_agreement': round(independent_matched/independent_seconds, 4) if independent_seconds else None}


def report(root, ledger):
    manifest = ledger.manifest(); rows = ledger.requests()
    found = {(r['clip_id'], r['model']): r for r in rows}
    summary = {'checked_at': now_iso(), 'authorization': AUTHORIZATION, 'totals': ledger.totals(),
               'clips': len(manifest['items']), 'human_reference_clips': sum(bool(i['human_reference']) for i in manifest['items']),
               'models': {}, 'items': []}
    for model in ('qwen3.5:9b', *POLICIES):
        selected = [r for r in rows if r['model'] == model]
        timed = [r['body']['elapsed_seconds'] for r in selected if 'elapsed_seconds' in r['body']]
        summary['models'][model] = {'attempts': len(selected), 'valid': sum(r['state'] == 'complete' for r in selected),
            'inference_estimate_usd': round(sum(r['estimate'] or 0 for r in selected)/1e6, 6),
            'mean_seconds': round(sum(timed)/len(timed), 3) if timed else None,
            **human_metrics(manifest['items'], found, model)}
    subset = [i for i in manifest['items'] if all((i['clip_id'], m) in found for m in ('qwen3.5:9b', *POLICIES))]
    summary['matched_three_model_subset'] = {'clips': len(subset), 'models': {
        m: human_metrics(subset, found, m) for m in ('qwen3.5:9b', *POLICIES)}}
    for item in manifest['items']:
        row = {'clip_id': item['clip_id'], 'duration': item['duration'], 'areas': item['areas'],
               'human_reference': item['human_reference'], 'human_version': item['human_version'], 'models': {}}
        for model in ('qwen3.5:9b', *POLICIES):
            request = found.get((item['clip_id'], model))
            if request:
                row['models'][model] = {'state': request['state'], 'annotation': request['body'].get('annotation'),
                    'human_agreement': agreement(item['human_reference'], request['body'].get('annotation'))}
        local = row['models'].get('qwen3.5:9b', {}).get('annotation')
        for model in POLICIES:
            if model in row['models']:
                row['models'][model]['qwen_agreement'] = agreement(local, row['models'][model].get('annotation'))
        summary['items'].append(row)
    folder = Path(root)/'comparisons'/AUTHORIZATION
    folder.mkdir(parents=True, exist_ok=True)
    (folder/'comparison.json').write_text(json.dumps(summary, indent=2)+'\n')
    lines = ['# Cat-watch cloud/local comparison', '', 'Updated: '+summary['checked_at'], '',
        '**This is a small diagnostic comparison, not a behavior-accuracy qualification.**',
        'Human references can include assisted reviews. Astra is selected for disagreement; compare it only on the same subset.',
        'No prediction replaces a human decision or enters training automatically.', '',
        '| Model | Valid / attempted | Agreement with available human labels | Estimated inference USD |',
        '| --- | --- | --- | --- |']
    for model, m in summary['models'].items():
        value = 'not available' if m['human_label_agreement'] is None else f"{m['human_label_agreement']:.1%} over {m['human_reference_seconds']}s"
        lines.append(f"| {model} | {m['valid']} / {m['attempts']} | {value} | ${m['inference_estimate_usd']:.6f} |")
    totals = summary['totals']
    lines += ['', f"Authorized maximum: ${totals['budget_usd']:.2f}. Conservative accounted exposure: ${totals['conservative_accounted_usd']:.6f}. Remaining authorization: ${totals['remaining_authorized_usd']:.6f}.", totals['note'], '']
    lines += ['Invalid outputs count as missing predictions in the attempted human-reference denominator. '
              'Unreviewed clips measure model agreement only; agreement does not establish correctness.', '',
              'Matched three-model subset (avoids comparing Astra hard cases against easier Sol cases):', '',
              '```json', json.dumps(summary['matched_three_model_subset'], indent=2), '```', '']
    for item in summary['items']:
        lines += [f"## Clip {item['clip_id'][:12]} — {item['duration']}s", '',
            f"[Open saved source video](http://127.0.0.1:8765/api/learning/clips/{item['clip_id']}/video)", '',
            'Area crop(s): '+', '.join(item['areas']), '',
            'Human reference: '+(canonical(item['human_reference']) if item['human_reference'] else 'Not independently reviewed'), '']
        for model, result in item['models'].items():
            lines += [f"### {model}: {result['state']}", '']
            for interval in (result.get('annotation') or {}).get('intervals', []):
                lines += [f"- {interval['start']}–{interval['end']}s: **{interval['label']}**. {interval['evidence']} Uncertainty: {interval['uncertainty']}"]
            lines.append('')
    (folder/'comparison.md').write_text('\n'.join(lines)+'\n')
    # Cost-only data can be used in the development journal without private content.
    safe = {k: v for k, v in summary.items() if k != 'items'}
    (folder/'cost-summary.json').write_text(json.dumps(safe, indent=2)+'\n')
    with (folder/'cost-ledger.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['request_id', 'clip_id', 'model', 'state', 'created_utc', 'input_tokens',
                         'cached_tokens', 'cache_write_30m_tokens', 'cache_write_12h_tokens',
                         'output_tokens_including_reasoning', 'reasoning_tokens',
                         'inference_estimate_usd', 'conservative_accounted_usd', 'reservation_usd'])
        for r in rows:
            usage = r['body'].get('usage') or {}
            cached, short, long = cache_categories(usage) if usage else ('', '', '')
            writer.writerow([r['id'], r['clip_id'], r['model'], r['state'],
                datetime.fromtimestamp(r['created'], timezone.utc).isoformat(), usage.get('input_tokens'),
                cached, short, long, usage.get('output_tokens'),
                usage.get('output_tokens_details', {}).get('reasoning_tokens'),
                '' if r['estimate'] is None else f"{r['estimate']/1e6:.6f}",
                f"{r['accounted']/1e6:.6f}", f"{r['reservation']/1e6:.6f}"])
    return safe
