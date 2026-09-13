"""Optional isolated browser acceptance: python tests/browser_smoke.py.

Requires Playwright plus its Chromium runtime; no camera, model or containers.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
import threading
import time

import uvicorn
from playwright.sync_api import sync_playwright, expect

import cv2
import numpy as np
from catwatch.runtime import Runtime
from catwatch.store import Store
from catwatch.web import create_app


def main():
    with tempfile.TemporaryDirectory() as root:
        store=Store(root)
        eid=store.open_visit('eating_pad',time.time()-50,time.time()-30)
        store.close_visit(eid,time.time()-30,False)
        runtime=Runtime(store);runtime.frame=cv2.imencode('.jpg',np.full((540,960,3),90,np.uint8))[1].tobytes();runtime.state.update(last_frame=time.time(),source={'width':960,'height':540},camera='preview')
        server=uvicorn.Server(uvicorn.Config(create_app(store,runtime,False),host='127.0.0.1',port=8767,log_level='error'))
        thread=threading.Thread(target=server.run,daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(.05)
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True)
                page=browser.new_page(viewport={'width':1280,'height':1000})
                # Alternate port keeps this test isolated from the live Windows app.
                page.route('**/api/**',lambda route:route.fulfill(response=route.fetch(headers={**route.request.headers,'origin':'http://127.0.0.1:8765'})))
                errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto('http://127.0.0.1:8767')
                page.locator('.card').first.wait_for()
                assert page.locator('.card strong').first.inner_text()=='1'
                page.get_by_role('button',name='Camera & settings').click()
                page.wait_for_function('() => calibrationDraft !== null')
                for area,points in [('eating_pad',[(.05,.1),(.25,.1),(.25,.4)]),('water_fountain',[(.35,.1),(.55,.1),(.55,.4)]),('litter_box',[(.65,.1),(.9,.1),(.9,.4)])]:
                    page.locator('#area').select_option(area)
                    box=page.locator('#camera').bounding_box()
                    for x,y in points:
                        page.locator('#camera').click(position={'x':x*box['width'],'y':y*box['height']})
                page.locator('#saveAreas').click()
                page.wait_for_timeout(300)
                if len(store.config()['polygons'])!=3:
                    raise AssertionError({'ui_error':page.locator('#error').inner_text(), 'areas':page.evaluate('polygons'), 'errors':errors})
                expect(page.locator('#frameNote')).to_contain_text('Areas and masks saved and confirmed')
                assert len(store.config()['polygons'])==3
                calibration_id=store.preparation()['id']
                page.reload()
                expect(page.locator('#frameNote')).to_contain_text('Areas and masks saved and confirmed')
                assert store.preparation()['id']==calibration_id and store.preparation()['confirmed']
                page.get_by_role('button',name='Visits & review',exact=True).click()
                page.get_by_role('button',name='Review',exact=True).click()
                page.locator('#behavior').select_option('eating_observed')
                page.get_by_role('button',name='Save review',exact=True).click()
                expect(page.locator('#review')).not_to_be_visible()
                assert store.event(eid)['behavior']=='eating_observed'
                page.get_by_role('button',name='Overview',exact=True).click()
                expect(page.locator('#report')).to_contain_text('eating observed: 1')
                page.get_by_role('button',name='Investigation',exact=True).click()
                expect(page.locator('#investHours')).to_have_value('8')
                expect(page.locator('#motionScope')).to_have_value('areas')
                expect(page.locator('#motionBuffer')).to_have_value('20')
                expect(page.locator('#cropContext')).to_have_value('50')
                assert page.evaluate('Object.keys(bufferedOutlines).length')==3
                page.locator('#investHours').fill('0.25')
                page.locator('#motionScope').select_option('areas')
                page.locator('#investStart').click()
                expect(page.locator('#investStatus')).to_contain_text('Investigation active')
                assert store.investigation()['settings']['duration_seconds']==900
                assert store.investigation()['settings']['motion_scope']=='areas'
                expect(page.locator('#motionScope')).to_be_disabled()
                expect(page.locator('#investHours')).to_be_disabled()
                assert not store.preparation()['confirmed']
                page.get_by_role('button',name='Stop investigation',exact=True).click()
                expect(page.locator('#investStatus')).to_contain_text('Investigation ended')
                Path('outputs').mkdir(exist_ok=True)
                page.screenshot(path='outputs/fresh-refactor/dashboard-smoke.png',full_page=True)
                assert not errors, errors
                browser.close()
            print('Browser smoke passed: area drawing, review, reports, fresh calibration, focused capture settings, locking and stop; no JS errors.')
        finally:
            server.should_exit=True
            thread.join(timeout=10)


if __name__=='__main__':
    main()
