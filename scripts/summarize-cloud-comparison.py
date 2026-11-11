"""Read saved comparison results and write a private, human-readable analysis.

No API calls, model inference, or production-label changes occur here.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path


def label_sequence(annotation):
    if not annotation:
        return []
    result = []
    for interval in annotation['intervals']:
        label = interval['label']
        if not result or result[-1] != label:
            result.append(label)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    result = json.loads((args.folder/'comparison.json').read_text())
    items = result['items']; models = list(result['models'])
    if result['totals']['unknown_or_in_flight']:
        raise ValueError('Resolve in-flight or unknown requests before final analysis')
    counts, coverage = {}, {}
    for model in models:
        labels = Counter(); seconds = Counter(); duration = 0
        for item in items:
            response = item['models'].get(model)
            if not response:
                continue
            duration += item['duration']
            annotation = response.get('annotation')
            intervals = (annotation or {}).get('intervals', [])
            labels.update(set(i['label'] for i in intervals))
            for i in intervals:
                seconds['unclear' if i['label'] == 'unclear' else 'determinate'] += i['end']-i['start']
        counts[model] = dict(labels)
        coverage[model] = {'attempted_clip_seconds': round(duration, 6),
            'determinate_seconds': round(seconds['determinate'], 6),
            'unclear_seconds': round(seconds['unclear'], 6),
            'unlabeled_or_invalid_seconds': round(max(0, duration-sum(seconds.values())), 6)}
    paired = []
    for n, item in enumerate(items, 1):
        sol = item['models'].get('gpt-6.1-sol', {}).get('annotation')
        astra = item['models'].get('gpt-6-astra', {}).get('annotation')
        if sol and astra:
            paired.append({'clip_number': n, 'same_subject': sol['subject'] == astra['subject'],
                           'same_label_sequence': label_sequence(sol) == label_sequence(astra)})
    findings = {'created_at': datetime.now(timezone.utc).isoformat(),
        'totals': result['totals'], 'models': result['models'],
        'clips_with_labels': counts, 'coverage': coverage,
        'sol_astra_paired_clips': len(paired),
        'sol_astra_same_subject': sum(p['same_subject'] for p in paired),
        'sol_astra_same_label_sequence': sum(p['same_label_sequence'] for p in paired),
        'note': 'Label-sequence agreement ignores interval boundary differences and is not an accuracy measurement.'}
    lines = ['# What the approved cloud comparison found', '', 'Generated: '+findings['created_at'], '',
        'The main finding is a disagreement about evidence for eating. Qwen proposed eating in '
        f"{counts['qwen3.5:9b'].get('eating', 0)} of 10 clips; Sol confirmed it in "
        f"{counts['gpt-6.1-sol'].get('eating', 0)}. On the selected hard subset, Astra confirmed it in "
        f"{counts['gpt-6-astra'].get('eating', 0)} of {len(paired)} clips.", '',
        '**This does not establish which model is correct.** Only one clip has an assisted human reference; '
        'there are no independent human references in this cohort or any human references in the Astra subset.', '',
        '| Model and settings | Valid responses | Mean request time | Estimated inference cost |',
        '| --- | --- | --- | --- |']
    names = {'qwen3.5:9b': 'Qwen3.5-9B Q4_K_M, thinking off',
             'gpt-6.1-sol': 'GPT-6.1 Sol, medium', 'gpt-6-astra': 'GPT-6 Astra, high'}
    for m, value in result['models'].items():
        lines.append(f"| {names[m]} | {value['valid']}/{value['attempts']} | {value['mean_seconds']:.3f}s | ${value['inference_estimate_usd']:.6f} |")
    total = result['totals']
    lines += ['', f"Total estimated inference: **${total['inference_estimate_usd']:.6f}**, including reported cache writes and reasoning tokens. "
        f"Conservative budget exposure: **${total['conservative_accounted_usd']:.6f}**; remaining authorization **${total['remaining_authorized_usd']:.6f}** of $20.",
        'The exposure includes a token-count allowance and worst input rates. It is not a claim that the provider charged that amount. '
        'The estimate has not been reconciled against an invoice or the account credit balance. Local electricity/hardware costs are excluded.', '',
        '[Per-request token and cost CSV](cost-ledger.csv) · [Full model explanations](comparison.md)', '',
        '## What agrees, and what differs', '',
        f"Sol and Astra produced the same subject assessment in {findings['sol_astra_same_subject']}/{len(paired)} shared clips and "
        f"the same ordered behavior-label sequence in {findings['sol_astra_same_label_sequence']}/{len(paired)}. "
        'Their interval boundaries sometimes differ. Matching sequences do not establish correctness.', '',
        'Qwen often cited head position near a bowl as evidence for eating, despite the shared instruction that proximity and head position alone are insufficient. '
        'The cloud models generally abstained when they could not distinguish chewing, lapping, grooming or inspection. '
        'These are comparisons of the saved model outputs, not a separate visual ground-truth assessment.', '',
        'Astra was selected for disagreement/invalid output, so its five clips are not a random sample. '
        'The larger cloud models, different reasoning settings, and serving backends are confounded; this is a comparison of the chosen operating configurations.', '',
        '## Labels for each clip', '',
        'Read arrows as label order; exact timestamps and evidence are in the full report.', '',
        '| Clip | Qwen | Sol / medium | Astra / high |', '| --- | --- | --- | --- |']
    for n, item in enumerate(items, 1):
        labels = []
        for model in models:
            response = item['models'].get(model)
            if not response:
                labels.append('Not selected')
            elif not response.get('annotation'):
                labels.append('Invalid/unavailable response')
            else:
                labels.append(' → '.join(label_sequence(response['annotation'])))
        link = f"[{n} · {item['duration']:.3f}s](http://127.0.0.1:8765/api/learning/clips/{item['clip_id']}/video)"
        lines.append('| '+link+' | '+' | '.join(labels)+' |')
    lines += ['', '## How much the models were willing to label', '',
        'Determinate means a label other than unclear, including no-cat. Coverage is not correctness. '
        'Gaps and invalid responses remain unlabelled; they are not converted into negative examples.', '',
        '| Model | Attempted seconds | Determinate | Unclear | Unlabelled / invalid |', '| --- | --- | --- | --- | --- |']
    for m, v in coverage.items():
        lines.append(f"| {m} | {v['attempted_clip_seconds']:.2f}s | {v['determinate_seconds']:.2f}s | {v['unclear_seconds']:.2f}s | {v['unlabeled_or_invalid_seconds']:.2f}s |")
    lines += ['', '## Useful human decisions next', '',
        '1. **Clips 5, 7 or 10:** is chewing/food consumption actually visible, or should the action remain unclear? These challenge Qwen’s eating rule.',
        '2. **Clip 9:** where does the initial stationary/repositioning phase end? Qwen labels the whole clip as eating even though its own explanation says “from 2.0s onwards.”',
        '3. **Clip 4:** no cat is visible according to both cloud models; Qwen marks uncertain presence. Resolve this using the project’s visible-subject definition and retain the occlusion flag.', '',
        'No answers have been filled in, no production prediction or human decision has been overwritten, and none of these proposals has entered training.', '',
        '## Practical conclusion', '',
        'Keep the local service for inexpensive first-pass proposals. The pilot supports testing Sol as a selective reviewer of questionable care labels. '
        'Astra supplied similar labels at higher cost and latency on this small subset; this pilot does not demonstrate a quality gain from using it routinely. '
        'Human adjudication of the eating disagreements is needed before using them to train or promote a behavior model.', '',
        'This approved one-shot batch is finished. No automatic new cloud batches or retries are scheduled.', '']
    (args.folder/'analysis.md').write_text('\n'.join(lines))
    (args.folder/'analysis-summary.json').write_text(json.dumps(findings, indent=2)+'\n')
    print(json.dumps(findings, indent=2))


if __name__ == '__main__':
    main()
