import json
import time
from copy import deepcopy
import httpx
import pytest

from catwatch.learning import comparison as cloud
from catwatch.learning import fountain as f
from test_comparison import setup,annotation


def protocol(items):
    return {'authorization':f.CAMPAIGN,'budget_micros':cloud.BUDGET,'expires_epoch':time.time()+3600,
            'policies':deepcopy(f.POLICIES),'max_input_tokens':f.MAX_INPUT,'items':items,'prompt':f.PROMPT}


def test_total_worst_case_fits_remaining_shared_ceiling(tmp_path):
    old,_,_=setup(tmp_path)
    ident=old.reserve('0','gpt-6-astra',cloud.reservation_for('gpt-6-astra'))
    old.finish(ident,'complete',{},accounted=3_600_000,estimate=0)
    # Other old requests preserve realistic completed aggregate exposure.
    for n,amount in enumerate([3_600_000,3_600_000,1_321_210],1):
        ident=old.reserve(str(n),'gpt-6-astra',cloud.reservation_for('gpt-6-astra'))
        old.finish(ident,'complete',{},accounted=amount,estimate=0)
    ledger=cloud.Ledger(old.path,authorization=f.CAMPAIGN,clip_limit=100,allowed_models=[f.MODEL])
    m=protocol([{'clip_id':str(i)} for i in range(100)]);ledger.authorize(m)
    reservation=cloud.reservation_for(f.MODEL,manifest=m)
    assert reservation==75_360 and reservation*100==7_536_000
    for i in range(100):assert ledger.reserve(str(i),f.MODEL,reservation)
    assert ledger.totals()['conservative_accounted_usd']==19.65721
    assert ledger.reserve('0',f.MODEL,reservation) is None
    with pytest.raises(ValueError):ledger.reserve('outside',f.MODEL,reservation)


def test_frozen_limits_allow_only_lower_caps_not_discounted_prices():
    m=protocol([]);assert cloud.reservation_for(f.MODEL,manifest=m)==75_360
    for key,value in [('input_rate','0'),('effort','low'),('output_limit',99999)]:
        bad=deepcopy(m);bad['policies'][f.MODEL][key]=value
        with pytest.raises(ValueError):cloud.limits(bad,f.MODEL)
    bad=deepcopy(m);bad['max_input_tokens']=cloud.MAX_INPUT+1
    with pytest.raises(ValueError):cloud.limits(bad,f.MODEL)
    with pytest.raises(ValueError):cloud.estimate_usage({'input_tokens':6001,'output_tokens':10},f.MODEL,manifest=m)


def test_counter_over_cap_stops_before_generation_and_keeps_reservation(tmp_path):
    old,items,_=setup(tmp_path,count=1)
    ledger=cloud.Ledger(old.path,authorization=f.CAMPAIGN,clip_limit=100,allowed_models=[f.MODEL])
    m=protocol(items);ledger.authorize(m);calls=[]
    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200,json={'input_tokens':6001})
    for _ in range(2):
        cloud.cloud_one(tmp_path,ledger,items[0],f.MODEL,'fixture',client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert calls==['/v1/responses/input_tokens']
    assert ledger.requests()[0]['state']=='blocked_input_limit'
    assert ledger.requests()[0]['accounted']==75_360


def test_focus_is_native_and_inside_saved_privacy_crop():
    m={'width':2560,'height':1440,'crop':[1083,375,1593,864]}
    polygons={'water_fountain':[[.4618,.3628],[.5069,.3455],[.5387,.4664],[.4795,.5151]]}
    x,y,x2,y2=f.focus_crop(m,polygons)
    assert 1083<=x<x2<=1593 and 375<=y<y2<=864
    assert 270<x2-x<300 and 330<y2-y<370
    with pytest.raises(ValueError):f.focus_crop(m,{})


def test_selection_limits_visits_and_repeated_times():
    cs=[{'id':str(i),'start':i*14,'score':100-i,'episode_key':str(i//3),'group_key':str(i//3)} for i in range(180)]
    picked=f.select(cs)
    assert len(picked)==100 and len({x['id'] for x in picked})==100
    assert max(sum(x['episode_key']==i['episode_key'] for x in picked) for i in picked)<=2
    assert all(abs(a['start']-b['start'])>=12 for n,a in enumerate(picked) for b in picked[n+1:])


def test_review_campaign_scope_cannot_write_another_batch_clip(tmp_path):
    from fastapi.testclient import TestClient
    from test_care_campaign import fixture
    from catwatch.learning.campaign_ui import create_app
    from catwatch.learning.contracts import digest
    store,old_manifest=fixture(tmp_path)
    item={**old_manifest['items'][0],'clip_id':digest('clip1'),'focus_crop':[1,1,9,9]}
    budget=f.ledger(tmp_path);budget.authorize(protocol([item]))
    with TestClient(create_app(tmp_path)) as client:
        batches=client.get('/api/batches').json()
        assert len(batches)==2
        old=client.get('/api/batch').json()
        new=client.get('/api/batch',params={'campaign':f.CAMPAIGN}).json()
        assert new['campaign']==f.CAMPAIGN and len(new['items'])==1
        assert len(old['items'])==1
        bad='/api/clips/'+digest('clip0')+'?campaign='+f.CAMPAIGN
        assert client.get(bad).status_code==404
        assert client.put('/api/clips/'+digest('clip0')+'/decision?campaign='+f.CAMPAIGN,
            headers={'x-catwatch-token':new['token']},json={'version':0,'action':'skip'}).status_code==404
        assert store.clip(digest('clip0'))['version']==0
        assert client.get('/api/batch?campaign=unknown').status_code==404
        assert client.get('/api/clips/'+digest('clip1')+'?campaign='+f.CAMPAIGN).json()['focus_crop']==[1,1,9,9]


def test_model_scope_is_enforced_by_manifest_even_for_generic_client(tmp_path):
    ledger=f.ledger(tmp_path);m=protocol([{'clip_id':'one'}]);m['dispatch_models']=[f.MODEL];ledger.authorize(m)
    generic=cloud.Ledger(ledger.path,authorization=f.CAMPAIGN,clip_limit=100)
    with pytest.raises(ValueError,match='frozen manifest'):
        generic.reserve('one','gpt-6-astra',cloud.reservation_for('gpt-6-astra',manifest=m))
    assert not generic.requests()
