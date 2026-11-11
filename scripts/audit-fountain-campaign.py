"""Reconcile a stopped fountain run locally; no API calls or label writes."""
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
import json
from pathlib import Path
import sqlite3
import statistics
import time

ROOT = Path('/data/learning')
CAMPAIGN = '2026-11-04-fountain-100'
FINGERPRINT = '900e180e988c5a13d1fe59e00f86d9e7b32c62c893bbb25e0f60a20af91fd4e4'


def db(path):
    connection = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA query_only=ON')
    return connection


def rounded(tokens, rate):
    return int((Decimal(tokens)*Decimal(rate)).to_integral_value(rounding=ROUND_CEILING))


def main():
    from catwatch.learning.contracts import digest
    from catwatch.learning.fountain import report
    folder = ROOT/'campaigns'/CAMPAIGN
    with db(ROOT/'cloud-comparison.sqlite3') as connection:
        auth = connection.execute('SELECT * FROM authorization WHERE id=?', (CAMPAIGN,)).fetchone()
        manifest = json.loads(auth['manifest'])
        assert auth['fingerprint'] == digest(manifest) == FINGERPRINT
        rows = [dict(r, body=json.loads(r['body'])) for r in connection.execute(
            'SELECT * FROM requests WHERE authorization=? ORDER BY created', (CAMPAIGN,))]
    assert rows and not any(r['state']=='sending' for r in rows), 'Wait for dispatch to stop'
    selected = {i['clip_id'] for i in manifest['items']}
    assert len(rows) <= 100 and len({r['clip_id'] for r in rows}) == len(rows)
    checks = 0
    for row in rows:
        assert row['clip_id'] in selected and row['model']=='gpt-6.1-sol'
        assert row['reservation']==75_360 and 0 <= row['accounted'] <= row['reservation']
        if row['state'] not in ('complete', 'invalid'):
            continue
        body = row['body']; usage = body['usage']; details = usage.get('input_tokens_details') or {}
        count, inputs, outputs = body['counted_input_tokens'], usage['input_tokens'], usage['output_tokens']
        assert 0 < count <= 6000 and 0 <= inputs <= 6000 and 0 <= outputs <= 1536
        cached, writes = details.get('cached_tokens', 0), details.get('cache_write_tokens', 0)
        split = details.get('cache_write_tokens_details')
        short, long = (writes, 0) if not split else (split.get('ttl_30m_tokens',0), split.get('ttl_12h_tokens',0))
        assert short+long==writes and inputs>=cached+writes
        estimate = rounded(inputs-cached-writes, '2')+rounded(cached, '.1')+rounded(short, '2.5')+rounded(long, '5')+rounded(outputs, '10')
        assert row['estimate']==estimate
        assert row['accounted']==rounded(count+inputs, '5')+rounded(outputs, '10')
        assert body['reasoning_effort']=='medium'
        checks += 1
    result = report(ROOT)
    assert result['totals']['conservative_accounted_usd'] <= 20
    with db(ROOT/'agent.sqlite3') as connection:
        audit = json.loads(connection.execute('SELECT body FROM metadata WHERE key=?', ('assisted_pool:'+CAMPAIGN,)).fetchone()[0])
        cfg = json.loads(connection.execute('SELECT body FROM settings WHERE id=1').fetchone()[0])
        reviewed = [r['id'] for r in connection.execute("SELECT id FROM clips WHERE decision IS NOT NULL AND decision!='null'")]
        dataset_count = connection.execute('SELECT COUNT(*) FROM datasets').fetchone()[0]
        model_count = connection.execute('SELECT COUNT(*) FROM models').fetchone()[0]
    started = min(r['created'] for r in rows)
    finished = max((datetime.fromisoformat(r['body']['finished_at']).timestamp() for r in rows if r['body'].get('finished_at')), default=started)
    with db(ROOT.parent/'catwatch.sqlite3') as connection:
        segments = [dict(r) for r in connection.execute('SELECT path,start,end FROM segments WHERE end>=? AND start<=? ORDER BY start', (started,finished))]
    elapsed = [r['body']['elapsed_seconds'] for r in rows if r['body'].get('elapsed_seconds') is not None]
    receipt = {'checked_at':datetime.now(timezone.utc).isoformat(), 'fingerprint':FINGERPRINT,
        'attempted_clips':len(rows), 'states':dict(Counter(r['state'] for r in rows)),
        'request_models':dict(Counter(r['model'] for r in rows)), 'independent_cost_checks':checks,
        'first_request_utc':datetime.fromtimestamp(started,timezone.utc).isoformat(),
        'last_response_utc':datetime.fromtimestamp(finished,timezone.utc).isoformat(),
        'request_elapsed_seconds':{'mean':round(statistics.mean(elapsed),3),'median':round(statistics.median(elapsed),3),'maximum':max(elapsed)} if elapsed else None,
        'totals':result['totals'], 'selected_human_reviews':len(selected.intersection(reviewed)),
        'all_human_reviews':len(reviewed), 'models':model_count, 'datasets':dataset_count, 'training':cfg.get('training'),
        'assisted_pool':{'created_at':audit['created_at'],'clips':len(audit['clips']),'partition_keys':len(audit['partitions']),
            'previous_splits':dict(Counter(c['split'] for c in audit['clips'])),
            'day_keys':sorted(p['key'] for p in audit['partitions'] if p['key'].startswith('day:'))},
        'recording_during_run':{'from_epoch':started,'to_epoch':finished,'registered_segments':len(segments),
            'last_registered_end':segments[-1]['end'] if segments else None,
            'maximum_internal_gap_seconds':round(max((b['start']-a['end'] for a,b in zip(segments,segments[1:])),default=0),3),
            'segments_with_existing_files':sum((ROOT.parent/s['path']).is_file() for s in segments)}}
    (folder/'requests.json').write_text(json.dumps(rows,indent=2)+'\n')
    (folder/'completion-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))


if __name__=='__main__':
    main()
