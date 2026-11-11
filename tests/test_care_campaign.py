import json
import time

from fastapi.testclient import TestClient
import pytest

from catwatch.learning import campaign as c
from catwatch.learning import comparison as cloud
from catwatch.learning.campaign_ui import create_app
from catwatch.learning.store import LearningStore
from catwatch.learning.contracts import digest


def manifest(items, authorization=c.CAMPAIGN):
    return {'authorization': authorization, 'budget_micros': cloud.BUDGET,
            'expires_epoch': time.time()+3600, 'items': items,
            'policies': cloud.POLICIES, 'max_input_tokens': cloud.MAX_INPUT, 'prompt': cloud.COMPARE_PROMPT}


def test_campaign_carries_prior_exposure_and_refuses_other_models(tmp_path):
    old = cloud.Ledger(tmp_path/'cloud-comparison.sqlite3')
    old.authorize(manifest([{'clip_id': 'old'}], cloud.AUTHORIZATION))
    ident = old.reserve('old', 'gpt-6-astra', cloud.reservation_for('gpt-6-astra'))
    old.finish(ident, 'complete', {}, accounted=2_019_750, estimate=681_330)
    new = c.ledger(tmp_path); items = [{'clip_id': str(i)} for i in range(100)]
    new.authorize(manifest(items))
    assert new.totals()['remaining_authorized_usd'] == 17.98025
    with pytest.raises(ValueError, match='not authorized'):
        new.reserve('0', 'gpt-6-astra', cloud.reservation_for('gpt-6-astra'))
    for i in range(25):
        new.reserve(str(i), c.MODEL, cloud.reservation_for(c.MODEL))
    with pytest.raises(ValueError, match='cannot cover'):
        new.reserve('25', c.MODEL, cloud.reservation_for(c.MODEL))
    assert new.totals()['conservative_accounted_usd'] <= 20
    assert old.totals()['conservative_accounted_usd'] == new.totals()['conservative_accounted_usd']
    assert c.ledger(tmp_path).reserve('0', c.MODEL, cloud.reservation_for(c.MODEL)) is None
    with pytest.raises(ValueError, match='reset'):
        new.authorize({**manifest(items), 'prompt': 'changed'})


def test_selection_balances_recent_scores_without_adjacent_duplicates():
    candidates = [{'id': str(i), 'target': c.TARGETS[i % 2], 'start': 10000-i*30,
                   'score': 100-i, 'group_key': str(i//3)} for i in range(160)]
    selected = c.diverse_selection(candidates)
    assert len(selected) == 100
    assert all(sum(x['target'] == t for x in selected) == 50 for t in c.TARGETS)
    assert len({i['id'] for i in selected}) == 100
    assert max(sum(x['group_key'] == i['group_key'] for x in selected) for i in selected) <= 2
    assert all(abs(a['start']-b['start']) >= 20 for n, a in enumerate(selected) for b in selected[n+1:])
    assert selected[0]['id'] == '0'


def fixture(tmp_path):
    store = LearningStore(tmp_path); store.configure({'training': False})
    for n in range(2):
        m = {'id': digest('clip'+str(n)), 'start': 1793760000+n*30, 'duration': 8.,
             'group_key': 'visit'+str(n), 'video_hash': 'video'+str(n), 'source_hashes': ['shared'],
             'video': 'evidence/test.mp4', 'areas': ['water_fountain'], 'crop': [0, 0, 10, 10],
             'width': 20, 'height': 20, 'fps': 15., 'frames': 120}
        store.add_clip(m)
    with store.db() as db:
        db.execute("UPDATE clips SET split='test',bucket='evaluation'")
        db.execute("UPDATE partitions SET split='test'")
    item = {'clip_id': digest('clip0'), 'start': 1793760000, 'target': 'water_fountain', 'duration': 8.,
            'selection': {}, 'local_prediction': None}
    m = manifest([item]); b = c.ledger(tmp_path); b.authorize(m)
    (tmp_path/'campaigns'/c.CAMPAIGN).mkdir(parents=True)
    return store, m


def test_assisted_reassignment_is_component_wide_audited_and_idempotent(tmp_path):
    store, m = fixture(tmp_path)
    audit = c.assign_assisted_pool(store, m)
    assert len(audit['clips']) == 2
    assert all(x['split'] == 'test' for x in audit['clips'])
    assert c.assign_assisted_pool(store, m) == audit
    assert all(store.clip(digest('clip'+str(i)))['split'] == 'train' for i in range(2))
    assert store.config()['training'] is False


@pytest.mark.parametrize('blocker', ['model', 'independent', 'training'])
def test_pool_reassignment_fails_atomically_when_unsafe(tmp_path, blocker):
    store, m = fixture(tmp_path)
    if blocker == 'model':
        with store.db() as db:
            db.execute("INSERT INTO models VALUES ('fixture',0,'retired','{}')")
    elif blocker == 'independent':
        with store.db() as db:
            db.execute('UPDATE clips SET decision=? WHERE id=?', (json.dumps({'independent': True}), digest('clip1')))
    else:
        store.configure({'training': True})
    with pytest.raises(ValueError):
        c.assign_assisted_pool(store, m)
    assert store.clip(digest('clip0'))['split'] == 'test'
    assert store.meta('assisted_pool:'+c.CAMPAIGN) is None


def test_review_requires_human_request_and_records_assistance_with_conflicts_and_undo(tmp_path):
    store, _ = fixture(tmp_path)
    with TestClient(create_app(tmp_path, refresh_seconds=999999)) as client:
        data = client.get('/api/batch').json()
        assert not store.clip(digest('clip0'))['decision']
        assert data['training_enabled'] is False
        payload = {'version': 0, 'action': 'review', 'annotation': {'subject': 'single_cat', 'quality': [],
                   'intervals': [{'start': 0, 'end': 8, 'label': 'drinking'}]}}
        assert client.put('/api/clips/'+digest('clip0')+'/decision', json=payload).status_code == 403
        headers = {'x-catwatch-token': data['token'], 'origin': 'https://evil.example'}
        assert client.put('/api/clips/'+digest('clip0')+'/decision', headers=headers, json=payload).status_code == 403
        headers['origin'] = 'http://localhost:8767'
        r = client.put('/api/clips/'+digest('clip0')+'/decision', headers=headers, json=payload)
        assert r.status_code == 200
        decision = r.json()['decision']
        assert decision['source'] == 'human' and decision['independent'] is False
        assert c.CAMPAIGN in decision['assisted_by']
        assert client.put('/api/clips/'+digest('clip0')+'/decision', headers=headers, json=payload).status_code == 409
        r = client.put('/api/clips/'+digest('clip0')+'/decision', headers=headers, json={'version': 1, 'action': 'undo'})
        assert r.status_code == 200 and r.json()['decision'] is None
        assert client.get('/api/clips/not-a-member').status_code == 404
        assert client.get('/', headers={'host': 'evil.example'}).status_code == 400
        assert store.config()['training'] is False


def test_dense_sampler_matches_existing_crop_and_timestamps(tmp_path):
    from pathlib import Path
    import shutil
    import numpy as np
    from catwatch.learning.media import sample, info
    video = Path(__file__).parent/'fixtures/synthetic-review.mp4'
    shutil.copyfile(video, tmp_path/'fixture.mp4')
    meta = info(tmp_path/'fixture.mp4')
    clip = {'duration': min(8., meta['duration']), 'manifest': {'video': 'fixture.mp4',
            'frames': meta['frame_count'], 'fps': meta['fps'], 'crop': [10, 10, 110, 110]}}
    evidence = cloud.Evidence(tmp_path)
    dense = list(c.dense_frames(evidence, clip))
    old = sample(evidence, clip, count=32, end=clip['duration'])
    assert len(dense) == 32
    assert [t for t, _ in dense] == [t for t, _ in old]
    assert all(np.array_equal(a, b) for (_, a), (_, b) in zip(dense, old))


def test_rolling_shortlist_excludes_the_frozen_batch_and_its_source_groups(tmp_path, monkeypatch):
    candidates = [{'id': str(i), 'target': c.TARGETS[i % 2], 'start': 10000-i*30,
                   'duration': 8, 'day': 'fixture', 'score': 100-i, 'signals': {},
                   'group_key': str(i//2)} for i in range(30)]
    monkeypatch.setattr(c, 'ranked_candidates', lambda root: candidates)
    folder = tmp_path/'campaigns'/c.CAMPAIGN
    folder.mkdir(parents=True)
    frozen = {'items': [{'clip_id': '0', 'group_key': '0'}]}
    (folder/'manifest.json').write_text(json.dumps(frozen))
    selected = c.refresh(tmp_path)
    assert selected and all(x['group_key'] != '0' for x in selected)
    assert all(x['id'] not in ('0', '1') for x in selected)
    assert json.loads((folder/'manifest.json').read_text()) == frozen
    assert not (tmp_path/'cloud-comparison.sqlite3').exists()
