from calibration_helpers import start as begin, prepare, permit
import json
import time
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from catwatch.analysis import AnalysisWorker, crop_window
from catwatch.investigation import MOTION_DEFAULTS
from catwatch.motion import MotionDetector, MotionTracker
from catwatch.retention import Retention
from catwatch.runtime import Runtime
from catwatch.store import Store
from test_investigation import source_segment

POLYGONS={'eating_pad':[[.1,.2],[.3,.2],[.3,.4],[.1,.4]],
          'water_fountain':[[.4,.2],[.6,.2],[.6,.4],[.4,.4]],
          'litter_box':[[.7,.2],[.9,.2],[.9,.4],[.7,.4]]}


def setup_cycle(tmp_path, now=100):
    store=Store(tmp_path);store.configure({'polygons':POLYGONS})
    session=begin(store,{'motion_scope':'areas','motion_fraction':.005,'motion_seconds':.5,'analysis_mode':'deferred','crop_comparison':True},now=now)
    return store,session


def test_area_motion_ignores_outside_changes_and_reports_each_region(tmp_path):
    _,session=setup_cycle(tmp_path)
    for name,polygon in POLYGONS.items():
        detector=MotionDetector(session['settings'],POLYGONS)
        blank=np.full((540,960,3),60,np.uint8)
        detector.observe(blank)
        outside=blank.copy();outside[430:500,20:800]=220
        assert all(v==0 for v in detector.observe(outside).values())
        moving=outside.copy()
        x,y=polygon[0];moving[int(y*540)+10:int(y*540)+40,int(x*960)+10:int(x*960)+40]=230
        scores=detector.observe(moving)
        assert scores[name]>.005
        assert all(v==0 for a,v in scores.items() if a!=name)


def test_area_debounce_does_not_combine_different_regions(tmp_path):
    store,session=setup_cycle(tmp_path);tracker=MotionTracker(store,session)
    tracker.observe(101,{'eating_pad':.02,'water_fountain':0})
    tracker.observe(101.3,{'eating_pad':0,'water_fountain':.02})
    tracker.observe(101.6,{'eating_pad':0,'water_fountain':.02})
    assert not store.motions()
    tracker.observe(101.9,{'eating_pad':0,'water_fountain':.02})
    tracker.interrupt()
    motion=store.motions()[0]
    assert json.loads(motion['area_peaks'])=={'water_fountain':.02}
    assert motion['start']==101.3
    assert store.motion_group_list(motion_area='water_fountain')['total']==1
    assert store.motion_group_list(motion_area='eating_pad')['total']==0
    assert store.motion_group_list(area='water_fountain')['total']==0


def test_new_session_protects_old_video_and_reviews_under_quota(tmp_path):
    store=Store(tmp_path);first=begin(store,now=100)
    old=source_segment(store,1,100,105,1000)
    mid=store.open_motion(first['id'],100,.01);store.update_motion(mid,105,.01);store.close_motion(mid)
    store.review_group(mid,{'status':'uncertain','areas':[],'behaviors':[],'notes':'Keep review','version':0})
    store.stop_investigation(now=110)
    second=begin(store,now=121)
    with store.db() as db:assert db.execute('select count(*) from protected_segments').fetchone()[0]==1
    retention=Retention(store,reserve_bytes=100_000_000)
    store.configure({'storage_cap_gb':.05})
    assert not retention.maintain(now=1000)
    assert old.exists()
    assert not retention.delete(store.segments()[0])
    assert store.group_review(mid)['notes']=='Keep review'
    assert store.motion_group_list(session_id=first['id'])['total']==1
    assert store.motion_group_list(session_id=second['id'])['total']==0


def test_deferred_jobs_and_capture_deadline(tmp_path):
    now=time.time();store,session=setup_cycle(tmp_path,now=now-100)
    mid=store.open_motion(session['id'],now-90,.01);store.update_motion(mid,now-80,.01);store.close_motion(mid)
    store.enqueue_analysis(mid)
    assert store.claim_job('detector_comparison') is None
    assert not Runtime(store).investigation_capture_finished()
    store.stop_investigation(now=now-20)
    assert Runtime(store).investigation_capture_finished()
    permit(store,'detector_comparison')
    assert store.claim_job('detector_comparison')['motion_id']==mid


def test_live_candidates_available_before_comparison(tmp_path):
    store,session=setup_cycle(tmp_path)
    mid=store.open_motion(session['id'],100,.01);store.update_motion(mid,105,.01);store.close_motion(mid)
    store.observation(102,'detection',{'model':'yolo11m','imgsz':640,'input_scope':'area_crops','detections':[{'label':'cat','confidence':.8,'box':[.1,.2,.3,.4]}]},session['id'])
    # Use current stamps: diagnostics outside the retention horizon may be removed.
    with store.db() as db:
        db.execute('INSERT INTO observations(session_id,stamp,kind,body) VALUES (?,?,?,?)',(session['id'],102,'detection',json.dumps({'model':'yolo11m','imgsz':640,'input_scope':'area_crops','detections':[{'label':'cat','confidence':.8,'box':[.1,.2,.3,.4]}]})))
    result=store.motion_group_list(cat='detected',session_id=session['id'])
    assert result['total']==1 and not result['groups'][0]['analysis_complete']
    assert result['groups'][0]['models']==['yolo11m/640/live/area_crops']
    assert store.motion_group_list(cat='not_detected')['total']==0


def test_crop_context_mapping_and_saved_provenance(tmp_path, monkeypatch):
    import sys
    store,session=setup_cycle(tmp_path)
    mid=store.open_motion(session['id'],100,.01);store.update_motion(mid,101,.01);store.close_motion(mid)
    frame=np.zeros((100,200,3),np.uint8)
    crop,bounds=crop_window(frame,POLYGONS['eating_pad'])
    assert crop.shape[:2]==(40,80) and bounds==(0,10,80,50)
    class Tensor:
        def __init__(self,value):self.value=value
        def cpu(self):return self
        def tolist(self):return self.value
    class Model:
        def predict(self,frame,**kwargs):
            h,w=frame.shape[:2]
            return [SimpleNamespace(names={15:'cat'},boxes=SimpleNamespace(xyxy=Tensor([[0,0,w,h]]),conf=Tensor([.8]),cls=Tensor([15])))]
    monkeypatch.setitem(sys.modules,'ultralytics',SimpleNamespace(YOLO=Model))
    monkeypatch.setattr('catwatch.analysis.sampled_frames',lambda *a:iter([(100,frame)]))
    worker=AnalysisWorker(Runtime(store),'detector_comparison');worker.models={'yolo11n':Model(),'yolo11m':Model()}
    result=worker.compare(store.motion(mid),[])
    assert len(result['observations'])==6
    eating=next(o for o in result['observations'] if o['crop_area']=='eating_pad')
    assert eating['detections'][0]['box']==[0,.1,.4,.5]
    store.enqueue_analysis(mid);permit(store,'detector_comparison');job=store.claim_job('detector_comparison');store.finish_job(job['id'],result)
    assert store.motion_group_list(model='yolo11m/640/crop:eating_pad',cat='detected')['total']==1


def test_deferred_evidence_is_protected_from_quota_expiry(tmp_path):
    store,session=setup_cycle(tmp_path)
    clip=source_segment(store,1,100,105,1000)
    mid=store.open_motion(session['id'],100,.01);store.update_motion(mid,105,.01);store.close_motion(mid)
    retention=Retention(store,reserve_bytes=100_000_000)
    store.configure({'storage_cap_gb':.05})
    assert not retention.maintain(now=1000)
    assert clip.exists()
    with store.db() as db:assert db.execute('select count(*) from protected_segments').fetchone()[0]==1


def test_explicit_reanalysis_of_protected_session_can_run(tmp_path):
    store=Store(tmp_path);first=begin(store,now=100)
    mid=store.open_motion(first['id'],100,.01);store.update_motion(mid,105,.01);store.close_motion(mid)
    store.stop_investigation(now=110);begin(store,now=121)
    store.queue_completed_motions(now=200)
    assert not store.jobs(mid)
    store.enqueue_analysis(mid,force=True)
    permit(store,'detector_comparison',session_id=first['id'])
    assert store.claim_job('detector_comparison')['motion_id']==mid


def test_slow_detector_keeps_newest_frames_and_balances_queue(tmp_path):
    runtime=Runtime(Store(tmp_path))
    for stamp in range(16):runtime.queue_detection_frame((stamp,None,'capture'))
    assert runtime.frame_queue.qsize()==10
    assert runtime.state['dropped_detection_frames']==6
    stamps=[]
    while not runtime.frame_queue.empty():
        stamps.append(runtime.frame_queue.get_nowait()[0]);runtime.frame_queue.task_done()
    runtime.frame_queue.join()
    assert stamps==list(range(6,16))


def test_detection_persists_coverage_and_gap_audit_with_visits(tmp_path):
    now=time.time();store,session=setup_cycle(tmp_path,now=now-10)
    class Tensor:
        def __init__(self,value):self.value=value
        def cpu(self):return self
        def tolist(self):return self.value
    class Model:
        def predict(self,frame,**kwargs):
            return [SimpleNamespace(names={15:'cat'},boxes=SimpleNamespace(xyxy=Tensor([[10,20,30,40]]),conf=Tensor([.8]),cls=Tensor([15])))]
    class CropModel:
        calls=0
        def predict(self,frame,**kwargs):
            self.calls+=1
            present=self.calls%2==1
            return [SimpleNamespace(names={15:'cat'},boxes=SimpleNamespace(xyxy=Tensor([[10,10,30,30]] if present else []),conf=Tensor([.8] if present else []),cls=Tensor([15] if present else [])))]
    runtime=Runtime(store);runtime.model=CropModel();runtime.state['dropped_detection_frames']=2
    for offset in range(6):runtime.detect(np.zeros((100,100,3),np.uint8),now-5+offset*.5)
    assert len(store.events())==1
    assert store.events()[0]['area']=='eating_pad'
    assert store.coverage()[0]['end']-store.coverage()[0]['start']==2.5
    with store.db() as db:
        assert db.execute("SELECT count(*) FROM observations WHERE kind='detection'").fetchone()[0]==6
        gaps=[json.loads(r[0]) for r in db.execute("SELECT body FROM observations WHERE kind='detector_gap'")]
    assert gaps==[{'reason':'older queued frames replaced by recent samples','count':2}]
