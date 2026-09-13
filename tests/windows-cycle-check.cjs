// Read-only acceptance for an active Windows-local investigation; never edits settings or labels.
const fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {spawn}=require('node:child_process');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const profile=fs.mkdtempSync(path.join(os.tmpdir(),'catwatch-review-'));
 const edge=spawn('C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:'ignore'});
 let socket,send;
 try{
  let port;for(let i=0;i<60;i++){try{port=fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];break;}catch{}await sleep(250);}
  if(!port)throw Error('Isolated Edge did not start');
  const browser=await(await fetch('http://127.0.0.1:'+port+'/json/version')).json();
  socket=new WebSocket(browser.webSocketDebuggerUrl);await new Promise((r,j)=>{socket.onopen=r;socket.onerror=j;});
  let id=0;const pending=new Map();socket.onmessage=e=>{const v=JSON.parse(e.data),p=pending.get(v.id);if(p){pending.delete(v.id);v.error?p.reject(Error(JSON.stringify(v.error))):p.resolve(v.result);}};
  send=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params,sessionId}));});
  const {targetId}=await send('Target.createTarget',{url:'about:blank'});const {sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});
  const call=(method,params={})=>send(method,params,sessionId);
  const evaluate=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});await call('Page.enable');
  await call('Page.navigate',{url:'http://127.0.0.1:8765/?cat=all&confidence=0.4#investigation'});
  for(let i=0;i<120;i++){if(await evaluate("window.catReviewOnly===false && document.getElementById('motionCount').textContent.includes('total groups')"))break;await sleep(500);}
  const initial=await evaluate("({text:document.getElementById('motionCount').textContent,filter:document.getElementById('filterCat').value,session:document.getElementById('filterSession').value,visible:!document.getElementById('investigation').hidden,reviewOnly:window.catReviewOnly,error:document.getElementById('error').hidden?null:document.getElementById('error').textContent})");
  if(!initial.visible||initial.reviewOnly||initial.filter!=='all'||initial.error)throw Error(JSON.stringify(initial));
  const out=path.join(__dirname,'../outputs/investigation-cycle');fs.mkdirSync(out,{recursive:true});
  await sleep(1200);let shot=await call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(out,'session-dashboard.png'),Buffer.from(shot.data,'base64'));
  await evaluate("document.querySelector('[data-tab=setup]').click()");
  for(let i=0;i<60;i++){if(await evaluate("document.getElementById('frameNote').textContent.includes('Latest analyzed frame')"))break;await sleep(500);}
  const detail=await evaluate("({cameraNote:document.getElementById('frameNote').textContent,canvasWidth:document.getElementById('camera').width})");
  shot=await call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(out,'live-camera.png'),Buffer.from(shot.data,'base64'));
  const health=await evaluate("fetch('/api/health').then(r=>r.json())");
  if(health.camera!=='connected'||health.detector!=='ready'||!health.calibrated||!health.storage.recording_allowed)throw Error(JSON.stringify(health));
  if(!health.video_description.includes('deferred')||!health.detector_comparison.includes('deferred'))throw Error('Heavy analysis is not deferred');
  const result={captured_at:new Date().toISOString(),initial,detail,health,labels_modified:false};fs.writeFileSync(path.join(out,'windows-cycle-check.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{if(send)await send('Browser.close').catch(()=>{});if(socket)socket.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
