from calibration_helpers import start as begin, prepare, permit
import json

import pytest
from fastapi.testclient import TestClient

from catwatch.runtime import Runtime
from catwatch.store import Store
from catwatch.web import create_app


def add_motion(store, start, peak=.01, group=None):
    session=store.investigation() or begin(store,now=1)
    mid=store.open_motion(session['id'],start,peak,group)
    store.update_motion(mid,start+5,peak)
    store.close_motion(mid,peak==0)
    return mid


def comparison(store, mid, cats=(), models=('yolo11n/640','yolo11m/640','yolo11m/1280'), status='complete'):
    observations=[]
    for model in models:
        name,size=model.split('/')
        observations.append({'stamp':store.motion(mid)['start']+1,'model':name,'imgsz':int(size),
                             'detections':[{'label':'cat','confidence':score,'box':box} for key,score,box in cats if key==model]})
    with store.db() as db:
        jid=db.execute('INSERT INTO analysis_jobs(motion_id,kind,status,created,updated,result) VALUES (?,?,?,?,?,?)',
                       (mid,'detector_comparison',status,1,1,json.dumps({'observations':observations}))).lastrowid
    return jid


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def test_filter_before_pagination_and_group_whole_chunks(store):
    first=add_motion(store,100)
    continued=add_motion(store,106,group=first)
    newer=add_motion(store,200)
    comparison(store,first)
    comparison(store,continued,[('yolo11m/1280',.8,[.1,.1,.2,.2])])
    comparison(store,newer)
    data=store.motion_group_list(cat='detected',limit=1)
    assert data['total']==1 and data['groups'][0]['id']==first
    assert data['groups'][0]['motion_ids']==[first,continued]
    assert data['groups'][0]['best_stamp']==107
    assert data['groups'][0]['disagreement']
    assert [g['id'] for g in store.motion_group_list(cat='not_detected')['groups']]==[newer]
    assert store.motion_group_list(cat='detected',model='yolo11n/640')['total']==0
    assert store.motion_group_list(confidence=.9,cat='detected')['total']==0
    page=store.motion_group_list(limit=1)
    assert page['next_offset']==1
    assert store.motion_group_list(limit=1,offset=1)['groups'][0]['id']==first


def test_missing_and_failed_comparisons_are_not_negative_evidence(store):
    missing=add_motion(store,100,peak=0)
    failed=add_motion(store,200)
    comparison(store,failed,status='failed')
    empty=add_motion(store,300)
    comparison(store,empty)
    assert {g['id'] for g in store.motion_group_list(cat='not_detected')['groups']}=={empty}
    assert {g['id'] for g in store.motion_group_list(analysis='incomplete')['groups']}=={missing,failed}
    gap=store.motion_group_list(analysis='gap')['groups'][0]
    assert gap['peak_unknown'] and gap['id']==missing


def test_snapshot_area_assignment_and_analysis_cache_invalidation(store):
    mid=add_motion(store,100)
    jid=comparison(store,mid,[('yolo11n/640',.8,[.1,.1,.3,.3])])
    store.configure({'polygons':{'eating_pad':[[0,0],[.5,0],[.5,.5],[0,.5]], 'water_fountain':[[.6,.6],[.7,.6],[.7,.7]], 'litter_box':[[.8,.8],[.9,.8],[.9,.9]]}})
    assert store.motion_group_list(area='eating_pad')['total']==1
    detail=store.motion_group_detail(mid)
    assert detail['samples'][0]['detections'][0]['areas']==['eating_pad']
    store.configure({'polygons':{'eating_pad':[[.6,0],[.7,0],[.7,.1]], 'water_fountain':[[.6,.6],[.7,.6],[.7,.7]], 'litter_box':[[.8,.8],[.9,.8],[.9,.9]]}})
    assert store.motion_group_list(area='outside')['total']==0
    assert store.motion_group_list(area='eating_pad')['total']==1
    with store.db() as db:
        db.execute('UPDATE analysis_jobs SET updated=2,result=? WHERE id=?',
                   (json.dumps({'observations':[{'stamp':101,'model':'yolo11n','imgsz':640,'detections':[]}]}),jid))
    assert store.motion_group_list(cat='detected')['total']==0
    comparison(store,mid,status='failed')
    assert store.motion_group_list(cat='not_detected')['total']==0


def test_review_labels_allowed_without_enabling_workers_and_preserve_audit(store):
    mid=add_motion(store,100)
    original=store.motion(mid)
    store.stop_investigation(now=200)
    runtime=Runtime(store);runtime.state['review_only']=True
    app=create_app(store,runtime,False)
    with TestClient(app) as client:
        token=client.get('/api/session').json()['token'];headers={'x-catwatch-token':token}
        path=f'/api/investigation/groups/{mid}/review'
        body={'status':'cat_confirmed','areas':['eating_pad'],'behaviors':[],'notes':'Cat visible beside food','version':0}
        assert client.put(path,json=body).status_code==403
        assert client.put(path,json=body,headers={**headers,'origin':'https://elsewhere.test'}).status_code==403
        saved=client.put(path,json=body,headers=headers)
        assert saved.status_code==200 and saved.json()['version']==1
        assert client.put(path,json=body,headers=headers).status_code==409
        body.update(status='uncertain',areas=[],notes='Partly obscured',version=1)
        assert client.put(path,json=body,headers=headers).status_code==200
        detail=client.get(f'/api/investigation/groups/{mid}').json()
        assert len(detail['history'])==2
        assert detail['history'][0]['previous']['notes']=='Cat visible beside food'
        assert client.get('/api/investigation/groups?review=uncertain').json()['total']==1
        for route in ['/api/investigation','/api/investigation/stop',f'/api/investigation/motions/{mid}/analyze']:
            assert client.post(route,json={},headers=headers).status_code==403
        assert client.put('/api/config',json={'confidence':.2},headers=headers).status_code==403
    assert store.motion(mid)==original
    assert not store.events()
    restored=Store(store.root)
    assert restored.group_review(mid)['status']=='uncertain'
    assert restored.investigation()['stop']==200


def test_review_and_filter_validation(store):
    mid=add_motion(store,100)
    runtime=Runtime(store)
    with TestClient(create_app(store,runtime,False)) as client:
        headers={'x-catwatch-token':client.get('/api/session').json()['token']}
        for query in ['confidence=nan','limit=0','cat=fish','min_duration=-1','max_duration=1&min_duration=2','start=200&end=100','model=unknown']:
            assert client.get('/api/investigation/groups?'+query).status_code==400
        base={'status':'no_cat','areas':[],'behaviors':[],'notes':'','version':0}
        for patch in [{'areas':['eating_pad']},{'behaviors':[],'notes':'x'*2001},{'status':'eating'},{'version':True},{'extra':'field'}]:
            assert client.put(f'/api/investigation/groups/{mid}/review',json={**base,**patch},headers=headers).status_code==400
        assert client.put('/api/investigation/groups/999/review',json=base,headers=headers).status_code==404
        assert store.group_review(mid)['version']==0


def test_failed_rerun_keeps_previous_cat_evidence_but_marks_incomplete(store):
    mid=add_motion(store,100)
    comparison(store,mid,[('yolo11m/640',.8,[.1,.1,.2,.2])])
    comparison(store,mid,status='failed')
    group=store.motion_group_list(cat='detected')['groups'][0]
    assert group['id']==mid and not group['analysis_complete']
    assert store.motion_group_list(cat='not_detected')['total']==0
