"""Explicitly prepare a real image for isolated investigation fixtures."""
import time
import cv2
import numpy as np

POLYGONS = {'eating_pad':[[0,0],[.5,0],[.5,.5],[0,.5]],
            'water_fountain':[[.6,.6],[.7,.6],[.7,.7]],
            'litter_box':[[.8,.8],[.9,.8],[.9,.9]]}

def prepare(store, polygons=None, masks=None):
    jpeg=cv2.imencode('.jpg',np.zeros((100,200,3),np.uint8))[1].tobytes()
    draft=store.prepare(jpeg,time.time(),200,100)
    return store.confirm_calibration({'id':draft['id'],'polygons':polygons or store.config()['polygons'] or POLYGONS,
        'masks':[[0,0,.38,.065]] if masks is None else masks})

def start(store, updates=None, now=None):
    updates=dict(updates or {})
    draft=prepare(store,masks=updates.get('masks'))
    return store.start_investigation(dict(updates,calibration_id=draft['id']),now=now)

def permit(store, kind, session_id=None):
    state=store.request_analysis(session_id=session_id)
    return store.control_analysis({'attempt':state['attempt'],'session_id':state['session_id'],
        'phase':'processing','allowed_kind':kind})
