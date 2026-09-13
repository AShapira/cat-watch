import json
import time

import pytest
from fastapi.testclient import TestClient

from calibration_helpers import prepare, start, permit, POLYGONS
from catwatch.analysis import AnalysisWorker
from catwatch.runtime import Runtime
from catwatch.store import Store
from catwatch.web import create_app
from test_investigation import source_segment


def test_fresh_image_required_each_cycle_and_frozen_snapshot(tmp_path,monkeypatch):
    clock=[1000.]
    monkeypatch.setattr(time,'time',lambda:clock[0])
    store=Store(tmp_path)
    assert store.config()['polygons']=={}
    with pytest.raises(ValueError):store.start_investigation()
    with pytest.raises(ValueError):store.prepare(b'image',980,200,100)
    first=prepare(store)
    session=store.start_investigation({'calibration_id':first['id'],'duration_seconds':900})
    assert session['deadline']==1900 and session['config_snapshot']['pre_seconds']==5
    with pytest.raises(ValueError):store.configure({'confidence':.5})
    with pytest.raises(ValueError):prepare(store)
    clock[0]=1904.9
    restored=Store(tmp_path);restored.recover()
    assert not Runtime(restored).analysis_ready()
    with pytest.raises(ValueError):prepare(store)
    clock[0]=1905
    assert Runtime(restored).analysis_ready()
    with pytest.raises(ValueError):restored.start_investigation({'calibration_id':first['id']})
    changed={**POLYGONS,'water_fountain':POLYGONS['eating_pad']}
    second=prepare(restored,changed,masks=[])
    other=restored.start_investigation({'calibration_id':second['id'],'masks':[]})
    assert other['config_snapshot']['polygons']!=session['config_snapshot']['polygons']
    assert restored.investigation(session['id'])['config_snapshot']==session['config_snapshot']
    assert (store.root/first['reference_image']).is_file()
    assert other['deadline']-other['start']==28800


@pytest.mark.parametrize('duration',[900,1800,28800,86400])
def test_duration_contract(tmp_path,duration):
    store=Store(tmp_path)
    assert start(store,{'duration_seconds':duration},now=100)['deadline']==100+duration


@pytest.mark.parametrize('duration',[0,899,901,86401,True,900.0])
def test_invalid_duration(tmp_path,duration):
    with pytest.raises(ValueError):start(Store(tmp_path),{'duration_seconds':duration},now=100)


def test_confirmation_invalidated_by_settings_changes(tmp_path):
    store=Store(tmp_path);draft=prepare(store)
    store.configure({'area_overlap':{a:.1 for a in POLYGONS}})
    assert not store.preparation()['confirmed']
    with pytest.raises(ValueError):store.start_investigation({'calibration_id':draft['id']})


@pytest.mark.parametrize('mode',['live','deferred'])
def test_deadline_plus_five_and_drained_queues_gate_analysis(tmp_path,monkeypatch,mode):
    clock=[100.];monkeypatch.setattr(time,'time',lambda:clock[0])
    store=Store(tmp_path);start(store,{'analysis_mode':mode,'duration_seconds':900})
    runtime=Runtime(store)
    clock[0]=1004.99;assert not runtime.investigation_capture_finished()
    clock[0]=1005;assert runtime.investigation_capture_finished()
    for key in ['capture_busy','live_model_loaded']:
        runtime.state[key]=True;assert not runtime.analysis_ready();runtime.state[key]=False
    runtime.frame_queue.put(None);assert not runtime.analysis_ready()
    runtime.frame_queue.get();runtime.frame_queue.task_done()
    runtime.segment_queue.put(None);assert not runtime.analysis_ready()
    runtime.segment_queue.get();runtime.segment_queue.task_done()
    assert runtime.analysis_ready()


def test_evidence_five_seconds_and_job_readiness(tmp_path):
    store=Store(tmp_path);session=start(store,now=100)
    for i,(a,b) in enumerate([(80,100),(100,120),(120,140)]):source_segment(store,i,a,b)
    evidence=store.evidence(105,110)
    assert min(x['play_start'] for x in evidence)==100
    assert max(x['play_end'] for x in evidence)==115
    mid=store.open_motion(session['id'],105,.01);store.update_motion(mid,110,.01);store.close_motion(mid)
    store.queue_completed_motions(now=114.999);assert not store.jobs()
    store.queue_completed_motions(now=115);assert len(store.jobs())==2
    assert not store.claim_job('detector_comparison')


def test_behaviors_exclusive_unclear_and_conflict_history(tmp_path):
    store=Store(tmp_path);session=start(store,now=100)
    mid=store.open_motion(session['id'],105,.01);store.close_motion(mid)
    body={'status':'cat_confirmed','areas':['eating_pad','water_fountain'],'behaviors':['eating','drinking'],'notes':'Both observed','version':0}
    saved=store.review_group(mid,body);assert saved['version']==1
    with pytest.raises(ValueError):store.review_group(mid,{**body,'version':1,'behaviors':['unclear','eating']})
    with TestClient(create_app(store,Runtime(store),False)) as client:
        token=client.get('/api/session').json()['token']
        assert client.put(f'/api/investigation/groups/{mid}/review',json=body,headers={'x-catwatch-token':token}).status_code==409
    store.review_group(mid,{**body,'version':1,'behaviors':['unclear']})
    detail=store.motion_group_detail(mid)
    assert detail['history'][0]['previous']['behaviors']==['eating','drinking']
    assert not store.events() and not store.jobs()


def test_failed_readiness_does_not_claim_and_restart_requires_retry(tmp_path,monkeypatch):
    store=Store(tmp_path);session=start(store,now=100)
    mid=store.open_motion(session['id'],105,.01);store.close_motion(mid);store.enqueue_analysis(mid)
    permit(store,'video_description')
    monkeypatch.setattr('catwatch.analysis.local_json',lambda *a,**kw:{'data':[{'id':'another-model'}]})
    AnalysisWorker(Runtime(store),'video_description').run_one()
    assert store.analysis_status()['phase']=='blocked'
    assert all(j['status']=='queued' for j in store.jobs())
    permit(store,'detector_comparison')
    owner={'container_id':'owned','started_at':'time'}
    store.update_analysis({'owner':owner})
    assert store.claim_job('detector_comparison')
    store.recover_investigation()
    assert store.analysis_status()['owner']==owner
    assert store.analysis_status()['phase']=='blocked'
    assert not store.claim_job('detector_comparison')
    assert all(j['status']=='queued' for j in store.jobs())
    with pytest.raises(ValueError):store.request_analysis()
    store.update_analysis({'owner':None})
    assert store.request_analysis()['attempt']==3


def test_controller_stale_permits_and_validation(tmp_path):
    store=Store(tmp_path);start(store,now=100)
    state=store.request_analysis()
    for patch in [{'attempt':True},{'attempt':state['attempt']-1},{'allowed_kind':'unknown'},
                  {'checked_kinds':'video_description'},{'checked_kinds':['unknown']},{'phase':'processing','allowed_kind':None}]:
        with pytest.raises(ValueError):store.control_analysis({'attempt':state['attempt'],'phase':'processing','allowed_kind':'video_description',**patch})
    store.pause_analysis('Out of memory')
    with pytest.raises(ValueError):store.control_analysis({'attempt':state['attempt'],'phase':'processing','allowed_kind':'video_description'})
