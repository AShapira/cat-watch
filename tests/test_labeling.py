import copy
import json
import os
from pathlib import Path
import shutil

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from calibration_helpers import start
from catwatch.store import Store
from catwatch.runtime import Runtime
from catwatch.web import create_app
from catwatch.labeling.contracts import normalize, source_intervals
from catwatch.labeling.storage import LabelingStore
from catwatch.labeling.media import Corpus, BudgetExceeded, CaptureResumed, sha256
from catwatch.labeling.service import LabelingService
from catwatch.labeling.predictions import prediction


def annotation(label='eating', a=1, b=10, coverage='fully_labeled', subject='single_cat', ident=1):
    return {'id':ident,'completed_by':7,'result':[
        {'id':'span','from_name':'activity','to_name':'video','type':'timelinelabels','value':{'ranges':[{'start':a,'end':b}],'timelinelabels':[label]}},
        {'from_name':'subject','to_name':'video','type':'choices','value':{'choices':[subject]}},
        {'from_name':'coverage','to_name':'video','type':'choices','value':{'choices':[coverage]}}]}


def manifest(key='test', stamp=100):
    return {'task_key':key,'dataset_id':'dataset','session_id':1,'group_id':1,'fps':10,'frame_count':10,
            'mapping':[{'start_frame':0,'end_frame':10,'capture_start':stamp,'source_hash':'a','source_start_frame':5}]}


def test_timing_inclusive_single_frame_and_gaps():
    m=manifest();a=annotation(a=1,b=1,coverage='partially_labeled')
    n=normalize(a,m);i=n['intervals'][0]
    assert (i['start_frame'],i['end_frame'],i['end_seconds'])==(0,1,.1)
    assert list(source_intervals(m,i))==[(100,100.1)]
    m['mapping']=[dict(m['mapping'][0],end_frame=5),dict(m['mapping'][0],start_frame=5,capture_start=110)]
    assert list(source_intervals(m,normalize(annotation(),m)['intervals'][0]))==[(100,100.5),(110,110.5)]


@pytest.mark.parametrize('change',[
    lambda a:a.update(was_cancelled=True),lambda a:a.update(draft=True),lambda a:a.update(result=[]),
    lambda a:a['result'][0]['value']['ranges'][0].update(start=0),
    lambda a:a['result'][0]['value']['ranges'][0].update(end=11),
    lambda a:a['result'][0]['value']['ranges'][0].update(start=1.5),
    lambda a:a['result'][0]['value']['ranges'][0].update(start=True),
    lambda a:a['result'][0]['value']['ranges'][0].update(end=9),
    lambda a:a['result'][0]['value'].update(timelinelabels=['invented']),
    lambda a:a['result'][1]['value'].update(choices=['no_cat']),
    lambda a:a['result'].append(dict(annotation('drinking')['result'][0],id='overlap'))])
def test_reject_ambiguous_or_invalid_annotations(change):
    a=annotation();change(a)
    with pytest.raises(ValueError):normalize(a,manifest())


def test_explicit_negative_partial_and_multicat():
    assert normalize(annotation('no_cat',subject='no_cat'),manifest())['supervised_eligible']
    assert not normalize(annotation(subject='multiple_cats'),manifest())['supervised_eligible']
    assert normalize(annotation(b=5,coverage='partially_labeled'),manifest())['intervals'][0]['end_frame']==5
    p=prediction([{'start_frame':0,'end_frame':1,'label':'drinking'}],manifest(),'local-v1',.5)
    assert p['result'][0]['value']['ranges']==[{'start':1,'end':1}]
    assert 'subject' not in str(p)


def test_migration_reopen_preserves_inert_labels(tmp_path):
    s=Store(tmp_path);eid=s.open_visit('eating_pad',100,101);s.close_visit(eid,101,False)
    s.correct(eid,{'behavior':'eating_observed'})
    ident=LabelingStore(s).get('dataset_id')
    s=Store(tmp_path)
    assert LabelingStore(s).get('dataset_id')==ident
    assert s.event(eid)['behavior']=='eating_observed'
    with s.db() as db:assert db.execute('PRAGMA user_version').fetchone()[0]==5


def test_revisions_replay_conflicts_deletion_and_overlap_report(tmp_path):
    db=LabelingStore(Store(tmp_path));db.add_task(manifest());task=db.tasks()[0]
    db.ingest(task,[annotation()]);db.ingest(task,[annotation()])
    with db.store.db() as sql:assert sql.execute('SELECT COUNT(*) FROM labeling_revisions').fetchone()[0]==1
    assert db.report()['activities']['eating']['seconds']==1
    db.add_task(manifest('overlap',100.5));other=db.tasks()[0 if db.tasks()[0]['task_key']=='overlap' else 1]
    db.ingest(other,[annotation('drinking',ident=2)])
    report=db.report();assert report['conflict_seconds']==.5
    assert report['activities']['eating']['seconds']==.5
    assert report['activities']['drinking']['seconds']==.5
    db.ingest(task,[annotation(),annotation(ident=3)])
    assert next(t for t in db.tasks() if t['task_key']=='test')['state']=='conflict'
    db.ingest(task,[])
    assert next(t for t in db.tasks() if t['task_key']=='test')['current_annotation'] is None


@pytest.fixture
def footage(tmp_path):
    s=Store(tmp_path/'recorder');session=start(s,now=100)
    mid=s.open_motion(session['id'],101,.1);s.update_motion(mid,103,.1);s.close_motion(mid);s.stop_investigation(now=110)
    for index,stamp in enumerate((100,110)):
        relative=f'media/{index:032x}-000000.mp4';p=s.root/relative;p.parent.mkdir(exist_ok=True)
        out=cv2.VideoWriter(str(p),cv2.VideoWriter_fourcc(*'mp4v'),10,(96,64))
        for frame in range(40):
            image=np.full((64,96,3),frame*5,np.uint8);cv2.putText(image,str(frame),(10,40),cv2.FONT_HERSHEY_SIMPLEX,.7,(0,0,255),1);out.write(image)
        out.release();s.add_segment(relative,stamp,stamp+4,p.stat().st_size)
    return s,mid


def corpus(tmp_path):
    ffmpeg=os.environ.get('CATWATCH_TEST_FFMPEG') or shutil.which('ffmpeg')
    if not ffmpeg:pytest.skip('Set CATWATCH_TEST_FFMPEG to run the real codec tests')
    return Corpus(tmp_path/'dataset','dataset',floor=0,ffmpeg=ffmpeg)


def test_native_video_export_dedup_gaps_quota_and_cancel(footage,tmp_path):
    s,gid=footage;c=corpus(tmp_path);g=s.motion_group_detail(gid)
    g['clips']=s.evidence(100,114);g['end']=114
    exported=[];c.export_group(s,g,lambda:False,exported.append)
    assert len(exported)==2
    assert all(m['dimensions']==[96,64] and m['frame_count']==40 and m['fps']==10 for m in exported)
    assert exported[1]['capture_start']==110
    assert len(list((c.root/'sources').iterdir()))==1 # byte-identical sources deduplicate
    usage=c.usage();again=[];c.export_group(s,g,lambda:False,again.append)
    assert [m['task_key'] for m in again]==[m['task_key'] for m in exported]
    assert c.usage()==usage
    with pytest.raises(CaptureResumed):c.export_group(s,g,lambda:True,lambda m:None)
    assert not list((c.root/'temporary').iterdir())
    c.cap=usage
    with pytest.raises(BudgetExceeded):c.budget(1)
    assert sha256(c.path(exported[0]['video_path']))==exported[0]['video_hash']


class FakeClient:
    url='http://127.0.0.1:8767'
    def __init__(self):self.remote={};self.lose=False
    def tasks(self,p):return list(self.remote.values())
    def request(self,path,method='GET',body=None):
        if method=='POST':
            ident=len(self.remote)+1;task={'id':ident,'data':body['data'],'annotations':[]};self.remote[ident]=task
            if self.lose:self.lose=False;raise OSError('Lost response')
            return task
        ident=int(path.strip('/').split('/')[-1])
        if method=='PATCH':self.remote[ident].update(body)
        return copy.deepcopy(self.remote[ident])


def test_lost_create_response_restart_and_deleted_task(footage,tmp_path):
    s,gid=footage;fake=FakeClient()
    cfg={'dataset_root':str(tmp_path/'corpus'),'token_file':str(tmp_path/'token'),'disk_floor_bytes':0}
    svc=LabelingService(s,Runtime(s),cfg,client=fake);svc.project_id=1
    m=manifest();m.update(group_id=gid);svc.db.add_task(m)
    svc.task_data=lambda task:{'task_key':task['task_key']}
    fake.lose=True
    with pytest.raises(OSError):svc.reconcile()
    svc.reconcile();assert len(fake.remote)==1 and svc.db.tasks()[0]['remote_id']==1
    fake.remote[1]['annotations']=[annotation()];svc.reconcile();assert svc.db.tasks()[0]['state']=='reviewed'
    svc.webhook({'action':'ANNOTATION_UPDATED','project':1,'annotation':{'task':1}})
    fake.remote.clear();svc.reconcile()
    assert svc.db.tasks()[0]['suppressed'] and svc.db.tasks()[0]['current_annotation'] is None
    svc.reconcile();assert not fake.remote


def test_disabled_ui_and_annotation_authority(tmp_path):
    s=Store(tmp_path);runtime=Runtime(s)
    with TestClient(create_app(s,runtime,False)) as c:
        assert c.get('/api/labeling/status').json()['enabled'] is False
        assert c.get('/api/activity-reports').json()['reviewed_seconds']==0
        assert c.get('/static/labeling.js').status_code==200
        assert b'groupReviewForm' not in c.get('/').content
        headers={'x-catwatch-token':c.get('/api/session').json()['token']}
        assert c.post('/api/labeling/reconcile',headers=headers).status_code==400
        assert c.post('/api/labeling/webhook',json={}).status_code==403
        for route in ['/api/events','/api/merge']:
            assert c.post(route,json={},headers=headers).status_code==410
        assert c.put('/api/investigation/groups/1/review',json={},headers=headers).status_code==410


def test_snapshot_manifest_and_tampering(footage,tmp_path):
    s,gid=footage;c=corpus(tmp_path)
    fake=FakeClient();cfg={'dataset_root':str(tmp_path/'snapshot-corpus'),'token_file':str(tmp_path/'token'),'disk_floor_bytes':0,'ffmpeg':c.ffmpeg}
    svc=LabelingService(s,Runtime(s),cfg,client=fake);svc.project_id=1
    svc.corpus.export_group(s,s.motion_group_detail(gid),lambda:False,svc.db.add_task)
    svc.task_data=lambda task:{'task_key':task['task_key']}
    svc.reconcile();t=svc.db.tasks()[0]
    fake.remote[t['remote_id']]['annotations']=[annotation('no_cat',b=t['manifest']['frame_count'],subject='no_cat')]
    ident=svc.request_snapshot()['id'];svc.snapshot(ident)
    out=svc.corpus.root/svc.snapshot_status(ident)['path'];meta=json.loads((out/'manifest.json').read_text())
    assert meta['clips']==1 and meta['intervals']==1
    rows=[json.loads(x) for x in (out/'intervals.jsonl').read_text().splitlines()]
    assert rows[0]['category']=='negative' and rows[0]['supervised_eligible']
    assert rows[0]['group_key'].endswith('/1')
    for name,digest in meta['files'].items():assert sha256(out/name)==digest
    # Recover a crash after the atomic directory move but before DB checkpoint.
    with s.db() as db:db.execute("UPDATE dataset_exports SET state='queued',path=NULL WHERE id=?",(ident,))
    svc.snapshot(ident);assert svc.snapshot_status(ident)['state']=='complete'
    video=svc.corpus.path(t['manifest']['video_path']);video.write_bytes(b'corruption')
    with pytest.raises(ValueError,match='hash mismatch'):svc.snapshot(svc.request_snapshot()['id'])


def test_export_defers_capture_and_open_motions(footage,tmp_path):
    s,gid=footage;cfg={'dataset_root':str(tmp_path/'corpus'),'token_file':str(tmp_path/'token'),'disk_floor_bytes':0}
    runtime=Runtime(s);svc=LabelingService(s,runtime,cfg,client=FakeClient());svc.queue(1)
    runtime.state['capture_busy']=True;svc.export_one();assert svc.db.jobs()[0]['state']=='queued'
    runtime.state['capture_busy']=False
    runtime.segment_queue.put('pending');assert svc.capture_busy();runtime.segment_queue.get();runtime.segment_queue.task_done()
    mid=s.open_motion(1,101,.1)
    with pytest.raises(ValueError,match='drain'):svc.queue(1)
    s.close_motion(mid)


def test_webhook_dedicated_secret_and_review_only(footage,tmp_path,monkeypatch):
    s,gid=footage;private=tmp_path/'secret';private.write_text('test-secret')
    cfg={'dataset_root':str(tmp_path/'corpus'),'token_file':str(tmp_path/'token'),'webhook_secret_file':str(private),'disk_floor_bytes':0}
    runtime=Runtime(s);runtime.state['review_only']=True
    monkeypatch.setattr(LabelingService,'start',lambda self:None)
    app=create_app(s,runtime,False);svc=LabelingService(s,runtime,cfg,client=FakeClient())
    # Factory must capture this exact service in endpoint closures.
    monkeypatch.setattr(LabelingService,'from_environment',lambda *args:svc)
    with TestClient(create_app(s,runtime,False)) as c:
        assert c.post('/api/labeling/webhook',json={'action':'ANNOTATION_UPDATED'}).status_code==403
        assert c.post('/api/labeling/webhook',json={'action':'ANNOTATION_UPDATED'},headers={'x-catwatch-labeling-token':'test-secret'}).status_code==202
        h={'x-catwatch-token':c.get('/api/session').json()['token']}
        assert c.post('/api/labeling/investigations/1/export',headers=h).status_code==202
        assert c.post('/api/investigation/stop',headers=h).status_code==403
        assert c.get('/api/activities?start=1').status_code==400


@pytest.mark.parametrize('fps,frames,expected',[(2,244,[240,4]),(14.99,1810,[1798,12])])
def test_clip_duration_limit_and_fractional_fps(tmp_path,fps,frames,expected):
    c=corpus(tmp_path);s=Store(tmp_path/'recorder');Runtime(s);session=start(s,now=100)
    relative='media/'+'b'*32+'-000000.mp4';p=s.root/relative
    writer=cv2.VideoWriter(str(p),cv2.VideoWriter_fourcc(*'mp4v'),fps,(32,24))
    for i in range(frames):writer.write(np.full((24,32,3),i%255,np.uint8))
    writer.release();s.add_segment(relative,100,100+frames/fps,p.stat().st_size)
    gid=s.open_motion(session['id'],100,.1);s.update_motion(gid,100+frames/fps,.1);s.close_motion(gid)
    exported=[];c.export_group(s,s.motion_group_detail(gid),lambda:False,exported.append)
    assert [m['frame_count'] for m in exported]==expected
    assert all(m['frame_count']/m['fps']<=120 for m in exported)
    assert exported[1]['mapping'][0]['source_start_frame']==expected[0]


def test_bad_configuration_does_not_prevent_dashboard(tmp_path,monkeypatch):
    p=tmp_path/'bad-config';p.write_text('invalid json');monkeypatch.setenv('CATWATCH_LABELING_CONFIG',str(p))
    s=Store(tmp_path/'recorder')
    with TestClient(create_app(s,Runtime(s),False)) as c:
        assert c.get('/').status_code==200
        status=c.get('/api/labeling/status').json()
        assert not status['enabled'] and status['error']
