from calibration_helpers import start as begin, prepare, permit
import json
import time
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from catwatch.investigation import MOTION_DEFAULTS
from catwatch.motion import MotionDetector, MotionTracker
from catwatch.retention import Retention
from catwatch.runtime import Runtime
from catwatch.store import Store
from catwatch.web import create_app


def test_review_only_preserves_records_and_rejects_mutations(tmp_path):
    store=Store(tmp_path)
    begin(store,)
    store.stop_investigation()
    runtime=Runtime(store)
    runtime.state['review_only']=True
    with TestClient(create_app(store,runtime,False)) as client:
        token=client.get('/api/session').json()['token']
        assert not client.get('/api/investigation').json()['session']['active']
        response=client.post('/api/investigation',json={},headers={'x-catwatch-token':token})
        assert response.status_code==403
        assert 'Review-only' in response.json()['detail']
    assert store.investigation()['stop'] is not None


def test_video_description_preserves_four_fps_and_pixel_budget(tmp_path, monkeypatch):
    from catwatch.analysis import AnalysisWorker
    store=Store(tmp_path)
    runtime=Runtime(store)
    path=tmp_path/'sample.mp4'
    writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),15,(160,96))
    for index in range(120):
        frame=np.full((96,160,3),80,np.uint8)
        frame[40:60,index:index+10]=240
        writer.write(frame)
    writer.release()
    requests=[]
    def request(endpoint,payload,timeout):
        requests.append(payload)
        assert payload['mm_processor_kwargs']['max_pixels']==32*448*256
        assert payload['chat_template_kwargs']['enable_thinking'] is False
        return {'choices':[{'message':{'content':'An object moves.'},'finish_reason':'stop'}]}
    monkeypatch.setattr('catwatch.analysis.local_json',request)
    answer=AnalysisWorker(runtime,'video_description').describe(
        {'start':100,'end':108},[{'path':'sample.mp4','start':100,'end':108}],'local-model')
    assert len(requests)==1
    assert answer['windows'][0]['sample_frames']==32
    assert answer['input_version']==2
    assert not list((tmp_path/'analysis-input').iterdir())


def source_segment(store, index, start, end, size=100):
    folder=store.root/'media'
    folder.mkdir(exist_ok=True)
    path=f'media/{"a"*32}-{index:06d}.mp4'
    (store.root/path).write_bytes(b'x'*size)
    store.add_segment(path,start,end,size)
    return store.root/path


def test_deadline_restart_stop_requires_new_calibration(tmp_path):
    store=Store(tmp_path)
    event=store.open_visit('water_fountain',10,11)
    store.configure({'confidence':.5})
    session=begin(store,now=100)
    assert session['deadline']==28900
    restored=Store(tmp_path)
    restored.recover()
    assert restored.investigation()['deadline']==28900
    assert restored.event(event)['interrupted']
    assert restored.config()['confidence']==.5
    restored.stop_investigation(now=200)
    assert restored.investigation()['end']==200
    with pytest.raises(ValueError):
        restored.start_investigation(now=205)
    assert begin(restored,now=211)['id']!=session['id']


def test_motion_debounce_merging_splitting_and_deadline(tmp_path):
    store=Store(tmp_path)
    session=begin(store,now=100)
    tracker=MotionTracker(store,session)
    tracker.observe(101,.01)
    tracker.observe(101.1,0)
    assert not store.motions()
    for stamp in [102,102.1,102.2,103,105,110]:
        tracker.observe(stamp,.01)
    tracker.observe(115,0)
    tracker.observe(116,.01)
    assert len(store.motions())==1
    tracker.observe(147,0)
    motion=store.motions()[0]
    assert (motion['start'],motion['end'],motion['open'])==(102,116,0)
    tracker.observe(150,.01)
    tracker.observe(150.6,.01)
    tracker.observe(210.5,.01)
    assert len(store.motions())==3
    latest=store.motions()[0]
    previous=store.motions()[1]
    assert latest['group_id']==previous['group_id']
    assert previous['end']==latest['start']
    tracker.session['end']=211
    tracker.observe(211,.1)
    assert not store.motions()[0]['open']


def test_static_timestamp_motion_and_lighting():
    detector=MotionDetector(dict(MOTION_DEFAULTS,masks=[[0,0,.4,.1]]))
    image=np.full((540,960,3),80,np.uint8)
    assert detector.observe(image)==0
    for _ in range(10):
        assert detector.observe(image)==0
    clock=image.copy()
    clock[:40,:300]=220
    assert detector.observe(clock)==0
    movement=clock.copy()
    movement[300:350,600:670]=240
    assert detector.observe(movement)>.0005
    shadow=clock.copy()
    shadow[350:420,500:600]=30
    assert detector.observe(shadow)>.0005
    brighter=np.full_like(image,150)
    assert detector.observe(brighter)>.1


def test_motion_retention_without_cat_and_expiry(tmp_path):
    store=Store(tmp_path)
    session=begin(store,now=100)
    before=source_segment(store,0,290,295)
    during=source_segment(store,1,301,306)
    after=source_segment(store,2,310,315)
    quiet=source_segment(store,3,320,325)
    recent=source_segment(store,4,460,465)
    mid=store.open_motion(session['id'],300,.01)
    store.update_motion(mid,305,.01)
    store.close_motion(mid)
    retention=Retention(store,reserve_bytes=100,disk_floor=0)
    assert retention.maintain(now=500)
    assert all(p.exists() for p in [before,during,after,recent])
    assert not quiet.exists()
    assert not store.events()
    store.stop_investigation(now=510)
    retention.maintain(now=700)
    assert during.exists() and not recent.exists()


def test_jobs_recovery_claim_and_no_duplicates(tmp_path):
    store=Store(tmp_path)
    session=begin(store,now=100)
    mid=store.open_motion(session['id'],101,.01)
    store.update_motion(mid,110,.01)
    store.close_motion(mid)
    store.queue_completed_motions(now=114)
    assert not store.jobs()
    store.queue_completed_motions(now=115)
    store.queue_completed_motions(now=115)
    assert len(store.jobs())==2
    permit(store,'video_description')
    with ThreadPoolExecutor(2) as pool:
        claims=list(pool.map(lambda _:store.claim_job('video_description'),range(2)))
    assert sum(j is not None for j in claims)==1
    store.recover_investigation()
    assert store.claim_job('video_description') is None
    permit(store,'video_description')
    job=store.claim_job('video_description')
    store.finish_job(job['id'],{'windows':[{'text':'A person moves.'}]})
    store.enqueue_analysis(mid,True)
    assert len(store.jobs())==3


def test_api_controls_validation_and_evidence(tmp_path):
    store=Store(tmp_path)
    runtime=Runtime(store)
    with TestClient(create_app(store,runtime,False)) as client:
        headers={'x-catwatch-token':client.get('/api/session').json()['token']}
        assert client.post('/api/investigation',json={}).status_code==403
        assert client.post('/api/investigation',json={'masks':[[.5,0,.1,1]]},headers=headers).status_code==400
        draft=prepare(store)
        response=client.post('/api/investigation',json={'calibration_id':draft['id']},headers=headers)
        assert response.status_code==200
        assert client.post('/api/investigation',json={},headers=headers).status_code==400
        assert client.patch('/api/investigation',json=dict(MOTION_DEFAULTS,masks=[]),headers=headers).status_code==400
        session=response.json()
        stamp=time.time()
        mid=store.open_motion(session['id'],stamp,.01)
        store.update_motion(mid,stamp+1,.01)
        store.close_motion(mid)
        assert client.get('/api/investigation/motions').json()['motions'][0]['evidence']=='expired'
        assert client.get(f'/api/investigation/motions/{mid}/thumbnail').status_code==410
        assert client.get('/api/investigation/jobs?limit=300').status_code==400
        assert client.post('/api/investigation/stop',json={},headers=headers).status_code==200
        report=client.get('/api/investigation/report').json()
        assert report['session_id']==session['id'] and report['finished']
        assert report['motion_groups']==1 and report['chunks_with_remaining_evidence']==0
        assert report['accuracy'].startswith('Not evaluated')


def test_motion_worker_records_without_gpu(tmp_path):
    store=Store(tmp_path)
    start=time.time()
    begin(store,now=start-1)
    runtime=Runtime(store)
    path=runtime.media/('b'*32+'-000000.mp4')
    writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),15,(960,540))
    assert writer.isOpened()
    for i in range(75):
        frame=np.full((540,960,3),60,np.uint8)
        cv2.rectangle(frame,(100+i*4,300),(160+i*4,360),(230,230,230),-1)
        writer.write(frame)
    writer.release()
    store.add_segment(str(path.relative_to(store.root)),start,start+5,path.stat().st_size)
    sid=store.segment_id(str(path.relative_to(store.root)))
    runtime.retention.leases[sid]=1
    runtime.segment_queue.put((path,start,start+5,sid,'capture-one'))
    import threading
    worker=threading.Thread(target=runtime.motion_worker)
    worker.start()
    runtime.segment_queue.join()
    runtime.stop.set()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert store.motions() and not store.events()
    assert runtime.state['motion_frames']==25
    assert runtime.state['detector']=='stopped' and runtime.frame_queue.qsize()>0
    assert runtime.frame and runtime.retention.leases[sid]==0


@pytest.mark.parametrize('value',[float('nan'),float('inf'),True,-1])
def test_nonfinite_motion_settings(value):
    with pytest.raises(ValueError):
        Store.validate_motion_settings(dict(MOTION_DEFAULTS,motion_fraction=value))
