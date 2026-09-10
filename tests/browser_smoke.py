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

from catwatch.runtime import Runtime
from catwatch.store import Store
from catwatch.web import create_app


def main():
    with tempfile.TemporaryDirectory() as root:
        store=Store(root)
        eid=store.open_visit('eating_pad',time.time()-50,time.time()-30)
        store.close_visit(eid,time.time()-30,False)
        server=uvicorn.Server(uvicorn.Config(create_app(store,Runtime(store),False),host='127.0.0.1',port=8767,log_level='error'))
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
                for area,points in [('eating_pad',[(.05,.1),(.25,.1),(.25,.4)]),('water_fountain',[(.35,.1),(.55,.1),(.55,.4)]),('litter_box',[(.65,.1),(.9,.1),(.9,.4)])]:
                    page.locator('#area').select_option(area)
                    box=page.locator('#camera').bounding_box()
                    for x,y in points:
                        page.locator('#camera').click(position={'x':x*box['width'],'y':y*box['height']})
                page.get_by_role('button',name='Save all areas').click()
                page.wait_for_timeout(300)
                if len(store.config()['polygons'])!=3:
                    raise AssertionError({'ui_error':page.locator('#error').inner_text(), 'areas':page.evaluate('polygons'), 'errors':errors})
                expect(page.locator('#frameNote')).to_contain_text('Areas saved')
                assert len(store.config()['polygons'])==3
                page.get_by_role('button',name='Visits & review',exact=True).click()
                page.get_by_role('button',name='Review',exact=True).click()
                page.locator('#behavior').select_option('eating_observed')
                page.get_by_role('button',name='Save review',exact=True).click()
                expect(page.locator('#review')).not_to_be_visible()
                assert store.event(eid)['behavior']=='eating_observed'
                page.get_by_role('button',name='Overview',exact=True).click()
                expect(page.locator('#report')).to_contain_text('eating observed: 1')
                page.get_by_role('button',name='Investigation',exact=True).click()
                page.get_by_role('button',name='Start 24-hour investigation',exact=True).click()
                expect(page.locator('#investStatus')).to_contain_text('Investigation active')
                deadline=store.investigation()['deadline']
                page.get_by_text('Motion sensitivity and excluded overlays',exact=True).click()
                page.get_by_role('button',name='Clear masks',exact=True).click()
                page.get_by_role('button',name='Apply to active investigation',exact=True).click()
                page.wait_for_timeout(300)
                assert store.investigation()['settings']['masks']==[]
                assert store.investigation()['deadline']==deadline
                page.get_by_role('button',name='Stop investigation',exact=True).click()
                expect(page.locator('#investStatus')).to_contain_text('Investigation ended')
                Path('outputs').mkdir(exist_ok=True)
                page.screenshot(path='outputs/dashboard-smoke.png',full_page=True)
                assert not errors, errors
                browser.close()
            print('Browser smoke passed: area drawing, review, reports, investigation start/masks/stop; no JS errors.')
        finally:
            server.should_exit=True
            thread.join(timeout=10)


if __name__=='__main__':
    main()
