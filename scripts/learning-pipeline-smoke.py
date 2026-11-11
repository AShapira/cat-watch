"""Exercise extraction, interrupted/resumed training and inference on generated data."""
import json
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import torch

from catwatch.learning.media import add_video, extract, file_hash
from catwatch.learning.store import LearningStore
from catwatch.learning.training import make_dataset, train

polygons={'eating_pad':[[0,0],[1,0],[1,1],[0,1]]}
torch.set_num_threads(2)
with tempfile.TemporaryDirectory() as folder:
    root=Path(folder); store=LearningStore(root/'learning')
    collected=set()
    for n in range(60):
        path=root/f'generated-{n}.mp4'
        writer=cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), 8, (96,96))
        for frame in range(16):
            pixels=np.full((96,96,3), (n*13+frame*3)%255, np.uint8)
            cv2.rectangle(pixels, (frame,10), (frame+30,50), (100,200,n*3), -1)
            writer.write(pixels)
        writer.release()
        ident=add_video(store,path,start=1700000000+n*86400,group_key=f'fixture-{n}',polygons=polygons)[0]
        clip=store.clip(ident)
        split=clip['split']
        # Two distinct episodes per split are sufficient to exercise mechanics,
        # deliberately far below every quality/promotion threshold.
        label='eating' if (split,'eating') not in collected else 'no_cat'
        if (split,label) not in collected:
            store.review(ident,{'version':0,'action':'review','annotation':{
                'subject':'single_cat' if label=='eating' else 'no_cat',
                'intervals':[{'start':0,'end':2,'label':label}]}})
            collected.add((split,label))
        if len(collected)==6:
            break
    assert len(collected)==6
    data=make_dataset(store)
    store.set_meta('pause_training',True)
    paused=train(store.root,data['id'])
    assert paused.get('paused') and list((store.root/'models').rglob('resume.pt'))
    store.set_meta('pause_training',False)
    completed=train(store.root,data['id'])
    record=store.model(completed['model_id'])
    assert record['state']=='shadow' and not record['body']['qualified_classes']
    assert len(record['body']['validation'])==2
    assert record['body']['test']['episodes']==2
    first=root/'generated-0.mp4'
    source=SimpleNamespace(root=root,segments=lambda:[{'start':100.,'end':102.,'path':first.name}])
    ids=extract(store,source,{'start':100.25,'end':101.75,'group_key':'extraction-fixture',
                           'session_id':1,'polygons':polygons})
    assert ids and abs(store.clip(ids[0])['duration']-1.5)<.2
    from catwatch.learning.inference import LiveClassifier
    now=time.time()
    source=SimpleNamespace(root=root,lock=threading.RLock(),segments=lambda:[
        {'id':999,'start':now-2,'end':now,'path':first.name}],
        investigation=lambda:{'id':1,'config_snapshot':{'polygons':polygons,'calibration':{'width':96,'height':96}}})
    runtime=SimpleNamespace(gpu_lock=threading.Lock(),retention=SimpleNamespace(leases={}),
        state={'detector':'ready','detection_stamp':now},detections=[])
    LiveClassifier(store,source,runtime).step()
    with store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM events WHERE source='model'").fetchone()[0] > 0
    assert runtime.retention.leases[999]==0
    print(json.dumps({'pipeline':'passed','data':'generated pixels only',
        'resume_checkpoint':True,'both_training_variants':True,'independent_test':True,
        'ffmpeg_extraction':True,'live_classifier':True,'qualified_for_alerts':False,'gpu':torch.cuda.get_device_name(0)}))
