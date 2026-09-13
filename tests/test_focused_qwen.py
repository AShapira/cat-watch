import base64
import json
import time
import urllib.error
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from calibration_helpers import start,permit,prepare,POLYGONS
from catwatch.analysis import AnalysisWorker
from catwatch.core import box_assignment
from catwatch.investigation import MOTION_DEFAULTS
from catwatch.regions import region_masks,crop_regions,predict_regions
from catwatch.runtime import Runtime
from catwatch.shared_model import describe_regions
from catwatch.store import Store
from catwatch.web import create_app
from test_investigation import source_segment


def test_buffer_exclusions_edges_and_presence_are_separate():
    polygons={'eating_pad':[[.4,.4],[.6,.4],[.6,.6],[.4,.6]]}
    exact=region_masks(polygons,100,100)['eating_pad']
    buffered=region_masks(polygons,100,100,.2,[[.35,.35,.4,.65]])['eating_pad']
    assert not exact[38,50] and buffered[38,50]
    assert not buffered[50,38]
    assert not box_assignment(polygons,[.42,.35,.48,.39],{'eating_pad':.2})['areas']
    mask=region_masks({'eating_pad':[[0,0],[.1,0],[.1,.1],[0,.1]]},100,100,1)['eating_pad']
    assert mask.shape==(100,100) and mask[0,0] and not mask[-1,-1]


def test_native_pixels_crop_merge_and_coordinate_deduplication():
    polygons={'eating_pad':[[.1,.2],[.3,.2],[.3,.4],[.1,.4]],
              'water_fountain':[[.25,.2],[.4,.2],[.4,.4],[.25,.4]],
              'litter_box':[[.75,.2],[.85,.2],[.85,.4],[.75,.4]]}
    frame=np.arange(100*200*3,dtype=np.uint8).reshape(100,200,3)
    regions=crop_regions(polygons,200,100,.5)
    assert len(regions)==2 and regions[0]['areas']==['eating_pad','water_fountain']
    seen=[]
    class Tensor:
        def __init__(self,x):self.x=x
        def cpu(self):return self
        def tolist(self):return self.x
    class Model:
        def predict(self,part,**kw):
            r=regions[len(seen)];x1,y1,x2,y2=r['box'];seen.append(part)
            assert np.array_equal(part,frame[y1:y2,x1:x2]) and kw['imgsz']==640
            return [SimpleNamespace(names={15:'cat'},boxes=SimpleNamespace(xyxy=Tensor([[1,2,11,12],[1,2,11,12]]),conf=Tensor([.8,.9]),cls=Tensor([15,15])))]
    detections,_=predict_regions(Model(),frame,polygons,.5)
    assert len(detections)==2 and detections[0]['confidence']==.9
    x,y,*_=regions[0]['box']
    assert detections[0]['box']==[(x+1)/200,(y+2)/100,(x+11)/200,(y+12)/100]


@pytest.mark.parametrize('field,value',[('motion_buffer',-1),('motion_buffer',1.1),('motion_buffer',True),('crop_context',float('nan')),('description_timeout',0)])
def test_setting_validation(tmp_path,field,value):
    with pytest.raises(ValueError):start(Store(tmp_path),{field:value})


def test_future_defaults_snapshots_and_historical_queue_isolation(tmp_path):
    store=Store(tmp_path);old=start(store,now=100)
    # Model the actual pre-refactor historical record without running a migration.
    legacy=dict(old['settings']);[legacy.pop(k) for k in ('motion_buffer','crop_context','detector_model','description_provider','description_model','description_url','description_timeout')]
    with store.db() as db:db.execute('UPDATE investigations SET settings=? WHERE id=?',(json.dumps(legacy),old['id']))
    mid=store.open_motion(old['id'],105,.01);store.close_motion(mid);store.enqueue_analysis(mid)
    before=store.jobs()
    new=start(store,now=time.time()-1000,updates={'duration_seconds':900})
    assert new['settings']['motion_scope']=='areas' and new['settings']['motion_buffer']==.2
    assert store.investigation(old['id'])['settings']==legacy
    other=store.open_motion(new['id'],new['start']+5,.01);store.close_motion(other);store.enqueue_analysis(other)
    permit(store,'video_description',new['id'])
    assert store.claim_job('video_description')['motion_id']==other
    assert store.claim_job('video_description') is None
    assert [j for j in store.jobs() if j['motion_id']==mid]==before


def fixture_worker(tmp_path,monkeypatch):
    now=[1000.];monkeypatch.setattr(time,'time',lambda:now[0])
    store=Store(tmp_path);session=start(store,now=0,updates={'duration_seconds':900})
    source_segment(store,1,99,121)
    mid=store.open_motion(session['id'],105,.01);store.update_motion(mid,113,.01);store.close_motion(mid);store.enqueue_analysis(mid)
    permit(store,'video_description')
    worker=AnalysisWorker(Runtime(store),'video_description')
    monkeypatch.setattr('catwatch.shared_model.ready_model',lambda _: {'digest':'exact-digest'})
    return now,store,worker


def test_shared_busy_backoff_is_bounded_and_survives_restart(tmp_path,monkeypatch):
    now,store,worker=fixture_worker(tmp_path,monkeypatch)
    def busy(*args):raise urllib.error.HTTPError('local',503,'busy',{},None)
    monkeypatch.setattr('catwatch.shared_model.describe_regions',busy)
    for count,delay in enumerate((30,120,300),1):
        worker.run_one();state=store.analysis_status()
        assert state['phase']=='processing' and state['retry']['attempts']==count
        assert state['retry']['next_at']==now[0]+delay
        worker.run_one();assert store.analysis_status()==state
        now[0]+=delay
    worker.run_one();assert store.analysis_status()['phase']=='blocked'
    assert all(j['status']=='queued' for j in store.jobs())
    store.recover_investigation();assert store.analysis_status()['retry']['attempts']==3
    permit(store,'video_description');assert store.analysis_status()['retry']=={}


def test_shared_timeout_preserves_jobs_without_automatic_retry(tmp_path,monkeypatch):
    _,store,worker=fixture_worker(tmp_path,monkeypatch)
    monkeypatch.setattr('catwatch.shared_model.describe_regions',lambda *a:(_ for _ in ()).throw(TimeoutError()))
    worker.run_one()
    assert store.analysis_status()['phase']=='blocked'
    assert all(j['status']=='queued' for j in store.jobs())


def test_qwen_native_images_timestamps_and_completed_request_checkpoint(tmp_path,monkeypatch):
    _,store,worker=fixture_worker(tmp_path,monkeypatch)
    worker.current_job=store.claim_job('video_description')['id']
    motion=store.motion(1);settings=store.investigation()['settings']
    source=np.arange(100*200*3,dtype=np.uint8).reshape(100,200,3)
    monkeypatch.setattr('catwatch.analysis.sampled_frames',lambda root,segments,a,b,fps: iter([(a+i*.5,source) for i in range(min(16,int((b-a)*2)))]))
    requests=[]
    def respond(config,path,payload):
        requests.append(payload)
        images=[m for m in payload['messages'] if m.get('images')]
        assert 0<len(images)<=16 and payload['think'] is False and payload['options']['num_predict']==512
        assert '0.00 seconds' in images[0]['content']
        image=cv2.imdecode(np.frombuffer(base64.b64decode(images[0]['images'][0]),np.uint8),cv2.IMREAD_COLOR)
        assert image.shape[0]<=100 and image.shape[1]<=200
        return {'message':{'content':'Visible cat; activity unclear.'},'done_reason':'stop'}
    monkeypatch.setattr('catwatch.shared_model.ollama_json',respond)
    result=describe_regions(worker,motion,[],settings,{'digest':'exact-digest'})
    assert result['model_digest']=='exact-digest' and result['provider']=='ollama'
    count=len(requests);assert count>0
    assert describe_regions(worker,motion,[],settings,{'digest':'exact-digest'})==result
    assert len(requests)==count


def test_preview_is_read_only_and_matches_detector_masks(tmp_path):
    store=Store(tmp_path);prepare(store)
    with TestClient(create_app(store,Runtime(store),False)) as client:
        token=client.get('/api/session').json()['token'];before=store.preparation()
        response=client.post('/api/investigation/preview-regions',json={'polygons':POLYGONS,'masks':[],'motion_buffer':.2},headers={'x-catwatch-token':token})
        assert response.status_code==200 and set(response.json()['outlines'])==set(POLYGONS)
        assert store.preparation()==before and store.investigation() is None


def test_presence_filters_keep_overlaps_unique_and_do_not_bridge_gaps(tmp_path,monkeypatch):
    monkeypatch.setattr(time,'time',lambda:1000.)
    store=Store(tmp_path)
    polygons=dict(POLYGONS,water_fountain=POLYGONS['eating_pad'])
    prepare(store,polygons=polygons,masks=[])
    session=store.start_investigation({'calibration_id':store.preparation()['id'],'masks':[]},now=100)
    groups=[]
    for offset,stamps in ((0,[110,111,112]),(30,[140,140.5]),(60,[170,172,174]),(90,[])):
        mid=store.open_motion(session['id'],110+offset,.01)
        store.update_motion(mid,115+offset,.01,{'eating_pad':.01,'water_fountain':.01})
        store.close_motion(mid)
        groups.append(store.motion(mid)['group_id'])
        for stamp in stamps:
            store.observation(stamp,'detection',{'model':'yolo11m','imgsz':640,'input_scope':'area_crops',
                'detections':[{'label':'cat','confidence':.9,'box':[.1,.1,.3,.3]}]})
    sustained=store.motion_group_list(presence='sustained')
    assert sustained['total']==1 and sustained['groups'][0]['id']==groups[0]
    assert sustained['groups'][0]['sustained_areas']==['eating_pad','water_fountain']
    assert store.motion_group_list(presence='sustained',area='water_fountain')['total']==1
    assert store.motion_group_list(presence='sustained',area='eating_pad')['total']==1
    assert store.motion_group_list(presence='brief')['total']==2
    assert store.motion_group_list(presence='cat',model='yolo11m/640/live/area_crops')['total']==3
    # Brief motion with no cat remains available; uncompleted comparisons are uncertain.
    assert store.motion_group_list(presence='buffered_motion')['total']==4
    assert store.motion_group_list(presence='uncertain')['total']==4
