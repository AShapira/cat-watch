from copy import deepcopy
import time

import pytest

from catwatch.learning import cropped_campaign as c
from catwatch.learning import comparison as cloud


def manifest(count=18):
    box=c.BOXES['water_fountain']
    return {'authorization':c.CAMPAIGN,'budget_micros':20_000_000,'dispatch_models':[c.MODEL],
            'expires_epoch':time.time()+3600,'policies':c.POLICIES,'max_input_tokens':c.MAX_INPUT,
            'items':[{'clip_id':str(n),'target':'water_fountain','areas':['water_fountain'],
                      'crop':box,'frames':[{'width':180,'height':202} for _ in range(32)]} for n in range(count)]}


def test_new_authorization_is_separate_idempotent_and_bounded(tmp_path):
    historical=tmp_path/'cloud-comparison.sqlite3';historical.write_bytes(b'old ledger is preserved')
    budget=c.ledger(tmp_path);m=manifest();c.validate_manifest(m);budget.authorize(m)
    maximum=cloud.reservation_for(c.MODEL,manifest=m)
    assert maximum==184320 and maximum*100<20_000_000
    for item in m['items']:assert budget.reserve(item['clip_id'],c.MODEL,maximum)
    again=c.ledger(tmp_path);again.authorize(m)
    assert again.reserve('0',c.MODEL,maximum) is None
    assert again.totals()['conservative_accounted_usd']==3.31776
    assert historical.read_bytes()==b'old ledger is preserved'
    with pytest.raises(ValueError):again.reserve('0','gpt-6-astra',maximum)
    with pytest.raises(ValueError):again.authorize({**m,'expires_epoch':m['expires_epoch']+3600})


@pytest.mark.parametrize('change',['wide','mixed','full_frame','wrong_dimensions','duplicate'])
def test_manifest_rejects_broadened_or_invalid_payload(change):
    m=deepcopy(manifest())
    if change=='wide':m['items'][0]['crop']=[1125,374,1463,651]
    elif change=='mixed':m['items'][0]['areas'].append('eating_pad')
    elif change=='full_frame':m['items'][0]['crop']=[0,0,2560,1440]
    elif change=='wrong_dimensions':m['items'][0]['frames'][0]['width']=2560
    else:m['items'][1]['clip_id']=m['items'][0]['clip_id']
    with pytest.raises(ValueError):c.validate_manifest(m)


def test_only_post_tightening_unreviewed_separate_clips():
    clip={'start':c.CUTOVER+10,'duration':8,'decision':None,
          'manifest':{'areas':['water_fountain'],'crop':c.BOXES['water_fountain'],'width':2560,'height':1440}}
    assert c.validate_clip(clip)=='water_fountain'
    with pytest.raises(ValueError):c.validate_clip({**clip,'start':c.CUTOVER-1})
    with pytest.raises(ValueError):c.validate_clip({**clip,'decision':{'source':'human'}})
