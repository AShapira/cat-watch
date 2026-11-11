"""Render the completed local cropped campaign; never sends inference requests."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import shutil
from zoneinfo import ZoneInfo


def labels(ann):
    return sorted({i['label'] for i in (ann or {}).get('intervals',[])})


def timeline(ann):
    return '; '.join(f"{i['start']:.1f}–{i['end']:.1f}s {i['label']}" for i in (ann or {}).get('intervals',[])) or 'No usable proposal'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('/home/alex/.local/share/cat-watch/data/learning'))
    parser.add_argument('--out',type=Path,default=Path('outputs/cropped-care-sol-20261109'))
    args=parser.parse_args();out=args.out.resolve();out.mkdir(exist_ok=True,parents=True)
    source=args.root/'campaigns/2026-11-09-cropped-care-sol'
    result=json.loads((source/'results.json').read_text());manifest=json.loads((source/'manifest.json').read_text())
    requests=json.loads((source/'requests.json').read_text());items=result['items'];cost=result['totals']
    if any(i['state'] in ('pending','sending') for i in items):raise ValueError('Wait for the batch to settle before producing its completion report')
    for name in ['results.json','manifest.json','requests.json','model-exposure.json']:
        if (source/name).exists():shutil.copy2(source/name,out/name)
    shutil.copytree(source/'previews',out/'previews',dirs_exist_ok=True)
    areas={}
    for area in ['water_fountain','eating_pad','litter_box']:
        subset=[i for i in items if i['target']==area]
        areas[area]={'clips':len(subset),'valid':sum(bool(i['annotation']) for i in subset),
            'label_clip_counts':dict(Counter(label for i in subset for label in labels(i['annotation']))),
            'quality_clip_counts':dict(Counter(q for i in subset for q in (i['annotation'] or {}).get('quality',[]))),
            'overlap_groups':len({i['episode_key'] for i in subset}),
            'sampled_seconds':round(sum(i['duration'] for i in subset),3)}
    paired=[i for i in items if i['annotation'] and i['local_prediction']]
    disagreements=[i for i in paired if labels(i['annotation'])!=labels(i['local_prediction'])]
    qwen_drinking=[i for i in paired if 'drinking' in labels(i['local_prediction'])]
    merged=[]
    for a,b in sorted((i['start'],i['start']+i['duration']) for i in items):
        if merged and a<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],b)
        else:merged.append([a,b])
    summary={'campaign':result['campaign'],'updated_at':result['updated_at'],'model':'gpt-6.1-sol',
        'states':result['states'],'areas':areas,'totals':cost,'clips':len(items),
        'timestamped_frames':sum(len(i['frames']) for i in manifest['items']),
        'sampled_seconds':round(sum(i['duration'] for i in items),3),
        'unique_camera_seconds':round(sum(b-a for a,b in merged),3),
        'first_clip_utc':datetime.fromtimestamp(min(i['start'] for i in items),timezone.utc).isoformat(),
        'last_clip_end_utc':datetime.fromtimestamp(max(i['start']+i['duration'] for i in items),timezone.utc).isoformat(),
        'source_groups':len({i['group_key'] for i in items}),
        'overlap_groups':len({i['episode_key'] for i in items}),
        'paired_qwen_clips':len(paired),'different_label_sets':len(disagreements),
        'qwen_drinking_comparison':[{'clip_id':i['clip_id'],'sol_labels':labels(i['annotation']),
                                    'qwen_labels':labels(i['local_prediction'])} for i in qwen_drinking],
        'measured_accuracy':None,'human_reviews_submitted':0}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    by_id={i['clip_id']:i for i in items}
    columns=['clip_id','area','start_utc','state','model','input_tokens','counted_input_tokens','output_tokens',
             'cached_tokens','reasoning_tokens','estimate_usd','conservative_exposure_usd','reserved_usd']
    with (out/'cost-ledger.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader()
        for r in requests:
            i=by_id[r['clip_id']];b=r['body'];u=b.get('usage') or {}
            writer.writerow({'clip_id':r['clip_id'],'area':i['target'],
                'start_utc':datetime.fromtimestamp(i['start'],timezone.utc).isoformat(),'state':r['state'],
                'model':r['model'],'input_tokens':u.get('input_tokens'),'counted_input_tokens':b.get('counted_input_tokens'),
                'output_tokens':u.get('output_tokens'),'cached_tokens':u.get('input_tokens_details',{}).get('cached_tokens'),
                'reasoning_tokens':u.get('output_tokens_details',{}).get('reasoning_tokens'),
                'estimate_usd':f"{(r['estimate'] or 0)/1e6:.6f}",'conservative_exposure_usd':f"{r['accounted']/1e6:.6f}",
                'reserved_usd':f"{r['reservation']/1e6:.6f}"})
    names={'water_fountain':'Drinking fountain','eating_pad':'Eating area','litter_box':'Litter box'}
    lines=['# Cropped cat activity — Sol classification report','',
        '9 November 2026. All displayed times use Asia/Jerusalem (UTC+02:00).','',
        '**These are unconfirmed model suggestions, not human labels or measured accuracy.**','',
        f"Completed {sum(i['state']=='complete' for i in items)} of {len(items)} clips using GPT-6.1 Sol / medium. "
        f"The batch contains {summary['timestamped_frames']} timestamped native cropped images, "
        f"covering {summary['sampled_seconds']:.1f} seconds across all three views.",'',
        '| Area | Clips | Model labels (clips containing each label) | Overlap-linked groups |',
        '| --- | ---: | --- | ---: |']
    for area,a in areas.items():
        counts=', '.join(f'{k}: {v}' for k,v in sorted(a['label_clip_counts'].items()))
        lines.append(f"| {names[area]} | {a['clips']} | {counts} | {a['overlap_groups']} |")
    lines+=['','A clip may contain several labels; label counts in a row therefore overlap.']
    lines+=['','## Fountain findings','',
        f"Sol proposed drinking in **{areas['water_fountain']['label_clip_counts'].get('drinking',0)} of {areas['water_fountain']['clips']}** selected fountain clips. "
        'This selected sample does not establish that the cat did not drink elsewhere or at another time.','',
        'The tightened 180 × 202 crop excludes the food bowls and retains the white backing. '
        'Several activity clips show only part of the cat while the head/mouth is outside the crop. '
        'Those views cannot establish drinking or eating from body position alone. '
        'The white backing is visible, but this is not a controlled before/after test of its benefit.','']
    for i in qwen_drinking:
        lines.append(f"- Saved Qwen suggested drinking for `{i['clip_id'][:12]}`; Sol returned **{', '.join(labels(i['annotation']))}**. "
                     'This is model disagreement requiring review, not an independently proven false positive.')
    lines+=['','## Eating and litter-box findings','']
    for area in ['eating_pad','litter_box']:
        a=areas[area]
        lines.append(f"- **{names[area]}:** "+', '.join(f'{k} in {v} clip(s)' for k,v in sorted(a['label_clip_counts'].items()))+'.')
    lines+=['','Litter-box presence or posture cannot establish successful elimination. '
            'Cropping and the covered box can obscure the relevant action.','',
        '## Coverage, selection and comparison','',
        'The batch deliberately samples activity during the food-area and litter visits, '
        'plus two empty-fountain controls. It is not a random prevalence sample. '
        'All clips were recorded after the tightened crop took effect; no old archived data were restored.','',
        f"The selected intervals span {summary['first_clip_utc']} to {summary['last_clip_end_utc']}, "
        f"but contain only **{summary['unique_camera_seconds']:.1f} seconds of distinct camera time**. "
        'They do not provide continuous overnight coverage or missed-event recall.','',
        f"There are {summary['source_groups']} original source-group names and {summary['overlap_groups']} overlap-connected groups "
        'across the selected clips and their retained context. Different crops can describe the same event, '
        'and short capture gaps can split a continuous visit. These counts must not be presented as independent confirmed behavior episodes.','',
        f"Saved Qwen proposals were available for {len(paired)} clips; {len(disagreements)} have different fine-grained label sets from Sol. "
        'This is agreement between models, not accuracy against ground truth.','',
        'The API received 32 native JPEG samples per clip, not continuous video or audio. '
        'Brief lapping between samples and out-of-crop actions can remain unresolved. '
        'Capture timestamps are recorder estimates; relative frame times follow the encoded video cadence. '
        'Human review and a clear positive drinking example are still needed to evaluate drinking recognition.','',
        '## Cost','',
        f"- Authorized maximum: **$20.00**, one non-renewing campaign.",
        '- Whole-batch worst-case reservation at preparation: **$3.317760**.',
        f"- Usage-based inference estimate: **${cost['inference_estimate_usd']:.6f}**.",
        f"- Conservative accounted exposure, including token-count allowance: **${cost['conservative_accounted_usd']:.6f}**.",
        f"- Unused authorized ceiling: **${cost['remaining_authorized_usd']:.6f}**; no additional batch was dispatched.",
        f"- Unknown/in-flight requests: **{cost['unknown_or_in_flight']}**. No automatic retries.",'',
        'The batch made 18 classification requests and 18 matching token-count requests.','',
        'These figures are token-rate estimates and conservative accounting, not an invoice. '
        'Rates were checked against [official pricing](https://developers.openai.com/api/docs/pricing); '
        'the model supports image input, so this task used timestamped crops '
        '([model documentation](https://developers.openai.com/api/docs/models/gpt-6.1-sol)).','',
        '## All clips and classifications','',
        'The cropped video is the same view used for classification. Food previews add one black bottom row for compatible playback.','',
        '| # | Local date/time | Area | Sol timeline | Saved Qwen labels | Quality | Clip |',
        '| ---: | --- | --- | --- | --- | --- | --- |']
    gallery=[]
    for n,i in enumerate(items,1):
        local=datetime.fromtimestamp(i['start'],ZoneInfo('Asia/Jerusalem')).strftime('%d Nov %H:%M:%S')
        preview=out/'previews'/f"{i['clip_id']}.mp4";ann=i['annotation'] or {}
        quality=', '.join(ann.get('quality',[])) or '—';sol=timeline(ann)
        qwen=', '.join(labels(i['local_prediction'])) or 'Pending/not available at preparation'
        lines.append(f"| {n} | {local} | {names[i['target']]} | {sol} | {qwen} | {quality} | [Watch]({preview}) |")
        details=[]
        for interval in ann.get('intervals',[]):
            details.append(f"<li><b>{html.escape(interval['label'])} {interval['start']:.1f}–{interval['end']:.1f}s</b>: "
                f"{html.escape(interval.get('evidence',''))} {html.escape(interval.get('uncertainty',''))}</li>")
        gallery.append(f'<article><h3>{n}. {html.escape(names[i["target"]])} · {local}</h3>'
                       f'<video controls preload="metadata" src="previews/{i["clip_id"]}.mp4"></video>'
                       f'<p><b>Sol:</b> {html.escape(sol)}</p><p><b>Saved Qwen:</b> {html.escape(qwen)}</p>'
                       f'<p>Quality: {html.escape(quality)}</p><ul>{"".join(details)}</ul></article>')
    lines+=['','## Evidence and operational status','',
        f"Manifest fingerprint: `{result['fingerprint']}`.",'',
        '[Video gallery](report.html) · [Machine-readable results](results.json) · '
        '[Summary](summary.json) · [Cost ledger](cost-ledger.csv) · [Exposure provenance](model-exposure.json)','',
        'No human reviews or training were submitted. The display-managed recorder runs independently; '
        'its final health and training checks are saved in `after.json`. Exposure metadata marks these '
        'previews as assisted; related episodes require exclusion from later blind evaluation.']
    if (out/'after.json').exists():
        after=json.loads((out/'after.json').read_text());h=after['health'];cfg=after['learning']['config']
        lines+=['',f"Final check at {after['checked_at']}: camera **{h['camera']}**, detector **{h['detector']}**, "
                f"continuous monitoring **{cfg['continuous']}**, training **{cfg['training']}**, "
                f"pause_training **{after['pause_training']}**, and deployment training lock **{h['performance']['training_locked']}**. "
                f"The current recorder's capture-gap counter is {h['capture_gaps']}; it resets on restart and is not an all-night coverage measure.",'',
                '[Open monitoring dashboard](http://127.0.0.1:8765)']
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    html_doc='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cat activity — Sol crop review</title><style>body{font:16px/1.5 system-ui;max-width:1200px;margin:32px auto;padding:0 18px;background:#f6f7f5;color:#172c23}h1,h2{line-height:1.2}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}article{background:white;border:1px solid #d7dfd9;border-radius:12px;padding:18px}video{width:100%;height:285px;object-fit:contain;background:#171c19;border-radius:8px}li{font-size:14px;margin-bottom:8px}.notice{padding:16px;background:#fff3d5;border-radius:8px}a{color:#146449}</style>
<h1>Cat activity — Sol crop review</h1><p>9 November 2026 · Times: Asia/Jerusalem · Cropped views only</p>
<p class="notice">Unconfirmed model suggestions. These clips do not measure accuracy or prove successful drinking or elimination.</p>'''
    html_doc+=f'<p>{len(items)} clips · inference estimate ${cost["inference_estimate_usd"]:.4f} · conservative exposure ${cost["conservative_accounted_usd"]:.4f} / $20 authorized</p>'
    html_doc+='<p><a href="report.md">Full report</a> · <a href="results.json">Structured results</a> · <a href="cost-ledger.csv">Cost ledger</a></p><main>'+''.join(gallery)+'</main></html>'
    (out/'report.html').write_text(html_doc)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
