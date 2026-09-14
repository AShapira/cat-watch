"""Structured model suggestions; never parse activity ranges from prose."""
from .contracts import LABELS, integer


def prediction(intervals, manifest, model_version, score=None):
    if not isinstance(model_version, str) or not model_version.strip():
        raise ValueError('Record the model and prompt version')
    result = []
    for index, item in enumerate(intervals):
        a, b = integer(item['start_frame']), integer(item['end_frame'])
        if not 0 <= a < b <= manifest['frame_count'] or item['label'] not in LABELS:
            raise ValueError('Invalid structured prediction interval')
        result.append({'id': f'prediction{index}', 'from_name': 'activity', 'to_name': 'video',
                       'type': 'timelinelabels', 'value': {'ranges': [{'start': a+1, 'end': b}],
                                                       'timelinelabels': [item['label']]}})
    if score is not None and (isinstance(score, bool) or not 0 <= score <= 1):
        raise ValueError('Prediction score must be between zero and one')
    return {'model_version': model_version, 'result': result, **({'score': score} if score is not None else {})}
