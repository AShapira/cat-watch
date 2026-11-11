"""Summarize saved campaign outputs offline; never dispatches or confirms a label."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlencode


def coarse(label):
    if label.startswith('litter_'):
        return 'litter_activity'
    return label if label in ('eating', 'drinking', 'litter_activity', 'no_cat', 'unclear') else 'other_activity'


def labels(annotation):
    return {coarse(i['label']) for i in (annotation or {}).get('intervals', []) if i['end'] > i['start']}


def analyze(result, requests):
    items = result['items']; complete = [i for i in items if i['state'] == 'complete']
    model_counts = {}
    for model, key in [('Sol', 'annotation'), ('saved_Qwen', 'local_prediction')]:
        usable = [i for i in complete if i.get(key)]
        counts = Counter(label for i in usable for label in labels(i[key]))
        groups = {label: len({i['group_key'] for i in usable if label in labels(i[key])}) for label in counts}
        model_counts[model] = {'annotations': len(usable), 'clips_with_label': dict(counts), 'source_groups_with_label': groups}
    paired = [i for i in complete if i.get('local_prediction')]
    paired_counts = {model: dict(Counter(label for i in paired for label in labels(i[key])))
                     for model, key in [('Sol', 'annotation'), ('saved_Qwen', 'local_prediction')]}
    exact = sum(labels(i['annotation']) == labels(i['local_prediction']) for i in paired)
    matched = sum((i.get('local_agreement') or {}).get('matched_seconds', 0) for i in paired)
    denominator = sum((i.get('local_agreement') or {}).get('reference_seconds', 0) for i in paired)
    token_totals = Counter()
    for row in requests:
        usage = row['body'].get('usage', {})
        for name in ('input_tokens', 'output_tokens'):
            token_totals[name] += usage.get(name, 0)
        token_totals['counted_input_tokens'] += row['body'].get('counted_input_tokens') or 0
        details = usage.get('input_tokens_details') or {}
        for name in ('cached_tokens', 'cache_write_tokens'):
            token_totals[name] += details.get(name, 0)
        token_totals['reasoning_tokens'] += (usage.get('output_tokens_details') or {}).get('reasoning_tokens', 0)
    review_groups = defaultdict(set)
    for i in complete:
        for label in labels(i['annotation']):
            if label in ('drinking', 'litter_activity'):
                review_groups[label].add(i['group_key'])
    return {'updated_at': datetime.now(timezone.utc).isoformat(), 'states': result['states'],
            'clips': len(items), 'valid_proposals': len(complete), 'model_counts': model_counts,
            'paired_local_proposals': len(paired), 'paired_model_counts': paired_counts, 'same_coarse_label_set': exact,
            'duration_agreement_with_sol_excluding_sol_unclear': round(matched/denominator, 4) if denominator else None,
            'comparison_reference_seconds': round(denominator, 3),
            'training_labels_created_by_runner': 0, 'independent_accuracy_reference_clips': 0,
            'campaign_inference_estimate_usd': round(sum(r['estimate'] or 0 for r in requests)/1e6, 6),
            'campaign_conservative_accounted_usd': round(sum(r['accounted'] for r in requests)/1e6, 6),
            'all_authorized_batches': result['totals'], 'tokens': dict(token_totals),
            'candidate_care_source_groups': {k: len(v) for k, v in review_groups.items()},
            'limitations': ['Model agreement is not accuracy.', 'Saved Qwen proposals used earlier sampling and may not match the 32-frame Sol protocol.',
                           'Source groups and clips are not confirmed independent positive episodes.', 'Reasoning tokens are already part of output tokens.']}


def write(folder):
    result = json.loads((folder/'results.json').read_text())
    requests = json.loads((folder/'requests.json').read_text())
    summary = analyze(result, requests)
    (folder/'analysis.json').write_text(json.dumps(summary, indent=2)+'\n')
    with (folder/'cost-ledger.csv').open('w', newline='') as f:
        columns = ['clip_id', 'model', 'state', 'created_utc', 'input_tokens', 'cached_tokens', 'cache_write_tokens',
                   'output_tokens', 'reasoning_tokens', 'counted_input_tokens', 'inference_estimate_usd', 'conservative_accounted_usd', 'response_id']
        writer = csv.DictWriter(f, fieldnames=columns); writer.writeheader()
        for r in requests:
            b = r['body']; u = b.get('usage') or {}; d = u.get('input_tokens_details') or {}
            writer.writerow({'clip_id': r['clip_id'], 'model': r['model'], 'state': r['state'],
                'created_utc': datetime.fromtimestamp(r['created'], timezone.utc).isoformat(),
                'input_tokens': u.get('input_tokens'), 'cached_tokens': d.get('cached_tokens'), 'cache_write_tokens': d.get('cache_write_tokens'),
                'output_tokens': u.get('output_tokens'), 'reasoning_tokens': (u.get('output_tokens_details') or {}).get('reasoning_tokens'),
                'counted_input_tokens': b.get('counted_input_tokens'),
                'inference_estimate_usd': r['estimate']/1e6 if r['estimate'] is not None else '',
                'conservative_accounted_usd': r['accounted']/1e6, 'response_id': b.get('response_id')})
    lines = ['# Focused care labeling: Sol and saved local proposals', '', 'Updated: '+summary['updated_at'], '',
             '**These are unconfirmed model proposals, not measured behavior accuracy.**', '',
             f"Valid Sol proposals: **{summary['valid_proposals']} / {summary['clips']}**. States: `{summary['states']}`.",
             f"This batch: estimated inference **${summary['campaign_inference_estimate_usd']:.6f}**; conservative exposure **${summary['campaign_conservative_accounted_usd']:.6f}**.",
             f"All authorized batches: conservative exposure **${summary['all_authorized_batches']['conservative_accounted_usd']:.6f} / $20**; remaining **${summary['all_authorized_batches']['remaining_authorized_usd']:.6f}**.",
             'Exposure includes the token-count allowance and conservative input rates. These figures are not provider invoices.', '',
             '| Proposed coarse behavior | Sol: all 100 clips | Sol: paired subset | Saved Qwen: paired subset |', '| --- | ---: | ---: | ---: |']
    for label in ('drinking', 'litter_activity', 'eating', 'other_activity', 'no_cat', 'unclear'):
        lines.append(f"| {label} | {summary['model_counts']['Sol']['clips_with_label'].get(label, 0)} | {summary['paired_model_counts']['Sol'].get(label, 0)} | {summary['paired_model_counts']['saved_Qwen'].get(label, 0)} |")
    lines += ['', f"Paired columns use exactly the same {summary['paired_local_proposals']} clips with saved Qwen proposals.", 'A clip can contain several behaviors, so columns need not sum to the clip count.',
              f"The two models have the same coarse label set on {summary['same_coarse_label_set']} / {summary['paired_local_proposals']} paired clips.",
              'This is diagnostic agreement. There is no independent human ground truth for this selected batch, and the saved Qwen sampling conditions differ.', '',
              '## Review priorities', '',
              'Review proposed drinking/litter actions first, checking visible action rather than area proximity. Use nearby non-care examples as negatives. Leave hidden behavior unclear.', '',
              '| Clip | Area | Sol proposal | Saved local proposal | Review |', '| --- | --- | --- | --- | --- |']
    def rank(i):
        care = labels(i.get('annotation')) & {'drinking', 'litter_activity'}
        disagreement = labels(i.get('annotation')) != labels(i.get('local_prediction'))
        return (not bool(care), not disagreement, -i['start'])
    for i in sorted(result['items'], key=rank):
        sl = ', '.join(sorted(labels(i.get('annotation')))) or i['state']
        ll = ', '.join(sorted(labels(i.get('local_prediction')))) or 'unavailable'
        lines.append(f"| {i['clip_id'][:12]} | {i['target']} | {sl} | {ll} | [Open](http://localhost:8767/?{urlencode({'campaign': result['campaign'], 'clip': i['clip_id']})}) |")
    (folder/'analysis.md').write_text('\n'.join(lines)+'\n')
    # A small starting queue helps the human adjudicate actual care/uncertainty
    # rather than spending the first session on many empty-camera negatives.
    first, groups = [], set()
    targets = sorted({i['target'] for i in result['items']})
    per_target = max(1, 10//len(targets))
    for target in targets:
        candidates = [i for i in items_for_review(result) if i['target'] == target]
        days = set()
        # Start across recording days before filling from the same day's visits.
        # Nearby timestamps can be different candidate keys within one true visit.
        for distinct_days in (True, False):
            for i in candidates:
                if sum(x['target'] == target for x in first) >= per_target:
                    break
                if i['group_key'] in groups or (distinct_days and i['day'] in days):
                    continue
                first.append(i); groups.add(i['group_key']); days.add(i['day'])
    review_lines = ['# Start here: ten human review decisions', '',
        'These are selected questions, not accepted labels. Watch the full local video, slow it down if useful, then accept, edit or mark unclear.',
        'For the fountain: is drinking visibly established, or only proximity/head position? For the litter box: what action is actually visible, and what is hidden?', '',
        'The starting list favors different recording days and source groups; candidate groups are not confirmed independent behavior episodes.', '',
        '| Date | Area | Proposed labels | Why selected | Review |', '| --- | --- | --- | --- | --- |']
    for i in first:
        proposed = ', '.join(sorted(labels(i['annotation'])))
        reason = 'Proposed care action' if labels(i['annotation']) & {'drinking', 'litter_activity'} else 'Cat/visit evidence needing a human decision' if 'unclear' in labels(i['annotation']) else 'Visible activity or useful negative'
        review_lines.append(f"| {i['day']} | {i['target']} | {proposed} | {reason} | [Open clip](http://localhost:8767/?{urlencode({'campaign': result['campaign'], 'clip': i['clip_id']})}) |")
    invalid = [i for i in result['items'] if i['state']=='invalid']
    if invalid:
        review_lines += ['', '## Clips without a usable Sol proposal', '',
                         'These requests failed local annotation validation and were not retried. Review the video manually or skip; a missing proposal is not a negative label.', '',
                         '| Date | Manual review |', '| --- | --- |']
        for i in invalid:
            review_lines.append(f"| {i['day']} | [Open clip](http://localhost:8767/?{urlencode({'campaign': result['campaign'], 'clip': i['clip_id']})}) |")
    (folder/'review-first.md').write_text('\n'.join(review_lines)+'\n')
    summary['suggested_first_review_clip_ids'] = [i['clip_id'] for i in first]
    (folder/'analysis.json').write_text(json.dumps(summary, indent=2)+'\n')
    return summary


def items_for_review(result):
    def priority(i):
        proposed = labels(i.get('annotation'))
        visible = i['selection'].get('fountain_cat_observations', i['selection'].get('cat_observations', 0)) > 0
        return (not bool(proposed & {'drinking', 'litter_activity'}), not ('unclear' in proposed and visible),
                not visible, -i['start'])
    return sorted((i for i in result['items'] if i['state'] == 'complete'), key=priority)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    print(json.dumps(write(args.folder), indent=2))
