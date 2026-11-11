import json
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from catwatch.learning import cloud
from catwatch.learning.contracts import LABELS, digest, normalize
from catwatch.learning.media import add_video
from catwatch.learning.monitoring import coverage, deliver_one, summary
from catwatch.learning.store import Conflict, LearningStore
from catwatch.learning.training import components, episode_metrics, make_dataset, qualifies
from catwatch.runtime import Runtime
from catwatch.store import Store
from catwatch.web import create_app
from calibration_helpers import POLYGONS, prepare


def manifest(key='one', start=1700000000., group=None, sources=None):
    ident = digest(key)
    return {'id': ident, 'start': start, 'duration': 8., 'group_key': group or key,
            'video': f'evidence/{ident}.mp4', 'video_hash': ident, 'source_hashes': sources or [ident],
            'crop': [0, 0, 100, 100], 'areas': ['eating_pad'], 'width': 200, 'height': 100,
            'fps': 10., 'frames': 80}


def annotation(label='eating', start=0., end=8.):
    return {'subject': 'no_cat' if label == 'no_cat' else 'single_cat', 'quality': [],
            'intervals': [{'start': start, 'end': end, 'label': label}]}


def review(store, ident, label='eating', version=0):
    return store.review(ident, {'version': version, 'action': 'review', 'annotation': annotation(label)})


def test_annotation_contract_partial_unclear_and_transitions():
    assert normalize(annotation(start=2, end=4), 8)['coverage'] == 'partially_labeled'
    with pytest.raises(ValueError):
        normalize({'subject': 'single_cat', 'intervals': []}, 8)
    with pytest.raises(ValueError):
        normalize({**annotation(), 'intervals': [{'start': 0, 'end': 5, 'label': 'eating'},
                                               {'start': 4, 'end': 8, 'label': 'drinking'}]}, 8)
    with pytest.raises(ValueError):
        normalize({**annotation(), 'subject': 'multiple_cats'}, 8)
    with pytest.raises(ValueError):
        normalize(annotation(start=float('nan')), 8)
    out = normalize({**annotation(), 'intervals': [{'start': 0, 'end': 3, 'label': 'sniffing_inspecting'},
                                                  {'start': 3, 'end': 8, 'label': 'eating'}]}, 8)
    assert out['coverage'] == 'fully_labeled'


def test_skip_undo_conflicts_and_history(tmp_path):
    s = LearningStore(tmp_path)
    ident = s.add_clip(manifest())
    assert s.review(ident, {'version': 0, 'action': 'skip'})['decision'] is None
    assert not s.review_queue()['items']
    saved = review(s, ident, version=1)
    assert saved['decision']['source'] == 'human' and saved['version'] == 2
    with pytest.raises(Conflict):
        review(s, ident, 'drinking', 1)
    undo = s.review(ident, {'version': 2, 'action': 'undo'})
    assert undo['decision'] is None and len(undo['history']) == 3
    assert not s.status()['training_ready']
    assert all(j['kind'] == 'label' for j in s.jobs())


def test_prediction_is_not_gold_and_blind_review(tmp_path):
    s = LearningStore(tmp_path); ident = s.add_clip(manifest())
    s.prediction(ident, annotation(), {'provider': 'test', 'model': 'fixture', 'prompt_version': '1'})
    assert s.status()['counts']['suggestions'] == 1
    assert s.status()['episodes']['eating'] == 0
    with s.db() as db:
        db.execute("UPDATE clips SET bucket='evaluation' WHERE id=?", (ident,))
    assert s.clip(ident, blind=True)['prediction'] is None
    assert s.review_queue()['items'][0]['prediction'] is None
    with pytest.raises(ValueError):
        make_dataset(s)


def test_media_import_preserves_pixels_and_groups(tmp_path):
    s = LearningStore(tmp_path)
    path = Path(__file__).parent/'fixtures/synthetic-review.mp4'
    ids = add_video(s, path, start=1700000000, group_key='episode-1', polygons=POLYGONS)
    assert ids
    assert ids == add_video(s, path, start=1700000000, group_key='episode-1', polygons=POLYGONS)
    assert s.status()['counts']['clips'] == len(ids)
    from catwatch.learning.media import sample
    c = s.clip(ids[0]); frames = sample(s, c)
    assert len(frames) == 16 and frames[0][1].shape[1] == c['manifest']['crop'][2]-c['manifest']['crop'][0]
    with pytest.raises(ValueError):
        s.safe_path('../secret')


def test_day_group_source_leakage_and_frozen_partitions(tmp_path):
    s = LearningStore(tmp_path)
    for n in range(30):
        ident = s.add_clip(manifest(str(n), 1700000000+n*86400))
        review(s, ident)
    first = make_dataset(s)
    assignment = {r['clip_id']: r['split'] for r in first['rows']}
    assert set(assignment.values()) == {'train', 'validation', 'test'}
    extra = s.add_clip(manifest('extra', 1700000000+12, sources=[digest('0')]))
    review(s, extra)
    second = make_dataset(s)
    changed = {r['clip_id']: r['split'] for r in second['rows']}
    assert all(changed[k] == v for k, v in assignment.items())
    assert changed[extra] == assignment[digest('0')]
    assert first['id'] != second['id']


def test_cross_midnight_and_shared_sources_are_connected(tmp_path):
    s = LearningStore(tmp_path)
    # Episodes crossing a day boundary and shared media form one component.
    a = manifest('a', 1700000000, group='shared')
    b = manifest('b', 1700000000+86400, group='shared')
    c = manifest('c', 1700000000+2*86400, sources=[a['video_hash']])
    for m in (a, b, c):
        s.add_clip(m)
    groups = components(s.clips()['items'])
    assert len(groups) == 1


def test_unknown_is_false_negative_and_independent_episode_metrics():
    rows = [{'group_key': str(n), 'label': 'eating', 'probabilities': [.9,.025,.025,.025,.025]} for n in range(30)]
    negatives = [{'group_key': 'n'+str(n), 'label': 'no_cat', 'probabilities': [0,0,0,0,1]} for n in range(30)]
    metrics = episode_metrics(rows*4+negatives)
    assert metrics['classes']['eating']['positive_episodes'] == 30
    assert 'eating' in qualifies(metrics)
    metrics = episode_metrics(rows+negatives, {'eating': .99, 'no_cat': .5})
    assert metrics['classes']['eating']['recall'] == 0
    assert 'eating' not in qualifies(metrics)


def test_correction_invalidates_model_and_future_alerts(tmp_path):
    s = LearningStore(tmp_path); ident = s.add_clip(manifest()); review(s, ident)
    s.save_model('model', 'active', {'label_versions': {ident: 1}})
    review(s, ident, 'drinking', 1)
    assert s.model('model')['state'] == 'invalidated'


def test_jobs_restart_retry_and_no_duplicate_imports(tmp_path):
    s = LearningStore(tmp_path)
    s.enqueue('test', 'key', {'a': 1}); s.enqueue('test', 'key', {'a': 2})
    j = s.claim('test'); assert j['payload'] == {'a': 1}
    assert s.claim('test') is None
    s.recover(); assert s.claim('test')['id'] == j['id']
    s.finish(j['id'], error='Busy', retry_after=30)
    assert s.claim('test') is None
    assert s.claim('test', now=time.time()+31)


def test_coverage_union_and_missing_time(tmp_path):
    s = LearningStore(tmp_path)
    with s.db() as db:
        db.executemany('INSERT INTO coverage VALUES (?,?,?)', [(0,20,1),(10,30,1),(30,70,0),(70,100,1)])
    c = coverage(s, 0, 100)
    assert c == {'fraction': .6, 'seconds': 60, 'largest_gap': 40}
    assert summary(s, 0, 100)['classes']['drinking']['episodes'] == 0


def test_telegram_disabled_private_allowlist_and_unknown_outcome(tmp_path, monkeypatch):
    s = LearningStore(tmp_path)
    s.notice('n', 'system', {'text': 'Fixture notification'})
    monkeypatch.setenv('CATWATCH_TELEGRAM_TOKEN', 'fake')
    called = []
    def send(request):
        called.append(request)
        raise httpx.ReadTimeout('ambiguous')
    transport = httpx.MockTransport(send)
    assert not deliver_one(s, transport=transport)
    assert not called
    with pytest.raises(ValueError):
        s.configure({'telegram_chat_id': '-123'})
    s.configure({'telegram_enabled': True, 'telegram_chat_id': '123'})
    assert deliver_one(s, transport=transport)
    assert s.notices()[0]['state'] == 'unknown'
    assert not deliver_one(s, transport=transport)
    assert len(called) == 1


def cloud_fixture(tmp_path, monkeypatch):
    s = LearningStore(tmp_path/'learning')
    ident = s.add_clip(manifest())
    policy = {'fixture-model': {'provider': 'openai', 'context_tokens': 100000,
              'input_usd_per_million': 1, 'output_usd_per_million': 2,
              'valid_until': time.time()+86400, 'source': 'https://developers.openai.com/api/docs/pricing'}}
    path = tmp_path/'policy.json'; path.write_text(json.dumps(policy))
    monkeypatch.setenv('CATWATCH_CLOUD_POLICY_FILE', str(path))
    monkeypatch.setenv('CATWATCH_OPENAI_API_KEY', 'fixture-key')
    import numpy as np
    monkeypatch.setattr(cloud, 'sample', lambda *a, **k: [(0., np.zeros((20,20,3), dtype=np.uint8))])
    b = cloud.propose(s, {'model': 'fixture-model', 'items': [{'clip_id': ident}]})
    return s, b


def test_cloud_requires_approval_expiry_and_budget(tmp_path, monkeypatch):
    s, b = cloud_fixture(tmp_path, monkeypatch)
    def forbidden(request):
        pytest.fail('No cloud request is authorized')
    assert not cloud.dispatch_one(s, transport=httpx.MockTransport(forbidden))
    with pytest.raises(ValueError):
        cloud.approve(s, b['id'], 'wrong')
    cloud.approve(s, b['id'], b['fingerprint'])
    with s.db() as db:
        db.execute('UPDATE cloud_batches SET expires=0')
    assert not cloud.dispatch_one(s, transport=httpx.MockTransport(forbidden))
    assert cloud.batch(s, b['id'])['state'] == 'expired'
    with pytest.raises(ValueError):
        cloud.propose(s, {'model': 'fixture-model', 'items': [{'clip_id': b['manifest']['items'][0]['clip_id']}], 'budget_usd': .01})


@pytest.mark.parametrize('change', ['revoke', 'payload', 'policy'])
def test_cloud_mutation_never_sends(tmp_path, monkeypatch, change):
    s, b = cloud_fixture(tmp_path, monkeypatch)
    cloud.approve(s, b['id'], b['fingerprint'])
    if change == 'revoke':
        cloud.revoke(s, b['id'])
    elif change == 'payload':
        s.safe_path(b['manifest']['items'][0]['images'][0]['path']).write_bytes(b'changed')
    else:
        monkeypatch.setattr(cloud, 'policies', lambda: {})
    assert not cloud.dispatch_one(s, transport=httpx.MockTransport(lambda r: pytest.fail('Unauthorized request')))


def test_cloud_unknown_outcome_reserved_once_no_retry(tmp_path, monkeypatch):
    s, b = cloud_fixture(tmp_path, monkeypatch)
    cloud.approve(s, b['id'], b['fingerprint'])
    calls = []
    def fail(request):
        calls.append(request)
        raise httpx.ReadTimeout('Ambiguous completion')
    assert cloud.dispatch_one(s, transport=httpx.MockTransport(fail))
    assert not cloud.dispatch_one(s, transport=httpx.MockTransport(fail))
    assert len(calls) == 1
    result = cloud.batch(s, b['id'])
    assert result['reserved_micros'] == b['manifest']['request_ceiling_micros']
    assert result['state'] == 'needs_attention'


def test_learning_api_review_only_auth_and_monitoring_calibration(tmp_path):
    source = Store(tmp_path); runtime = Runtime(source)
    app = create_app(source, runtime, False); learning = app.state.agent.store
    ident = learning.add_clip(manifest())
    with TestClient(app) as c:
        token = c.get('/api/session').json()['token']; headers = {'x-catwatch-token': token}
        assert c.get('/api/learning/status').status_code == 200
        assert c.post('/api/monitoring/start', json={}).status_code == 403
        assert c.post('/api/monitoring/start', json={}, headers=headers).status_code == 400
        runtime.state['review_only'] = True
        assert c.post('/api/learning/import', headers=headers).status_code == 403
        result = c.put(f'/api/learning/clips/{ident}/decision', json={'version': 0, 'action': 'review', 'annotation': annotation()}, headers=headers)
        assert result.status_code == 200
        assert c.put(f'/api/learning/clips/{ident}/decision', json={'version': 0, 'action': 'review', 'annotation': annotation()}, headers=headers).status_code == 409
        assert c.get('/api/learning/export').json()[0]['annotations'][0]['result'][0]['value']['ranges'][0] == {'start': 1, 'end': 80}
        runtime.state['review_only'] = False
        prepared = prepare(source)
        started = c.post('/api/monitoring/start', json={'calibration_id': prepared['id']}, headers=headers)
        assert started.status_code == 200
        assert learning.config()['continuous']
        assert c.post('/api/monitoring/stop', headers=headers).status_code == 200
        assert not learning.config()['continuous']


def test_overlapping_exports_do_not_inflate_independent_support(tmp_path):
    s = LearningStore(tmp_path)
    for key, stamp in [('motion',1700000000), ('visit',1700000002), ('area',1700000004)]:
        review(s, s.add_clip(manifest(key, stamp)))
    assert s.status()['episodes']['eating'] == 1
    data = make_dataset(s)
    assert len({r['group_key'] for r in data['rows']}) == 1
    rows = [{'group_key':'one', 'label':label, 'probabilities':[0,0,0,0,1]} for label in ('drinking','no_cat')]
    assert episode_metrics(rows)['classes']['eating']['negative_episodes'] == 1


def test_candidate_cannot_inherit_another_models_coverage(tmp_path):
    from catwatch.learning.monitoring import baseline
    s = LearningStore(tmp_path); now = time.time()
    with s.db() as db:
        db.execute('INSERT INTO coverage VALUES (?,?,1)', (now-31*86400, now))
        db.execute('INSERT INTO model_coverage VALUES (?,?,?)', ('old', now-31*86400, now))
    assert baseline(s, now, 'old')['ready']
    assert not baseline(s, now, 'candidate')['ready']
    assert coverage(s, now-3600, now, 'candidate')['fraction'] == 0


def test_human_correction_replaces_machine_summary_interval(tmp_path):
    s = LearningStore(tmp_path); ident = s.add_clip(manifest())
    s.save_model('m', 'shadow', {})
    with s.db() as db:
        db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)',
                   ('e',1700000000,1700000008,'eating','model','m',ident,0,'{}'))
    assert summary(s, 1700000000, 1700000010)['classes']['eating']['episodes'] == 1
    review(s, ident, 'no_cat')
    assert summary(s, 1700000000, 1700000010)['classes']['eating']['episodes'] == 0


def test_label_change_during_training_blocks_publication(tmp_path):
    s = LearningStore(tmp_path); ident = s.add_clip(manifest()); review(s, ident)
    labels = {ident:1}
    review(s, ident, 'drinking', 1)
    with pytest.raises(Conflict):
        s.save_model('late-worker', 'shadow', {'label_versions':labels})
    assert not s.models()


def test_daily_summary_dst_calendar_and_restart_idempotence(tmp_path):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from types import SimpleNamespace
    from catwatch.learning.monitoring import tick
    s = LearningStore(tmp_path); s.configure({'continuous':True}, internal=True)
    now = datetime(2026,10,25,9,1,tzinfo=ZoneInfo('Asia/Jerusalem')).timestamp()
    runtime = SimpleNamespace(state={'camera':'stopped','detector':'stopped'})
    tick(s, runtime, now); tick(s, runtime, now+15)
    notices = [n for n in s.notices() if n['kind']=='summary']
    assert len(notices) == 1
    assert notices[0]['body']['end']-notices[0]['body']['start'] == 25*3600


def test_shadow_alerts_require_coverage_and_all_assessments(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from catwatch.learning import monitoring
    s = LearningStore(tmp_path); s.configure({'continuous':True}, internal=True)
    now = time.time(); since = now-8*86400
    s.save_model('candidate', 'shadow', {'qualified_classes':['eating'], 'shadow_alert_since':since})
    runtime = SimpleNamespace(state={'camera':'connected','detector':'ready','detection_stamp':now})
    s.set_meta('inference_stamp', now)
    monkeypatch.setattr(monitoring, 'baseline', lambda *a, **k: {'ready':True, 'valid_days':14,
        'classes':{'eating':{'absence_seconds':3600,'frequent_per_hour':3}}})
    monitoring.tick(s, runtime, now)
    assert s.model('candidate')['state'] == 'shadow'
    assert not [n for n in s.notices() if n['kind']=='behavior']
    with s.db() as db:
        db.execute('INSERT INTO model_coverage VALUES (?,?,?)', ('candidate', since, now))
    s.notice('unassessed', 'behavior', {'model_id':'candidate', 'label':'eating', 'text':'Fixture'}, shadow=True)
    for n in range(105):
        s.notice(str(n), 'system', {'text':'Fixture'})
    monitoring.tick(s, runtime, now)
    assert s.model('candidate')['state'] == 'shadow'  # includes alerts beyond first page
    monitoring.acknowledge(s, 'unassessed', {'correct':True})
    monitoring.tick(s, runtime, now)
    assert s.model('candidate')['state'] == 'active'


def test_scene_movement_uses_background_geometry():
    import cv2
    import numpy as np
    from catwatch.learning.scene import displacement
    rng = np.random.default_rng(17)
    reference = rng.integers(0,256,(400,640,3),dtype=np.uint8)
    shifted = cv2.warpAffine(reference, np.float32([[1,0,60],[0,1,0]]), (640,400))
    assert displacement(reference, reference) < .01
    assert displacement(reference, shifted) > .08
    assert displacement(np.zeros_like(reference), np.zeros_like(reference)) is None


def test_corrected_model_cancels_pending_telegram_alert(tmp_path, monkeypatch):
    s = LearningStore(tmp_path)
    s.configure({'telegram_enabled':True,'telegram_chat_id':'123'})
    monkeypatch.setenv('CATWATCH_TELEGRAM_TOKEN','fake')
    s.save_model('m','invalidated',{'qualified_classes':['eating']})
    s.notice('old-alert','behavior',{'text':'Fixture','model_id':'m','label':'eating'})
    assert deliver_one(s,transport=httpx.MockTransport(lambda r: pytest.fail('Invalidated alert must not send')))
    assert s.notices()[0]['state']=='cancelled'


def test_outbound_area_names_cannot_disguise_whole_room(tmp_path, monkeypatch):
    s,b=cloud_fixture(tmp_path,monkeypatch)
    ident=b['manifest']['items'][0]['clip_id']
    m=s.clip(ident)['manifest']
    m['crop']=[0,0,m['width'],m['height']]
    with s.db() as db:
        db.execute('UPDATE clips SET manifest=? WHERE id=?',(json.dumps(m),ident))
    with pytest.raises(ValueError,match='area crop'):
        cloud.propose(s,{'model':'fixture-model','items':[{'clip_id':ident}]})


def test_failed_shadow_candidate_does_not_block_future_training(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from catwatch.learning import monitoring
    s=LearningStore(tmp_path); s.configure({'continuous':True},internal=True)
    s.save_model('candidate','shadow',{'qualified_classes':['eating']})
    for n in range(2):
        s.notice(str(n),'behavior',{'model_id':'candidate','correct':False,'text':'Fixture'},shadow=True)
    monkeypatch.setattr(monitoring,'baseline',lambda *a,**k:{'ready':False,'valid_days':0,'classes':{}})
    monitoring.tick(s,SimpleNamespace(state={}))
    assert s.model('candidate')['state']=='rejected'
    assert not s.inference_models()
