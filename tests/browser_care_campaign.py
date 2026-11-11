"""Browser acceptance using synthetic footage and fake Sol output only."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from playwright.sync_api import sync_playwright, expect
from calibration_helpers import POLYGONS
from catwatch.learning import campaign as c
from catwatch.learning.campaign_ui import create_app
from catwatch.learning.media import add_video
from catwatch.learning.store import LearningStore
from catwatch.learning import comparison as cloud

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory); store = LearningStore(root); store.configure({'training': False})
    ids = add_video(store, Path(__file__).parent/'fixtures/synthetic-review.mp4', start=time.time()-300,
                    group_key='synthetic-only', polygons=POLYGONS)
    items = [{'clip_id': ident, 'start': store.clip(ident)['start'], 'duration': store.clip(ident)['duration'],
              'target': c.TARGETS[n % 2], 'selection': {}, 'local_prediction': None} for n, ident in enumerate(ids)]
    manifest = {'authorization': c.CAMPAIGN, 'budget_micros': cloud.BUDGET, 'expires_epoch': time.time()+3600,
                'items': items, 'policies': cloud.POLICIES, 'max_input_tokens': cloud.MAX_INPUT, 'prompt': cloud.COMPARE_PROMPT}
    budget = c.ledger(root); budget.authorize(manifest)
    for item in items:
        annotation = {'subject': 'single_cat', 'quality': [], 'intervals': [{'start': 0, 'end': item['duration'],
                       'label': 'other_activity', 'evidence': 'Synthetic UI fixture. No real behavior claim.', 'uncertainty': ''}]}
        ident = budget.reserve(item['clip_id'], c.MODEL, cloud.reservation_for(c.MODEL))
        budget.finish(ident, 'complete', {'annotation': annotation}, accounted=0, estimate=0)
    (root/'campaigns'/c.CAMPAIGN).mkdir(parents=True)
    server = uvicorn.Server(uvicorn.Config(create_app(root), host='127.0.0.1', port=8778, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    try:
        for _ in range(100):
            if server.started: break
            time.sleep(.05)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1100})
            page.route('**/api/**', lambda route: route.fulfill(response=route.fetch(headers={**route.request.headers, 'origin':'http://127.0.0.1:8767'})))
            errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto('http://127.0.0.1:8778/')
            expect(page.locator('#evidence')).to_contain_text('Synthetic UI fixture')
            page.wait_for_function("() => document.querySelector('#video').readyState >= 2")
            page.locator('#play').click()
            page.wait_for_function("() => video.currentTime > .2")
            page.wait_for_function("() => {const a=ctx.getImageData(0,0,canvas.width,canvas.height).data;return a.some((v,i)=>i%4!==3&&v>80)}")
            page.locator('#play').click()
            first = page.locator('#video').get_attribute('src').split('/')[-2]
            page.locator('#intervals select').select_option('drinking')
            page.locator('#accept').click()
            expect(page.locator('#stats')).to_contain_text('1 / 100 reviewed')
            decision = store.clip(first)['decision']
            assert decision['intervals'][0]['label'] == 'drinking' and decision['independent'] is False
            page.locator('#status').select_option('accepted'); page.locator('#queue button').first.click()
            page.locator('#undo').click()
            expect(page.locator('#stats')).to_contain_text('0 / 100 reviewed')
            assert store.clip(first)['decision'] is None
            page.locator('#status').select_option('pending')
            page.locator('#skip').click()
            expect(page.locator('#queue button')).to_have_count(len(items)-1)
            assert store.clip(first)['decision'] is None
            artifacts = Path('.artifacts/care-review'); artifacts.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(artifacts/'desktop.png'), full_page=True)
            page.set_viewport_size({'width': 390, 'height': 844})
            page.screenshot(path=str(artifacts/'mobile.png'), full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
            assert not errors, errors
            assert store.config()['training'] is False
            browser.close()
            print(json.dumps({'browser': 'passed', 'fixture_only': True, 'checks': ['cropped playback','edit/accept','assisted provenance','undo','skip','desktop/mobile','no JS errors']}))
    finally:
        server.should_exit = True; thread.join(timeout=5)
