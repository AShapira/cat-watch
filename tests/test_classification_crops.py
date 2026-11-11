import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from catwatch.learning.crop_policy import (BRIDGE, CROP_POLICY, classification_regions,
                                          FOUNTAIN_BRIDGE, install_fountain_bridge,
                                          install_queue_bridge, legacy_fountain_polygon)
from catwatch.learning.media import add_video, file_hash, sample
from catwatch.learning.store import LearningStore
from catwatch.learning.worker import Agent
from catwatch.regions import crop_regions
from catwatch.store import Store

POLYGONS = {
    'eating_pad': [[.4, .4], [.55, .4], [.55, .6], [.4, .6]],
    'water_fountain': [[.5, .3], [.65, .3], [.65, .5], [.5, .5]],
    'litter_box': [[.8, .1], [.95, .1], [.95, .3], [.8, .3]],
}


def payload():
    return {'start': 100, 'end': 108, 'session_id': 1, 'group_key': 'motion:1:2',
            'polygons': POLYGONS, 'kind': 'motion'}


def test_independent_classification_preserves_detector_context():
    detector = crop_regions(POLYGONS, 2560, 1440)
    assert any(r['areas'] == ['eating_pad', 'water_fountain'] for r in detector)
    classified = classification_regions(POLYGONS, 2560, 1440)
    assert [r['areas'] for r in classified] == [[a] for a in sorted(POLYGONS)]
    for region in classified:
        area = region['areas'][0]
        assert region == crop_regions({area: POLYGONS[area]}, 2560, 1440)[0]
    assert crop_regions(POLYGONS, 2560, 1440) == detector


def test_one_source_video_separate_manifests_and_native_samples(tmp_path):
    store = LearningStore(tmp_path)
    source = Path(__file__).parent / 'fixtures/synthetic-review.mp4'
    ids = add_video(store, source, start=1700000000., group_key='episode-1', polygons=POLYGONS)
    assert len(ids) == len(set(ids)) == 3
    assert ids == add_video(store, source, start=1700000000., group_key='episode-1', polygons=POLYGONS)
    clips = [store.clip(ident) for ident in ids]
    assert len(list((tmp_path / 'evidence').glob('*.mp4'))) == 1
    assert {c['manifest']['video_hash'] for c in clips} == {file_hash(source)}
    assert {tuple(c['manifest']['areas']) for c in clips} == {(a,) for a in POLYGONS}
    for clip in clips:
        manifest = clip['manifest']
        assert manifest['group_key'] == 'episode-1' and manifest['crop_policy'] == CROP_POLICY
        x1, y1, x2, y2 = manifest['crop']
        frames = sample(store, clip, count=2)
        assert all(frame.shape[:2] == (y2-y1, x2-x1) for _, frame in frames)


def test_identical_area_boxes_keep_distinct_classification_identity(tmp_path):
    store = LearningStore(tmp_path)
    source = Path(__file__).parent / 'fixtures/synthetic-review.mp4'
    polygons = {a: POLYGONS['eating_pad'] for a in ('eating_pad', 'water_fountain')}
    ids = add_video(store, source, start=1700000000., group_key='episode-1', polygons=polygons)
    assert len(set(ids)) == 2
    assert {tuple(store.clip(i)['manifest']['areas']) for i in ids} == {(a,) for a in polygons}


def test_bridge_splits_new_and_pending_jobs_for_legacy_extractor(tmp_path):
    store = LearningStore(tmp_path)
    store.configure({'training': False})
    store.enqueue('extract', 'pending', payload())
    store.enqueue('label', 'label', {'clip_id': 'unchanged'})
    with store.db() as db:
        assert install_queue_bridge(db) == 1
        assert install_queue_bridge(db) == 0
    for _ in range(2):
        store.enqueue('extract', 'new', payload())
    jobs = store.jobs()
    assert len(jobs) == 5
    assert next(j for j in jobs if j['kind'] == 'label')['payload'] == {'clip_id': 'unchanged'}
    for prefix in ('new', 'pending'):
        pair = [j for j in jobs if j['kind'] == 'extract' and j['key'].startswith(prefix)]
        assert len(pair) == 2
        regions = [r for j in pair for r in crop_regions(j['payload']['polygons'], 2560, 1440)]
        assert sorted(r['areas'] for r in regions) == [[a] for a in sorted(POLYGONS)]
        assert all({k: v for k, v in j['payload'].items() if k != 'polygons'} ==
                   {k: v for k, v in payload().items() if k != 'polygons'} for j in pair)
    assert not store.config()['training']


def test_bridge_installation_is_atomic_and_leaves_claimed_jobs_unchanged(tmp_path):
    store = LearningStore(tmp_path)
    store.enqueue('extract', 'running', payload())
    running = store.claim('extract')
    store.enqueue('extract', 'pending', payload())
    before = store.jobs()
    with pytest.raises(RuntimeError):
        with store.db() as db:
            install_queue_bridge(db)
            raise RuntimeError('rollback this transaction')
    assert store.jobs() == before
    with store.db() as db:
        assert not db.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?', ('trigger', BRIDGE)).fetchone()
        install_queue_bridge(db)
    assert next(j for j in store.jobs() if j['id'] == running['id']) == before[-1]


def test_patched_worker_start_removes_bridge_without_losing_split_jobs(tmp_path, monkeypatch):
    source = Store(tmp_path)
    store = LearningStore(tmp_path / 'learning')
    with store.db() as db:
        install_queue_bridge(db)
    store.enqueue('extract', 'old-worker', payload())
    old_jobs = store.jobs()
    # Inspection of the store is not a deployment and must preserve the bridge.
    restarted = LearningStore(tmp_path / 'learning')
    assert restarted.jobs() == old_jobs
    with restarted.db() as db:
        assert db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (BRIDGE,)).fetchone()
    monkeypatch.setattr('threading.Thread.start', lambda self: None)
    monkeypatch.setenv('CATWATCH_PREPARED_DATASET', str(tmp_path / 'no-legacy-dataset'))
    agent = Agent(source, SimpleNamespace(retention=SimpleNamespace()))
    agent.start()
    assert restarted.jobs() == old_jobs
    assert restarted.meta('classification_crop_policy')['implementation'] == 'native-media'
    restarted.enqueue('extract', 'new-worker', payload())
    assert len(restarted.jobs()) == 3
    assert next(j for j in restarted.jobs() if j['key'] == 'new-worker')['payload'] == payload()


def fountain_override():
    return {'polygon': POLYGONS['water_fountain'], 'source_size': [2560,1440],
            'box': [1180,400,1360,602]}


def test_tight_fountain_crops_only_matching_calibration_and_preserves_other_areas():
    original = classification_regions(POLYGONS,2560,1440)
    overrides = {'water_fountain':fountain_override()}
    tight = classification_regions(POLYGONS,2560,1440,overrides=overrides)
    for before,after in zip(original,tight):
        assert after == ({'areas':['water_fountain'],'box':[1180,400,1360,602]}
                         if before['areas']==['water_fountain'] else before)
    changed = {**POLYGONS,'water_fountain':[[.1,.1],[.2,.1],[.2,.2]]}
    assert classification_regions(changed,2560,1440,overrides=overrides) == classification_regions(changed,2560,1440)
    half = classification_regions(POLYGONS,1280,720,overrides=overrides)
    assert next(r['box'] for r in half if r['areas']==['water_fountain']) == [590,200,680,301]


def test_tight_bridge_fires_for_split_companions_and_preserves_running_inputs(tmp_path):
    store = LearningStore(tmp_path)
    override = fountain_override()
    with store.db() as db:
        install_queue_bridge(db)
    store.enqueue('extract','pending',payload())
    # Claim the food/litter job, then its fountain companion.
    store.claim('extract'); running = store.claim('extract')
    store.enqueue('extract','queued',payload())
    with store.db() as db:
        assert install_fountain_bridge(db,override) == 1
        assert install_fountain_bridge(db,override) == 0
    store.enqueue('extract','new',payload())
    assert next(j for j in store.jobs() if j['id']==running['id'])['payload'] == running['payload']
    for key in ('queued','new'):
        water = next(j for j in store.jobs() if j['key']==key+':independent-water-fountain')
        assert water['payload']['classification_original_polygons'] == {'water_fountain':override['polygon']}
        assert crop_regions(water['payload']['polygons'],2560,1440)[0]['box'] == override['box']
        other = next(j for j in store.jobs() if j['key']==key)
        assert other['payload']['polygons'] == {a:p for a,p in POLYGONS.items() if a!='water_fountain'}
    # Singleton jobs with a different calibration must not inherit this crop.
    fresh={**payload(),'polygons':{'water_fountain':[[.1,.1],[.2,.1],[.2,.2]]}}
    store.enqueue('extract','new-calibration',fresh)
    assert next(j for j in store.jobs() if j['key']=='new-calibration')['payload'] == fresh


def test_tight_native_import_has_new_identity_and_keeps_old_manifest(tmp_path):
    store=LearningStore(tmp_path)
    source=Path(__file__).parent/'fixtures/synthetic-review.mp4'
    polygons={'water_fountain':POLYGONS['water_fountain']}
    old=add_video(store,source,start=1700000000.,group_key='same-episode',polygons=polygons)[0]
    old_manifest=store.clip(old)['manifest']
    store.set_meta('classification_crop_overrides',{'water_fountain':fountain_override()})
    new=add_video(store,source,start=1700000000.,group_key='same-episode',polygons=polygons)[0]
    assert new!=old and store.clip(old)['manifest']==old_manifest
    clip=store.clip(new)
    assert clip['manifest']['video_hash']==old_manifest['video_hash']
    frames=sample(store,clip,count=2)
    x1,y1,x2,y2=clip['manifest']['crop']
    assert all(f.shape[:2]==(y2-y1,x2-x1) for _,f in frames)
    assert clip['manifest']['classification_crop_overrides']['water_fountain']==fountain_override()


def test_tight_bridge_rolls_back_and_native_worker_retires_both(tmp_path,monkeypatch):
    source=Store(tmp_path); store=LearningStore(tmp_path/'learning')
    with store.db() as db:
        install_queue_bridge(db)
    store.enqueue('extract','pending',payload())
    before=store.jobs()
    with pytest.raises(RuntimeError):
        with store.db() as db:
            install_fountain_bridge(db,fountain_override())
            raise RuntimeError('rollback')
    assert store.jobs()==before
    with store.db() as db:
        install_fountain_bridge(db,fountain_override())
    pending=store.jobs()
    monkeypatch.setattr('threading.Thread.start',lambda self:None)
    monkeypatch.setenv('CATWATCH_PREPARED_DATASET',str(tmp_path/'missing'))
    Agent(source,SimpleNamespace(retention=SimpleNamespace())).start()
    assert store.jobs()==pending
    with store.db() as db:
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name IN (?,?)",(BRIDGE,FOUNTAIN_BRIDGE)).fetchone()
