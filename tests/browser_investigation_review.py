"""Isolated end-to-end group filtering, overlays, playback and review persistence."""
import os
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uvicorn
from playwright.sync_api import sync_playwright, expect
from calibration_helpers import start
from catwatch.store import Store
from catwatch.runtime import Runtime
from catwatch.web import create_app
from test_investigation_review import add_motion, comparison


def main():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);store=Store(root)
        store.configure({'polygons':{'eating_pad':[[0,0],[.5,0],[.5,.5],[0,.5]], 'water_fountain':[[.6,.6],[.7,.6],[.7,.7]], 'litter_box':[[.8,.8],[.9,.8],[.9,.9]]}})
        cat=add_motion(store,100);continued=add_motion(store,106,group=cat)
        comparison(store,cat,[('yolo11m/1280',.85,[.1,.4,.3,.7])]);comparison(store,continued)
        quiet=add_motion(store,200);comparison(store,quiet)
        missing=add_motion(store,300,peak=0)
        store.stop_investigation(now=400)
        (root/'media').mkdir();clip=root/'media'/('a'*32+'-000001.mp4')
        shutil.copyfile(Path(__file__).parent/'fixtures/synthetic-review.mp4',clip)
        store.add_segment(str(clip.relative_to(root)),100,112,clip.stat().st_size)
        start(store,now=500);store.stop_investigation(now=600)
        runtime=Runtime(store);runtime.state['review_only']=True
        server=uvicorn.Server(uvicorn.Config(create_app(store,runtime,False),host='127.0.0.1',port=8768,log_level='error'))
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        try:
            for _ in range(100):
                if server.started:break
                time.sleep(.05)
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True, executable_path=os.environ.get("CATWATCH_TEST_CHROMIUM"))
                page=browser.new_page(viewport={'width':1280,'height':1100})
                page.route('**/api/**',lambda route:route.fulfill(response=route.fetch(headers={**route.request.headers,'origin':'http://127.0.0.1:8765'})))
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto('http://127.0.0.1:8768/?session_id=1#investigation')
                expect(page.locator('#investigation')).to_be_visible()
                expect(page.locator('#motionCount')).to_contain_text('3 total groups / 4 motion entries')
                expect(page.locator('#investStart')).to_be_disabled()
                page.locator('#filterSession').select_option('2')
                expect(page.locator('#motionEvents article')).to_have_count(0)
                page.locator('#filterSession').select_option('1')
                expect(page.locator('#motionEvents article')).to_have_count(3)
                page.locator('#catQuickFilter').click()
                expect(page.locator('#motionEvents article')).to_have_count(1)
                expect(page.locator('#motionEvents')).to_contain_text('2 motion entries')
                page.locator('#motionEvents button').click()
                expect(page.locator('#motionReview')).to_be_visible()
                expect(page.locator('#reanalyzeMotion')).to_be_disabled()
                page.wait_for_function("() => document.getElementById('motionVideo').currentTime >= .95")
                expect(page.locator('#areaResolution')).to_contain_text('original source pixels')
                expect(page.locator('#saveAreaSnapshot')).to_be_enabled()
                page.locator('#areaZoom').select_option('zoom2')
                expect(page.locator('#areaViewport')).to_have_class('area-viewport zoom2')
                with page.expect_download() as downloaded:
                    page.locator('#saveAreaSnapshot').click()
                import cv2
                img=cv2.imread(downloaded.value.path())
                assert img.shape[1]==int(page.locator('#areaCanvas').get_attribute('width'))
                assert img.shape[0]==int(page.locator('#areaCanvas').get_attribute('height'))
                expect(page.locator('#overlayNote')).to_contain_text('Eating pad')
                expect(page.locator('#overlayNote')).to_contain_text('33% overlap')
                assert page.locator('#motionOverlay').evaluate('(c)=>c.width>0 && c.height>0')
                page.locator('#overlayConfidence').fill('0.95');page.locator('#overlayConfidence').press('Tab')
                expect(page.locator('#overlayNote')).to_contain_text('not a confirmed absence')
                page.locator('#overlayConfidence').fill('0.4');page.locator('#overlayConfidence').press('Tab')
                expect(page.locator('#groupLabeling')).to_contain_text('Activity labeling')
                assert not store.events()
                page.locator('#closeMotion').click()
                page.locator('#overlapSettings summary').click()
                page.locator('#overlapEating').fill('60')
                page.locator('#saveOverlap').click()
                expect(page.locator('#overlapSaved')).to_contain_text('Next investigation thresholds saved')
                page.locator('#filterArea').select_option('eating_pad')
                page.get_by_role('button',name='Apply filters',exact=True).click()
                expect(page.locator('#motionEvents article')).to_have_count(1)
                page.locator('#overlapEating').fill('20')
                page.locator('#saveOverlap').click()
                expect(page.locator('#motionEvents article')).to_have_count(1)
                assert store.group_review(cat)['status']=='unreviewed'
                page.locator('#overlapSettings summary').click()
                page.locator('#resetMotionFilters').click()
                expect(page.locator('#motionEvents article')).to_have_count(3)
                expect(page.locator('#motionEvents')).to_contain_text('Peak unknown — analysis gap')
                page.locator('#filterCat').select_option('not_detected')
                page.get_by_role('button',name='Apply filters',exact=True).click()
                expect(page.locator('#motionEvents article')).to_have_count(1)
                expect(page.locator('#motionEvents')).to_contain_text('Group #'+str(quiet))
                page.locator('#resetMotionFilters').click()
                page.locator('#catQuickFilter').click()
                expect(page.locator('#motionEvents article')).to_have_count(1)
                Path('outputs/fresh-refactor').mkdir(parents=True,exist_ok=True)
                page.screenshot(path='outputs/fresh-refactor/investigation-review-smoke.png',full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
                assert not errors,errors
                browser.close()
            print('Browser passed: grouped filters, candidate seek, overlays, Label Studio handoff, read-only guards, mobile layout; no JS errors.')
        finally:
            server.should_exit=True;thread.join(timeout=10)


if __name__=='__main__':main()
