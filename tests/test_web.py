import pytest
from fastapi.testclient import TestClient

from catwatch.runtime import Runtime
from catwatch.store import Store
from catwatch.web import create_app


@pytest.fixture
def client(tmp_path):
    store=Store(tmp_path)
    runtime=Runtime(store)
    with TestClient(create_app(store,runtime,False)) as client:
        client.store=store
        yield client


def test_local_origin_and_csrf(client):
    assert client.get('/').status_code==200
    assert client.get('/api/health',headers={'host':'evil.example'}).status_code==400
    assert client.put('/api/config',json={'storage_cap_gb':2}).status_code==403
    token=client.get('/api/session').json()['token']
    headers={'x-catwatch-token':token}
    assert client.put('/api/config',json={'storage_cap_gb':2},headers=headers).status_code==200
    assert client.put('/api/config',json={'storage_cap_gb':2},headers={**headers,'origin':'https://evil.example'}).status_code==403


def test_reviewed_behavior_only_and_export(client):
    eid=client.store.open_visit('water_fountain',100,110)
    client.store.close_visit(eid,110,False)
    data=client.get('/api/reports?start=90&end=120').json()['rows']
    fountain=next(r for r in data if r['area']=='water_fountain')
    assert fountain['visits']==1
    assert fountain['behaviors']['drinking_observed']==0
    token=client.get('/api/session').json()['token']
    r=client.patch(f'/api/events/{eid}',json={'behavior':'drinking_observed'},headers={'x-catwatch-token':token})
    assert r.status_code==410
    assert client.store.event(eid)["behavior"] == "unknown"
    assert 'drinking_observed' in client.get('/api/reports.csv?start=90&end=120').text
    assert client.get('/api/events?limit=-1').status_code==400


def test_clip_range_and_missing_media(client,tmp_path):
    name=f"media/{'a'*32}-000000.mp4"
    (tmp_path/name).write_bytes(b'0123456789')
    client.store.add_segment(name,100,110,10)
    sid=client.store.segments()[0]['id']
    r=client.get(f'/api/clips/{sid}',headers={'Range':'bytes=2-5'})
    assert r.status_code==206 and r.content==b'2345'
    assert client.get('/api/clips/9999').status_code==410
