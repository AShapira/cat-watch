"""Disposable real Label Studio + browser + corpus acceptance. Never uses live ports.

python tests/label_studio_acceptance.py --label-studio /venv/bin/label-studio \
  --ffmpeg /path/to/ffmpeg --chromium /path/to/chrome --output /tmp/ls-acceptance-new
Optional --source /path/to/copied-or-readable-camera-segment.mp4 checks native footage.
Requires requirements-labeling-test.txt in a separate test environment.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
import uvicorn
from playwright.sync_api import sync_playwright
from calibration_helpers import start
from catwatch.store import Store
from catwatch.runtime import Runtime
from catwatch.labeling.client import Client
from catwatch.labeling.service import LabelingService
from catwatch.labeling.media import sha256
from test_labeling import annotation


def main():
    ap=argparse.ArgumentParser()
    for arg in ('label-studio','ffmpeg','chromium','output'):ap.add_argument('--'+arg,required=True)
    ap.add_argument('--source',default=str(Path(__file__).parent/'fixtures/synthetic-review.mp4'))
    args=ap.parse_args();root=Path(args.output).resolve()
    for port in (18769,18770):
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1',port)) == 0:
                raise RuntimeError(f'Test port {port} is occupied; refusing to use another instance')
    root.mkdir(parents=True,exist_ok=False)
    (root/'dataset').mkdir()
    for key in ('token','password','webhook'):
        p=root/key;p.write_text(secrets.token_hex(24));p.chmod(0o600)
    env=dict(os.environ,XDG_DATA_HOME=str(root/'xdg'),XDG_CACHE_HOME=str(root/'cache'),XDG_CONFIG_HOME=str(root/'config'),
        LABEL_STUDIO_USERNAME='catwatch@localhost',LABEL_STUDIO_PASSWORD=(root/'password').read_text(),
        LABEL_STUDIO_USER_TOKEN=(root/'token').read_text(),LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED='true',
        LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT=str(root/'dataset'),LABEL_STUDIO_COLLECT_ANALYTICS='false',
        LABEL_STUDIO_LATEST_VERSION_CHECK='false',LABEL_STUDIO_SENTRY_DSN='',LABEL_STUDIO_FRONTEND_SENTRY_DSN='',
        LABEL_STUDIO_DISABLE_SIGNUP_WITHOUT_LINK='true')
    log=(root/'label-studio.log').open('w')
    command=[args.label_studio,'start','--no-browser','--internal-host','127.0.0.1','--port','18769',
        '--data-dir',str(root/'state'),'--enable-legacy-api-token']
    process=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT)
    url='http://127.0.0.1:18769'
    server=thread=None
    try:
        for _ in range(240):
            if process.poll() is not None:raise RuntimeError('Label Studio startup failed; inspect the isolated log')
            try:
                with urllib.request.urlopen(url+'/health',timeout=1) as response:
                    if response.status==200:break
            except OSError:time.sleep(.5)
        else:raise TimeoutError('Label Studio startup')
        client=Client(url,root/'token','legacy')
        pat=client.request('/api/token/','POST',{})['token'];(root/'pat').write_text(pat);(root/'pat').chmod(0o600)
        client=Client(url,root/'pat')
        store=Store(root/'recorder');runtime=Runtime(store);session=start(store,now=100)
        path=store.root/'media'/'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-000000.mp4'
        shutil.copyfile(args.source,path)
        cap=cv2.VideoCapture(str(path));fps=cap.get(cv2.CAP_PROP_FPS);frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));cap.release()
        assert frames>0 and fps>0
        store.add_segment(str(path.relative_to(store.root)),100,100+frames/fps,path.stat().st_size)
        gid=store.open_motion(session['id'],100,.01);store.update_motion(gid,100+frames/fps,.01);store.close_motion(gid)
        store.stop_investigation(now=110+frames/fps)
        config={'dataset_root':str(root/'dataset'),'url':url,'token_file':str(root/'pat'),'webhook_secret_file':str(root/'webhook'),
                'callback_url':'http://127.0.0.1:18770/api/labeling/webhook','ffmpeg':args.ffmpeg,'disk_floor_bytes':0}
        service=LabelingService(store,runtime,config);service.ensure_project();service.queue(session['id']);service.export_one();service.reconcile()
        from catwatch.web import create_app
        config_path=root/'integration.json';config_path.write_text(json.dumps(config))
        previous=os.environ.get('CATWATCH_LABELING_CONFIG')
        os.environ['CATWATCH_LABELING_CONFIG']=str(config_path)
        try:app=create_app(store,runtime,False)
        finally:
            if previous is None:os.environ.pop('CATWATCH_LABELING_CONFIG',None)
            else:os.environ['CATWATCH_LABELING_CONFIG']=previous
        # Drive reconciliation explicitly in this test while using the real webhook endpoint.
        app.state.labeling.start=lambda:None
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=18770,log_level='warning'))
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        assert server.started
        with store.db() as db:queued_before=db.execute('SELECT COUNT(*) FROM labeling_sync').fetchone()[0]
        tasks=service.db.tasks();assert tasks and all(j['state']=='complete' for j in service.db.jobs())
        task=tasks[0];count=task['manifest']['frame_count'];ident=task['remote_id']
        body=annotation('no_cat',b=count,subject='no_cat')['result']
        body.append({'id':'span','from_name':'boundary','to_name':'video','type':'choices','value':{'choices':['start_outside_clip']}})
        # Seed a test annotation, then edit and save it through the real browser.
        ann=client.request(f'/api/tasks/{ident}/annotations/','POST',{'result':body})
        for _ in range(100):
            with store.db() as db:queued=db.execute('SELECT COUNT(*) FROM labeling_sync').fetchone()[0]
            if queued>queued_before:break
            time.sleep(.1)
        assert queued>queued_before, 'Actual Label Studio webhook did not reach cat-watch'
        errors=[]
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=args.chromium,headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(url+'/user/login/')
            page.locator('input[name="email"]').fill('catwatch@localhost')
            page.locator('input[name="password"]').fill((root/'password').read_text())
            page.locator('button[type="submit"]').click()
            assert page.request.get(url+'/api/current-user/whoami').status==200
            page.goto(f'{url}/projects/{service.project_id}/data?task={ident}')
            page.wait_for_function('() => document.querySelector("video")?.readyState >= 2')
            native=page.locator('video').evaluate('(v)=>[v.videoWidth,v.videoHeight]')
            assert native==task['manifest']['dimensions']
            page.wait_for_function('(n) => Htx.annotationStore.selected.names.get("video").length===n',arg=count,timeout=10000)
            # Exercise both extreme frame positions in the stock video control.
            page.evaluate('(n)=>Htx.annotationStore.selected.names.get("video").setFrame(n)',count)
            assert page.evaluate('Htx.annotationStore.selected.names.get("video").frame')==count
            page.evaluate('Htx.annotationStore.selected.names.get("video").setFrame(1)')
            page.get_by_role('link',name='Open cat-watch diagnostics').wait_for(state='attached')
            page.locator('textarea').fill('Acceptance browser round trip')
            page.locator('textarea').press('Shift+Enter')
            page.locator('button').filter(has_text='Update').click()
            page.wait_for_timeout(800)
            page.reload();page.wait_for_function('() => document.querySelector("video")?.readyState >= 2')
            page.screenshot(path=str(root/'label-studio.png'),full_page=True)
            assert not errors,errors
            browser.close()
        process.terminate();process.wait(timeout=20)
        process=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT)
        for _ in range(120):
            try:
                client.request('/api/projects/');break
            except Exception:time.sleep(.5)
        else:raise TimeoutError('Label Studio restart')
        detail=client.request(f'/api/tasks/{ident}/');assert len(detail['annotations'])==1
        result=detail['annotations'][0]['result']
        assert any(r.get('value',{}).get('text')==['Acceptance browser round trip'] for r in result)
        # A fresh bridge instance verifies restart recovery and normalized boundaries.
        service=LabelingService(store,runtime,config);service.ensure_project();service.reconcile()
        current=service.db.tasks()[0]['current_annotation'];span=current['intervals'][0]
        assert (span['start_frame'],span['end_frame'])==(0,count)
        assert span['boundary']==['start_outside_clip']
        snapshot=service.request_snapshot()['id'];service.snapshot(snapshot)
        report=service.db.report();assert report['activities']['no_cat']['seconds']>0
        export=root/'dataset'/service.snapshot_status(snapshot)['path'];meta=json.loads((export/'manifest.json').read_text())
        assert all(sha256(export/name)==digest for name,digest in meta['files'].items())
        client.request(f'/api/annotations/{ann["id"]}/','DELETE');service.reconcile()
        assert service.db.report()['reviewed_seconds']==0
        client.request(f'/api/tasks/{ident}/','DELETE');service.reconcile();assert service.db.tasks()[0]['suppressed']
        evidence={'label_studio':'1.23.0','native_dimensions':native,'fps':fps,'frames':count,
                  'browser_errors':errors,'snapshot':snapshot,'checks':['PAT refresh','project and local storage','authenticated webhook delivery','clip conversion',
                  'native playback','first/last frame','browser edit/save/reload','boundary round trip','Label Studio restart','restart reconciliation',
                  'snapshot hashes','annotation deletion','task deletion']}
        (root/'acceptance.json').write_text(json.dumps(evidence,indent=2));print(json.dumps(evidence,indent=2))
    finally:
        if server:
            server.should_exit=True;thread.join(timeout=10)
        process.terminate()
        try:process.wait(timeout=20)
        except subprocess.TimeoutExpired:process.kill();process.wait()
        log.close()


if __name__=='__main__':main()
