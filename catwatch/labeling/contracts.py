"""Label Studio 1.23 frame ranges -> immutable, zero-based half-open intervals."""
import hashlib
import json
import math
from pathlib import Path

RESOURCES = Path(__file__).parent
TAXONOMY = json.loads((RESOURCES / 'taxonomy.json').read_text())
LABELS = tuple(TAXONOMY['labels'])
SUBJECTS = ('single_cat', 'no_cat', 'uncertain_presence', 'multiple_cats')
QUALITY = ('occlusion', 'blur', 'poor_lighting', 'truncated_activity')
BOUNDARY = ('start_outside_clip', 'end_outside_clip')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def integer(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or int(value) != value:
        raise ValueError('Frame boundaries must be finite integers')
    return int(value)


def union(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1] + 1e-7:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    return merged


def normalize(annotation, manifest):
    """Never interpret a draft, prediction, empty submission or missing frames as negatives."""
    if annotation.get('was_cancelled') or annotation.get('draft'):
        raise ValueError('Skipped tasks and drafts are not completed annotations')
    choices, intervals, boundaries = {}, [], {}
    for result in annotation.get('result', []):
        name, value = result.get('from_name'), result.get('value', {})
        if name in ('subject', 'coverage', 'quality'):
            if name in choices:
                raise ValueError('Duplicate task choices')
            choices[name] = value.get('choices', [])
        elif name == 'boundary':
            flags = value.get('choices', [])
            if set(flags) - set(BOUNDARY):
                raise ValueError('Unknown boundary flag')
            boundaries[result['id']] = flags
        elif name == 'activity':
            labels = value.get('timelinelabels', [])
            if len(labels) != 1 or labels[0] not in LABELS:
                raise ValueError('Choose one known primary activity per region')
            for span in value.get('ranges', []):
                # Label Studio video frames are 1-based, and both bounds are inclusive.
                a, b = integer(span['start']) - 1, integer(span['end'])
                if not 0 <= a < b <= manifest['frame_count']:
                    raise ValueError('Activity range exceeds the clip')
                intervals.append({'start_frame': a, 'end_frame': b, 'label': labels[0], 'region_id': result['id']})
    if len(choices.get('subject', [])) != 1 or choices['subject'][0] not in SUBJECTS:
        raise ValueError('Choose a subject assessment')
    if len(choices.get('coverage', [])) != 1 or choices['coverage'][0] not in ('fully_labeled', 'partially_labeled'):
        raise ValueError('Choose full or partial annotation coverage')
    if set(choices.get('quality', [])) - set(QUALITY):
        raise ValueError('Unknown quality flag')
    if not intervals:
        raise ValueError('Mark explicit intervals; an empty annotation is not a negative example')
    subject = choices['subject'][0]
    intervals.sort(key=lambda i: (i['start_frame'], i['end_frame']))
    for n, item in enumerate(intervals):
        for previous in intervals[:n]:
            if previous['end_frame'] > item['start_frame'] and previous['label'] != item['label']:
                raise ValueError('Incompatible overlapping activities need correction')
        if subject == 'no_cat' and item['label'] != 'no_cat':
            raise ValueError('No-cat assessment requires no-cat intervals')
        if subject == 'uncertain_presence' and item['label'] not in ('unclear', 'no_cat'):
            raise ValueError('Uncertain presence cannot establish a specific cat activity')
        item['boundary'] = boundaries.get(item['region_id'], [])
        item['start_seconds'] = item['start_frame'] / manifest['fps']
        item['end_seconds'] = item['end_frame'] / manifest['fps']
    covered = union((i['start_frame'], i['end_frame']) for i in intervals)
    if choices['coverage'][0] == 'fully_labeled' and covered != [[0, manifest['frame_count']]]:
        raise ValueError('Fully labeled clips must cover every frame')
    return {'taxonomy_version': 1, 'subject': subject, 'coverage': choices['coverage'][0],
            'quality': choices.get('quality', []), 'intervals': intervals,
            'supervised_eligible': subject != 'multiple_cats',
            'annotation_id': annotation['id'], 'completed_by': annotation.get('completed_by'),
            'updated_at': annotation.get('updated_at'), 'raw_hash': fingerprint(annotation)}


def source_intervals(manifest, item):
    """Map each labeled frame run without bridging source gaps or timing discontinuities."""
    for run in manifest['mapping']:
        a = max(item['start_frame'], run['start_frame'])
        b = min(item['end_frame'], run['end_frame'])
        if a < b:
            yield (run['capture_start'] + (a-run['start_frame']) / manifest['fps'],
                   run['capture_start'] + (b-run['start_frame']) / manifest['fps'])
