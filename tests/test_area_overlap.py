from calibration_helpers import start
import json

import pytest
from fastapi.testclient import TestClient

from catwatch.core import AREAS, box_assignment, box_overlap
from catwatch.runtime import Runtime
from catwatch.store import Store
from catwatch.web import create_app
from test_investigation_review import add_motion, comparison


def test_overlap_geometry_and_denominator():
    polygon=[[0,0],[1,0],[1,.2],[0,.2]]
    assert box_overlap(polygon,[0,0,1,1])==pytest.approx(.2)
    assert box_overlap(list(reversed(polygon)),[0,0,1,1])==pytest.approx(.2)
    assert box_overlap(polygon,[0,0,.5,.1])==pytest.approx(1)
    assert box_overlap(polygon,[0,.2,1,1])==0  # touching has no area
    assert box_overlap(polygon,[0,0,0,1])==0
    assert box_overlap(polygon,[0,0,float('nan'),1])==0
    # Concave L: area .75, clipped in the upper-right quarter to area .05.
    concave=[[0,0],[1,0],[1,.5],[.5,.5],[.5,1],[0,1]]
    assert box_overlap(concave,[0,0,1,1])==pytest.approx(.75)
    assert box_overlap(concave,[.4,.4,.7,.7])==pytest.approx(5/9)


def test_overlap_boundary_and_multiple_qualifying_areas():
    polygon=[[0,0],[1,0],[1,.2],[0,.2]]
    thresholds=dict.fromkeys(AREAS,.2)
    assert box_assignment({'eating_pad':polygon},[0,0,1,1],thresholds)['areas']==['eating_pad']
    assert box_assignment({'eating_pad':polygon,'water_fountain':polygon},[0,0,1,1],thresholds)['areas']==['eating_pad','water_fountain']
    thresholds['eating_pad']=.21
    assert box_assignment({'eating_pad':polygon},[0,0,1,1],thresholds)['location']=='outside'
    assert box_assignment({},[0,0,1,1],thresholds)['location']=='unknown'


def test_saved_boxes_use_snapshot_without_modifying_evidence_or_labels(tmp_path):
    store=Store(tmp_path)
    polygon=[[0,0],[1,0],[1,.2],[0,.2]]
    store.configure({'polygons':{'eating_pad':polygon,'water_fountain':polygon,'litter_box':[[.9,.9],[1,.9],[1,1]]}})
    start(store,now=1)
    mid=add_motion(store,100)
    comparison(store,mid,[('yolo11m/1280',.85,[0,0,1,1])])
    before=store.jobs(mid)
    store.review_group(mid,{'status':'cat_confirmed','areas':['eating_pad','water_fountain'],'behaviors':['eating','drinking'],'notes':'Human label','version':0})
    for area in ['eating_pad','water_fountain']:
        assert store.motion_group_list(area=area)['total']==1
    assert store.motion_group_list()['total']==1
    detection=store.motion_group_detail(mid)['samples'][0]['detections'][0]
    assert detection['overlaps']['eating_pad']==pytest.approx(.2)
    assert detection['areas']==['eating_pad','water_fountain']
    store.configure({'area_overlap':dict.fromkeys(AREAS,.3)})
    assert store.motion_group_list(area='eating_pad')['total']==1
    assert store.jobs(mid)==before
    assert store.group_review(mid)['behaviors']==['eating','drinking']
    assert not store.events()


def test_threshold_endpoint_is_narrow_authenticated_and_persistent(tmp_path):
    store=Store(tmp_path);runtime=Runtime(store);runtime.state['review_only']=True
    with TestClient(create_app(store,runtime,False)) as client:
        path='/api/investigation/area-settings'
        body={'area_overlap':dict.fromkeys(AREAS,.2)}
        assert client.get(path).json()==body
        assert client.put(path,json=body).status_code==403
        headers={'x-catwatch-token':client.get('/api/session').json()['token']}
        assert client.put(path,json=body,headers={**headers,'origin':'https://elsewhere.test'}).status_code==403
        assert client.put(path,json={**body,'confidence':.1},headers=headers).status_code==400
        for invalid in [0,1.01,True,'20',None]:
            bad={'area_overlap':{**body['area_overlap'],'eating_pad':invalid}}
            assert client.put(path,json=bad,headers=headers).status_code==400
        assert client.put(path,json={'area_overlap':{'eating_pad':.2}},headers=headers).status_code==400
        body['area_overlap']['water_fountain']=.35
        assert client.put(path,json=body,headers=headers).status_code==200
        assert client.put('/api/config',json={'confidence':.2},headers=headers).status_code==403
    assert Store(tmp_path).config()['area_overlap']['water_fountain']==.35
