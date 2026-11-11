"""Reproducible, grouped local VideoMAE training; no implicit downloads."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import argparse
import json
import math
import os
from pathlib import Path
import random
import subprocess
import time

from .contracts import CARE, LABELS, canonical, coarse, digest, episode_keys, local_day
from .store import LearningStore

CHECKPOINT = 'MCG-NJU/videomae-base-finetuned-kinetics'
PREPROCESS = {'frames': 16, 'size': 224, 'window_seconds': 4, 'version': 1}


def components(clips):
    """Connect days, visits and shared sources BEFORE assigning any split."""
    parent = {}
    def find(k):
        parent.setdefault(k, k)
        if parent[k] != k:
            parent[k] = find(parent[k])
        return parent[k]
    def join(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[max(a, b)] = min(a, b)
    keys = {}
    for clip in clips:
        m = clip['manifest']
        k = [f"day:{clip['day']}", f"day:{local_day(clip['start']+clip['duration'])}",
             'group:'+clip['group_key'], 'video:'+m['video_hash']]
        k += ['source:'+h for h in m.get('source_hashes', [])]
        keys[clip['id']] = k
        for x in k:
            join(k[0], x)
    groups = defaultdict(list)
    for clip in clips:
        groups[find(keys[clip['id']][0])].append(clip)
    return [(members, sorted({k for c in members for k in keys[c['id']]})) for members in groups.values()]


def make_dataset(store):
    with store.db() as db:
        clips = [store.decode_clip(r) for r in db.execute('SELECT * FROM clips ORDER BY start,id')]
    groups = components(clips)
    episodes = episode_keys(clips)
    rows, held, assignments = [], [], {}
    # Split assignments survive subsequent datasets. Newly discovered cross-split
    # duplicates are quarantined, never silently shuffled into training.
    with store.db() as db:
        existing = {r['key']: r['split'] for r in db.execute('SELECT * FROM partitions')}
        for members, keys in groups:
            prior = {existing[k] for k in keys if k in existing}
            if len(prior) > 1:
                held.extend(c['id'] for c in members)
                continue
            split = next(iter(prior)) if prior else ('train' if int(digest(keys)[:8], 16) % 10 < 6 else
                                                     'validation' if int(digest(keys)[:8], 16) % 10 < 8 else 'test')
            for k in keys:
                db.execute('INSERT OR IGNORE INTO partitions VALUES (?,?)', (k, split))
            for c in members:
                assignments[c['id']] = split
                db.execute('UPDATE clips SET split=? WHERE id=?', (split, c['id']))
                ann = c['decision']
                if not ann or ann['subject'] not in ('single_cat', 'no_cat'):
                    continue
                if split != 'train' and not ann.get('independent'):
                    continue
                for interval in ann['intervals']:
                    label = coarse(interval['label'])
                    if label not in LABELS:
                        continue
                    a = interval['start']
                    while a < interval['end']:
                        b = min(a+4, interval['end'])
                        if b-a >= 1:
                            rows.append({'clip_id': c['id'], 'version': c['version'], 'group_key': episodes[c['id']],
                                         'start': a, 'end': b, 'label': label, 'split': split,
                                         'source': 'human', 'weight': 1., 'video_hash': c['manifest']['video_hash']})
                        a = b
        if not rows:
            raise ValueError('Confirm timed behaviors first; proposals are not evaluation labels')
        # Do not let many overlapping exports of one visit dominate optimization.
        repetitions = Counter((r['group_key'], r['label']) for r in rows if r['split'] == 'train')
        for r in rows:
            if r['split'] == 'train':
                r['weight'] = 1/repetitions[(r['group_key'], r['label'])]
        body = {'schema': 1, 'preprocess': PREPROCESS, 'checkpoint': CHECKPOINT,
                'license': 'CC-BY-NC-4.0', 'seed': 17, 'rows': rows, 'quarantined': held,
                'label_versions': {c['id']: c['version'] for c in clips if c['decision'] and c['id'] in assignments},
                'splits': dict(Counter(r['split'] for r in rows))}
        ident = digest(body)
        db.execute('INSERT OR IGNORE INTO datasets VALUES (?,?,?)', (ident, time.time(), canonical(body)))
        db.executemany('UPDATE clips SET pinned=1 WHERE id=?', [(r['clip_id'],) for r in rows])
    target = store.root/'datasets'/f'{ident}.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text(canonical(body))
    return {'id': ident, **body}


def episode_metrics(samples, thresholds=None):
    """One vote per independent episode/true behavior, not per adjacent window."""
    thresholds = thresholds or {label: .5 for label in LABELS}
    grouped = defaultdict(list)
    for sample in samples:
        grouped[(sample['group_key'], sample['label'])].append(sample['probabilities'])
    confusion = {label: Counter() for label in LABELS}
    votes = []
    for (group, truth), vectors in grouped.items():
        scores = [sum(v[i] for v in vectors)/len(vectors) for i in range(len(LABELS))]
        index = max(range(len(LABELS)), key=scores.__getitem__)
        predicted = LABELS[index] if scores[index] >= thresholds.get(LABELS[index], 1) else 'unclear'
        confusion[truth][predicted] += 1
        votes.append((group, truth, predicted))
    result = {}
    for label in LABELS:
        positive = {g for g, truth, _ in votes if truth == label}
        negative = {g for g, _, _ in votes} - positive
        true_hits = {g for g, truth, pred in votes if truth == pred == label}
        # Count false claims once per episode even if it has several other actions.
        false_hits = {g for g, truth, pred in votes if truth != label and pred == label}
        tp, fn, fp = len(true_hits), len(positive-true_hits), len(false_hits)
        precision, recall = tp/(tp+fp) if tp+fp else 0., tp/(tp+fn) if tp+fn else 0.
        result[label] = {'precision': precision, 'recall': recall, 'positive_episodes': tp+fn,
                         'negative_episodes': len(negative),
                         'tp': tp, 'fp': fp, 'fn': fn,
                         'f1': 2*precision*recall/(precision+recall) if precision+recall else 0.,
                         'precision_interval': wilson(tp, tp+fp), 'recall_interval': wilson(tp, tp+fn)}
    return {'classes': result, 'confusion': {k: dict(v) for k, v in confusion.items()},
            'macro_f1': sum(r['f1'] for r in result.values())/len(LABELS), 'episodes': len(grouped)}


def wilson(success, total):
    if total == 0:
        return [0., 1.]
    p, z = success/total, 1.96
    center = (p+z*z/(2*total))/(1+z*z/total)
    half = z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/(1+z*z/total)
    return [max(0, center-half), min(1, center+half)]


def thresholds_from_validation(samples):
    thresholds = {}
    for label in LABELS:
        candidates = []
        for t in (.5, .6, .7, .8, .85, .9, .95, .98):
            m = episode_metrics(samples, {k: t for k in LABELS})['classes'][label]
            candidates.append((m['precision'] >= .95, m['f1'], t))
        thresholds[label] = max(candidates)[2]
    return thresholds


def qualifies(metrics):
    return [label for label in CARE if
            metrics['classes'][label]['positive_episodes'] >= 30 and
            metrics['classes'][label]['negative_episodes'] >= 30 and
            metrics['classes'][label]['precision'] >= .95 and metrics['classes'][label]['recall'] >= .85]


def gpu_free_mib():
    import torch
    if not torch.cuda.is_available():
        return 0
    free, _ = torch.cuda.mem_get_info()
    # Windows CUDA can report a process/VM budget rather than memory available
    # across WSL and Podman. A resident shared model must count against capacity.
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=memory.free',
                                 '--format=csv,noheader,nounits'],
                                capture_output=True, text=True, timeout=5, check=True)
        host_free = [float(line.strip()) for line in result.stdout.splitlines() if line.strip()]
        if not host_free or any(not math.isfinite(n) or n < 0 for n in host_free):
            return 0
        return min(free/1024**2, *host_free)
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0  # Leave heavy work queued when shared capacity cannot be verified.


def train(root, dataset_id):
    from ..performance import training_locked
    if training_locked():
        return {'paused': True, 'reason': 'Training is paused by the workstation deployment policy'}
    """Run head and last-block experiments; choose on validation, then test once."""
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    import numpy as np
    import torch
    from transformers import VideoMAEForVideoClassification, VideoMAEImageProcessor
    from .media import file_hash, sample
    store = LearningStore(root)
    dataset = json.loads(store.safe_path(f'datasets/{dataset_id}.json').read_text())
    weights = Path(os.environ.get('CATWATCH_VIDEOMAE', '/opt/models/videomae'))
    if not (weights/'model.safetensors').is_file():
        raise ValueError('Pinned VideoMAE weights are not installed locally')
    if gpu_free_mib() < store.config()['training_free_mib']:
        return {'paused': True, 'reason': 'Waiting for GPU capacity'}
    parts = {split: [r for r in dataset['rows'] if r['split'] == split] for split in ('train', 'validation', 'test')}
    if any(not rows for rows in parts.values()):
        raise ValueError('Independent train, validation and test days are required')
    model_root = store.root/'models'/dataset_id
    import shutil
    used = sum(p.stat().st_size for p in (store.root/'models').rglob('*') if p.is_file())
    if used > 10_000_000_000 or shutil.disk_usage(store.root).free < 3_000_000_000:
        return {'paused': True, 'reason': 'Model storage budget or free-space reserve reached; checkpoints preserved'}
    model_root.mkdir(parents=True, exist_ok=True)
    processor = VideoMAEImageProcessor.from_pretrained(str(weights), local_files_only=True)
    clips = {r['clip_id']: store.clip(r['clip_id']) for r in dataset['rows']}
    for cid, version in dataset['label_versions'].items():
        if store.clip(cid)['version'] != version:
            raise ValueError('Labels changed; build a new dataset')
    for clip in clips.values():
        if file_hash(store.safe_path(clip['manifest']['video'])) != clip['manifest']['video_hash']:
            raise ValueError('Pinned training evidence failed its checksum')

    def tensor(row):
        frames = [cv[:, :, ::-1].copy() for _, cv in sample(store, clips[row['clip_id']], start=row['start'], end=row['end'])]
        return processor(frames, return_tensors='pt')['pixel_values'].to('cuda')

    def evaluate(model, rows):
        model.eval()
        out = []
        for row in rows:
            cfg = store.config()
            if not cfg['enabled'] or not cfg['training'] or store.meta('pause_training', False) or gpu_free_mib() < cfg['gpu_reserve_mib']:
                raise TrainingPaused('Evaluation paused; resume from the last checkpoint')
            with torch.inference_mode(), torch.autocast('cuda', dtype=torch.bfloat16):
                probabilities = model(pixel_values=tensor(row)).logits.float().softmax(-1)[0].cpu().tolist()
            out.append({**row, 'probabilities': probabilities})
        return out

    started = time.time()
    candidates = []
    for variant in ('head', 'last-block'):
        torch.manual_seed(17)
        random.seed(17)
        np.random.seed(17)
        folder = model_root/variant
        folder.mkdir(exist_ok=True)
        done = folder/'validation.json'
        if done.exists():
            candidates.append(json.loads(done.read_text()))
            continue
        model = VideoMAEForVideoClassification.from_pretrained(str(weights), num_labels=len(LABELS),
            id2label=dict(enumerate(LABELS)), label2id={k: i for i, k in enumerate(LABELS)},
            ignore_mismatched_sizes=True, local_files_only=True).to('cuda')
        for name, parameter in model.named_parameters():
            parameter.requires_grad = ('classifier' in name or
                                       variant == 'last-block' and ('encoder.layer.11.' in name or 'fc_norm' in name))
        optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=1e-4 if variant == 'head' else 1e-5)
        checkpoint = folder/'resume.pt'
        epoch, offset, best, stale = 0, 0, -1., 0
        if checkpoint.exists():
            saved = torch.load(checkpoint, map_location='cpu', weights_only=True)
            model.load_state_dict(saved['model']); optimizer.load_state_dict(saved['optimizer'])
            epoch, offset, best, stale = (saved[k] for k in ('epoch', 'offset', 'best', 'stale'))

        def save(e, index):
            temporary = folder/'resume.tmp'
            torch.save({'model': model.state_dict(), 'optimizer': optimizer.state_dict(),
                        'epoch': e, 'offset': index, 'best': best, 'stale': stale}, temporary)
            os.replace(temporary, checkpoint)

        for e in range(epoch, 20):
            ordered = list(parts['train'])
            random.Random(17+e).shuffle(ordered)
            model.train()
            for index in range(offset if e == epoch else 0, len(ordered)):
                cfg = store.config()
                if (not cfg['enabled'] or not cfg['training'] or
                    gpu_free_mib() < cfg['gpu_reserve_mib'] or time.time()-started > 4*3600 or
                    store.meta('pause_training', False)):
                    save(e, index)
                    return {'paused': True, 'reason': 'Checkpoint saved; yielding GPU'}
                row = ordered[index]
                optimizer.zero_grad(set_to_none=True)
                with torch.autocast('cuda', dtype=torch.bfloat16):
                    loss = model(pixel_values=tensor(row), labels=torch.tensor([LABELS.index(row['label'])], device='cuda')).loss * row['weight']
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.)
                optimizer.step()
                if index % 20 == 0:
                    store.set_meta('training_progress', {'dataset': dataset_id, 'variant': variant, 'epoch': e+1,
                                   'example': index+1, 'total': len(ordered), 'loss': float(loss.detach()), 'updated': time.time()})
                    save(e, index+1)
            predictions = evaluate(model, parts['validation'])
            thresholds = thresholds_from_validation(predictions)
            metrics = episode_metrics(predictions, thresholds)
            score = metrics['macro_f1']
            if score > best:
                best, stale = score, 0
                model.save_pretrained(folder/'best', safe_serialization=True)
                processor.save_pretrained(folder/'best')
                (folder/'best-validation.json').write_text(canonical({'variant': variant, 'thresholds': thresholds,
                    'metrics': metrics, 'predictions': predictions, 'path': str((folder/'best').relative_to(store.root))}))
            else:
                stale += 1
            save(e+1, 0)
            if stale >= 3:
                break
        result = json.loads((folder/'best-validation.json').read_text())
        done.write_text(canonical(result))
        candidates.append(result)
        del model, optimizer
        torch.cuda.empty_cache()
    winner = max(candidates, key=lambda c: (c['metrics']['macro_f1'], c['variant'] == 'head'))
    ident = digest([dataset_id, winner['variant'], PREPROCESS])
    model = VideoMAEForVideoClassification.from_pretrained(str(store.safe_path(winner['path'])), local_files_only=True).to('cuda')
    predictions = evaluate(model, parts['test'])
    metrics = episode_metrics(predictions, winner['thresholds'])
    body = {'dataset_id': dataset_id, 'checkpoint': CHECKPOINT, 'checkpoint_sha256': file_hash(weights/'model.safetensors'),
            'license': 'CC-BY-NC-4.0', 'preprocess': PREPROCESS, 'path': winner['path'],
            'label_versions': dataset['label_versions'], 'thresholds': winner['thresholds'],
            'validation': [{k: c[k] for k in ('variant', 'metrics')} for c in candidates],
            'test': metrics, 'test_examples': predictions, 'qualified_classes': qualifies(metrics),
            'shadow_since': time.time(), 'training_seconds': time.time()-started,
            'runtime': {'torch': torch.__version__, 'gpu': torch.cuda.get_device_name(0)}}
    store.save_model(ident, 'shadow', body)
    return {'model_id': ident, 'metrics': metrics, 'state': 'shadow'}


class TrainingPaused(Exception):
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--dataset', required=True)
    args = parser.parse_args()
    store = LearningStore(args.root)
    try:
        result = train(args.root, args.dataset)
    except TrainingPaused as error:
        result = {'paused': True, 'reason': str(error)}
    except Exception as error:
        # No network or credentials in this worker; keep bounded actionable diagnostics.
        result = {'error': f'{type(error).__name__}: {str(error)[:400]}'}
    store.set_meta('training_result:'+args.dataset, result)


if __name__ == '__main__':
    main()
