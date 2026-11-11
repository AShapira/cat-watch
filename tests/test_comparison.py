from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import time

import httpx
import pytest

from catwatch.learning import comparison as c


def annotation(label='moving'):
    return {'subject': 'single_cat', 'quality': [], 'intervals': [
        {'start': 0, 'end': 6, 'label': label, 'evidence': 'Visible at 1s', 'uncertainty': ''}]}


def setup(tmp_path, count=10):
    raw = b'fixture-image'; (tmp_path/'frame.jpg').write_bytes(raw)
    items = [{'clip_id': str(i), 'duration': 6, 'frames': [{'time': 0, 'path': 'frame.jpg',
              'sha256': hashlib.sha256(raw).hexdigest()}], 'areas': ['fixture'],
              'human_reference': {**annotation(), 'independent': i == 0}, 'human_version': 2} for i in range(count)]
    manifest = {'authorization': c.AUTHORIZATION, 'budget_micros': c.BUDGET,
                'expires_epoch': time.time()+3600, 'items': items, 'policies': c.POLICIES,
                'max_input_tokens': c.MAX_INPUT, 'prompt': c.COMPARE_PROMPT}
    ledger = c.Ledger(tmp_path/'ledger.sqlite3'); ledger.authorize(manifest)
    return ledger, items, manifest


def test_concurrent_reservations_and_restart_cannot_overspend(tmp_path):
    ledger, items, manifest = setup(tmp_path)
    def reserve(pair):
        clip, model = pair
        try:
            return ledger.reserve(clip['clip_id'], model, c.reservation_for(model))
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(reserve, [(i, m) for i in items for m in c.POLICIES]))
    total = ledger.totals()
    assert 15 < total['conservative_accounted_usd'] <= 20
    resumed = c.Ledger(ledger.path)
    assert resumed.totals() == total
    row = ledger.requests()[0]
    assert resumed.reserve(row['clip_id'], row['model'], row['reservation']) is None
    with pytest.raises(ValueError, match='reset'):
        resumed.authorize({**manifest, 'expires_epoch': time.time()+7200})
    assert sum(r['model'] == 'gpt-6-astra' for r in resumed.requests()) <= 5


def test_cannot_underreserve_or_use_unapproved_clip_or_expired_authority(tmp_path):
    ledger, items, _ = setup(tmp_path)
    with pytest.raises(ValueError, match='reservation'):
        ledger.reserve('0', 'gpt-6-astra', 0)
    with pytest.raises(ValueError, match='manifest'):
        ledger.reserve('outside', 'gpt-6.1-sol', c.reservation_for('gpt-6.1-sol'))
    with ledger.db() as db:
        db.execute('UPDATE authorization SET expires=0')
    with pytest.raises(ValueError, match='expired'):
        ledger.reserve('0', 'qwen3.5:9b', 0)


def test_unknown_request_retains_money_and_is_not_retried(tmp_path):
    ledger, items, _ = setup(tmp_path)
    calls = []
    def handler(request):
        calls.append(request)
        assert ledger.requests()[0]['accounted'] == c.reservation_for('gpt-6.1-sol')
        raise httpx.ReadTimeout('fixture')
    for _ in range(2):
        c.cloud_one(tmp_path, ledger, items[0], 'gpt-6.1-sol', 'fixture-secret',
                    client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert len(calls) == 1
    assert ledger.requests()[0]['state'] == 'unknown'
    assert ledger.totals()['conservative_accounted_usd'] == c.reservation_for('gpt-6.1-sol')/1e6
    assert b'fixture-secret' not in ledger.path.read_bytes()


@pytest.mark.parametrize('valid', [True, False])
def test_usage_includes_hidden_reasoning_and_invalid_output_is_paid(tmp_path, valid):
    ledger, items, _ = setup(tmp_path)
    bodies = []
    def handler(request):
        body = json.loads(request.content); bodies.append(body)
        if request.url.path.endswith('input_tokens'):
            return httpx.Response(200, json={'input_tokens': 1000})
        return httpx.Response(200, json={'id': 'fixture', 'model': body['model'], 'status': 'completed',
            'service_tier': 'default', 'usage': {'input_tokens': 1000, 'output_tokens': 2000,
            'input_tokens_details': {'cached_tokens': 100}, 'output_tokens_details': {'reasoning_tokens': 1900}},
            'output': [{'type': 'message', 'content': [{'type': 'output_text',
                         'text': json.dumps(annotation()) if valid else 'invalid'}]}]})
    c.cloud_one(tmp_path, ledger, items[0], 'gpt-6.1-sol', 'fixture-secret',
                client=httpx.Client(transport=httpx.MockTransport(handler)))
    row = ledger.requests()[0]
    assert row['state'] == ('complete' if valid else 'invalid')
    assert row['estimate'] == 21810 and row['accounted'] == 30000
    assert bodies[-1]['reasoning'] == {'effort': 'medium', 'mode': 'standard'}
    assert bodies[-1]['service_tier'] == 'default' and bodies[-1]['store'] is False
    assert 'human_reference' not in json.dumps(bodies)
    assert 'Visible at 1s' not in json.dumps(bodies)
    summary = c.report(tmp_path, ledger)
    assert summary['models']['gpt-6.1-sol']['human_label_agreement'] == (1 if valid else 0)
    assert summary['models']['gpt-6.1-sol']['valid_output_reference_coverage'] == (1 if valid else 0)
    assert (tmp_path/'comparisons'/c.AUTHORIZATION/'cost-ledger.csv').exists()


def test_mutated_frame_cannot_leave_machine(tmp_path):
    ledger, items, _ = setup(tmp_path)
    (tmp_path/'frame.jpg').write_bytes(b'changed')
    with pytest.raises(ValueError, match='nothing sent'):
        c.cloud_one(tmp_path, ledger, items[0], 'gpt-6.1-sol', 'fixture-secret')
    assert not ledger.requests()


def test_too_large_input_prevents_generation(tmp_path):
    ledger, items, _ = setup(tmp_path); calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'input_tokens': c.MAX_INPUT+1})
    c.cloud_one(tmp_path, ledger, items[0], 'gpt-6-astra', 'fixture-secret',
                client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert len(calls) == 1 and ledger.requests()[0]['state'] == 'blocked_input_limit'


def test_coarse_agreement_excludes_unknown_reference_but_counts_missing_prediction():
    ref = {'intervals': [{'start': 0, 'end': 3, 'label': 'grooming'}, {'start': 3, 'end': 6, 'label': 'unclear'}]}
    pred = {'intervals': [{'start': 1, 'end': 3, 'label': 'stationary'}]}
    assert c.agreement(ref, pred) == {'reference_seconds': 3, 'matched_seconds': 2, 'agreement': .666667}
    assert c.agreement(ref, {'intervals': []})['agreement'] == 0


@pytest.mark.parametrize('split,expected', [(None, 22210),
    ({'ttl_30m_tokens': 600, 'ttl_12h_tokens': 200}, 22710)])
def test_cache_writes_replace_input_rate_without_double_charging(split, expected):
    usage = {'input_tokens': 1000, 'output_tokens': 2000,
             'input_tokens_details': {'cached_tokens': 100, 'cache_write_tokens': 800}}
    if split:
        usage['input_tokens_details']['cache_write_tokens_details'] = split
    assert c.estimate_usage(usage, 'gpt-6.1-sol') == expected


@pytest.mark.parametrize('details', [
    {'cached_tokens': 500, 'cache_write_tokens': 600},
    {'cache_write_tokens': 800, 'cache_write_tokens_details': {'ttl_30m_tokens': 400}},
    {'cache_write_tokens': True},
])
def test_invalid_cache_breakdown_is_not_settled(details):
    with pytest.raises(ValueError):
        c.estimate_usage({'input_tokens': 1000, 'output_tokens': 2, 'input_tokens_details': details}, 'gpt-6.1-sol')


def test_offline_reconciliation_preserves_reservation_and_usage(tmp_path):
    ledger, _, _ = setup(tmp_path)
    ident = ledger.reserve('0', 'gpt-6.1-sol', c.reservation_for('gpt-6.1-sol'))
    with pytest.raises(ValueError, match='dispatch'):
        ledger.reconcile_estimates()
    usage = {'input_tokens': 1000, 'output_tokens': 2000,
             'input_tokens_details': {'cached_tokens': 100, 'cache_write_tokens': 800}}
    ledger.finish(ident, 'complete', {'usage': usage}, accounted=30000, estimate=21810)
    assert ledger.reconcile_estimates() == 1
    row = ledger.requests()[0]
    assert row['estimate'] == 22210 and row['accounted'] == 30000
    assert row['body']['usage'] == usage
    assert row['body']['accounting_revisions'][0]['previous_estimate_micros'] == 21810
    assert ledger.reconcile_estimates() == 0
