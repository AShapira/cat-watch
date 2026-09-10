"""Isolated end-to-end group filtering, overlays, playback and review persistence."""
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
from catwatch.store import Store
from catwatch.runtime import Runtime
from catwatch.web import create_app
from test_investigation_review import add_motion, comparison


def main():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);store=Store(root)
        store.configure({'polygons':{'eating_pad':[[0,0],[.5,0],[.5,.5],[0,.5]], 'water_fountain':[[.6,.6],[.7,.6],[.7,.7]], 'litter_box':[[.8,.8],[.9,.8],[.9,.9]]}})
        cat=add_motion(store,100);continued=add_motion(store,106,group=cat)
        comparison(store,cat,[('yolo11m/1280',.85,[.1,.1,.3,.3])]);comparison(store,continued)
        quiet=add_motion(store,200);comparison(store,quiet)
        missing=add_motion(store,300,peak=0)
        store.stop_investigation(now=400)
        (root/'media').mkdir();clip=root/'media'/('a'*32+'-000001.mp4')
        shutil.copyfile(Path(__file__).parent/'fixtures/synthetic-review.mp4',clip)
        store.add_segment(str(clip.relative_to(root)),100,112,clip.stat().st_size)
        runtime=Runtime(store);runtime.state['review_only']=True
        server=uvicorn.Server(uvicorn.Config(create_app(store,runtime,False),host='127.0.0.1',port=8768,log_level='error'))
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        try:
            for _ in range(100):
                if server.started:break
                time.sleep(.05)
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True)
                page=browser.new_page(viewport={'width':1280,'height':1100})
                page.route('**/api/**',lambda route:route.fulfill(response=route.fetch(headers={**route.request.headers,'origin':'http://127.0.0.1:8765'})))
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto('http://127.0.0.1:8768/#investigation')
                expect(page.locator('#investigation')).to_be_visible()
                expect(page.locator('#motionCount')).to_contain_text('3 total groups / 4 motion entries')
                expect(page.locator('#investStart')).to_be_disabled()
                page.locator('#catQuickFilter').click()
                expect(page.locator('#motionEvents article')).to_have_count(1)
                expect(page.locator('#motionEvents')).to_contain_text('2 motion entries')
                page.locator('#motionEvents button').click()
                expect(page.locator('#motionReview')).to_be_visible()
                expect(page.locator('#reanalyzeMotion')).to_be_disabled()
                page.wait_for_function("document.getElementById('motionVideo').currentTime >= .95")
                expect(page.locator('#overlayNote')).to_contain_text('Eating pad')
                assert page.locator('#motionOverlay').evaluate('(c)=>c.width>0 && c.height>0')
                page.locator('#overlayConfidence').fill('0.95');page.locator('#overlayConfidence').press('Tab')
                expect(page.locator('#overlayNote')).to_contain_text('not a confirmed absence')
                page.locator('#overlayConfidence').fill('0.4');page.locator('#overlayConfidence').press('Tab')
                page.locator('#groupReviewStatus').select_option('cat_confirmed')
                page.locator('#groupReviewAreas input[value=eating_pad]').check()
                page.locator('#groupReviewNotes').fill('Visible cat; presence only.')
                page.locator('#saveGroupReview').click()
                expect(page.locator('#groupReviewSaved')).to_contain_text('Review saved')
                assert store.group_review(cat)['areas']==['eating_pad']
                assert not store.events()
                page.locator('#closeMotion').click()
                page.locator('#filterReview').select_option('cat_confirmed')
                page.get_by_role('button',name='Apply filters',exact=True).click()
                expect(page.locator('#motionEvents article')).to_have_count(1)
                page.locator('#motionEvents button').click()
                expect(page.locator('#groupReviewNotes')).to_have_value('Visible cat; presence only.')
                page.locator('#closeMotion').click()
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
                Path('outputs').mkdir(exist_ok=True)
                page.screenshot(path='outputs/investigation-review-smoke.png',full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
                assert not errors,errors
                browser.close()
            print('Browser passed: grouped filters, candidate seek, overlays, persistent review, read-only guards, mobile layout; no JS errors.')
        finally:
            server.should_exit=True;thread.join(timeout=10)


if __name__=='__main__':main()
