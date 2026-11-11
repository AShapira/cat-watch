"""Explicit, one-shot comparison. No scheduler and no API key in arguments or env."""
import argparse
import json
from pathlib import Path
import sys

import httpx

from .comparison import (AUTHORIZATION, POLICIES, ENDPOINT, Ledger, prepare,
                         local_one, cloud_one, choose_astra, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['prepare', 'local', 'cloud', 'report', 'reconcile'])
    args = parser.parse_args()
    root = Path('/data/learning')
    ledger = Ledger(root/'cloud-comparison.sqlite3')
    manifest = prepare(root, ledger)
    print(json.dumps({'authorization': AUTHORIZATION, 'stage': args.stage,
        'clips': len(manifest['items']), 'human_references': sum(bool(i['human_reference']) for i in manifest['items']),
        'frames': sum(len(i['frames']) for i in manifest['items']), 'expires_epoch': manifest['expires_epoch'],
        'totals': ledger.totals()}), flush=True)
    key = None
    try:
        if args.stage == 'reconcile':
            print(json.dumps({'offline_cost_corrections': ledger.reconcile_estimates()}), flush=True)
        if args.stage == 'local':
            for item in manifest['items']:
                local_one(root, ledger, item)
                print(json.dumps(report(root, ledger)), flush=True)
        if args.stage == 'cloud':
            # Abort on any unresolved previous outbound request, including process
            # termination after reservation. Rerunning must not spend around a fault.
            if any(r['model'] in POLICIES and r['state'] not in ('complete', 'invalid') for r in ledger.requests()):
                raise ValueError('Prior cloud request requires reconciliation before any more spending')
            rows = ledger.requests()
            if any(not any(r['clip_id'] == i['clip_id'] and r['model'] == 'qwen3.5:9b' for r in rows) for i in manifest['items']):
                raise ValueError('Run the paired local baseline first')
            key = json.loads(sys.stdin.readline()).get('api_key')
            if not isinstance(key, str) or not key.strip():
                raise ValueError('No API credential supplied')
            # Read-only authentication/model availability check sends no footage.
            with httpx.Client(timeout=30, trust_env=False, follow_redirects=False) as client:
                for model in POLICIES:
                    response = client.get(ENDPOINT+'/models/'+model, headers={'Authorization': 'Bearer '+key})
                    if response.status_code != 200:
                        raise ValueError(f'Model access check failed: {model}, HTTP {response.status_code}; no footage sent')
            for model in POLICIES:
                items = manifest['items'] if model == 'gpt-6.1-sol' else choose_astra(ledger)
                for item in items:
                    cloud_one(root, ledger, item, model, key)
                    print(json.dumps(report(root, ledger)), flush=True)
                    row = next(r for r in ledger.requests() if r['clip_id'] == item['clip_id'] and r['model'] == model)
                    if row['state'] not in ('complete', 'invalid'):
                        raise ValueError('Cloud request did not settle normally; stopped without retry')
    finally:
        key = None
        print(json.dumps(report(root, ledger)), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Do not emit request headers, provider payloads or exception reprs.
        print(json.dumps({'stopped': True, 'error_type': type(error).__name__,
                          'message': str(error) if isinstance(error, ValueError) else 'Operation failed; see durable ledger'}), flush=True)
        sys.exit(1)
