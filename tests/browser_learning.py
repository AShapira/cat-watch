"""Browser acceptance on synthetic footage only; never uploads private footage."""
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
from catwatch.learning.media import add_video
from catwatch.runtime import Runtime
from catwatch.store import Store
from catwatch.web import create_app


def main():
    artifacts = Path(__file__).resolve().parents[1]/'.artifacts'/'learning-ui'
    artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        source = Store(folder)
        runtime = Runtime(source)
        runtime.state.update(review_only=True, message='Synthetic acceptance fixture; no camera connected')
        app = create_app(source, runtime, False)
        learning = app.state.agent.store
        ids = add_video(learning, Path(__file__).parent/'fixtures/synthetic-review.mp4',
                        start=time.time()-300, group_key='synthetic-episode', polygons=POLYGONS)
        for ident in ids:
            c = learning.clip(ident)
            learning.prediction(ident, {'subject': 'single_cat', 'quality': [], 'intervals': [
                {'start': 0, 'end': c['duration'], 'label': 'other_activity',
                 'evidence': 'Synthetic fixture for interface testing only.', 'uncertainty': 'Not a real behavior classification.'}]},
                {'provider': 'fixture', 'model': 'synthetic', 'prompt_version': 'test'})
        with learning.db() as db:
            db.execute("UPDATE clips SET bucket='difficult'")
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8768, log_level='error'))
        thread = threading.Thread(target=server.run, daemon=True); thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(.05)
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 1100})
                page.route('**/api/**', lambda route: route.fulfill(response=route.fetch(
                    headers={**route.request.headers, 'origin': 'http://127.0.0.1:8765'})))
                errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto('http://127.0.0.1:8768')
                expect(page.locator('#today')).to_be_visible()
                expect(page.locator('#reviewCount')).not_to_have_text('0')
                page.screenshot(path=str(artifacts/'today.png'), full_page=True)
                page.locator('#openDecisions').click()
                expect(page.locator('#decisionCard')).to_be_visible()
                expect(page.locator('#proposalExplanation')).to_contain_text('Synthetic fixture')
                page.wait_for_function("() => document.querySelector('#decisionVideo').readyState >= 2")
                page.wait_for_function("() => {const c=document.querySelector('#decisionCrop'); return c.getContext('2d').getImageData(10,10,1,1).data[1] > 80}")
                page.screenshot(path=str(artifacts/'decision.png'), full_page=True)
                first = page.locator('#decisionVideo').get_attribute('src').split('/')[-2]
                page.keyboard.press('1')
                page.locator('#decisionConfirm').click()
                expect(page.locator('#decisionUndo')).to_be_enabled()
                assert learning.clip(first)['decision']['intervals'][0]['label'] == 'eating'
                page.locator('#decisionUndo').click()
                expect(page.locator('#decisionUndo')).to_be_disabled()
                assert learning.clip(first)['decision'] is None
                page.locator('[data-tab=timeline]').click()
                expect(page.locator('#timelineList article')).to_have_count(len(ids))
                page.locator('[data-tab=learning]').click()
                expect(page.locator('#episodeProgress')).to_contain_text('independent episodes')
                expect(page.locator('#trainModel')).to_be_disabled()
                page.screenshot(path=str(artifacts/'learning.png'), full_page=True)
                page.set_viewport_size({'width': 390, 'height': 844})
                page.locator('[data-tab=today]').click()
                expect(page.locator('#today')).to_be_visible()
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth+1')
                page.screenshot(path=str(artifacts/'mobile.png'), full_page=True)
                assert not errors, errors
                browser.close()
            print(json.dumps({'browser': 'passed', 'synthetic_clips': len(ids), 'screenshots': str(artifacts)}))
        finally:
            server.should_exit = True
            thread.join(timeout=5)


if __name__ == '__main__':
    main()
