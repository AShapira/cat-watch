const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {spawn} = require('node:child_process');
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const profile=fs.mkdtempSync(path.join(os.tmpdir(),'catwatch-screens-'));
  const edge=spawn('C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', ['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:'ignore'});
  let socket,send;
  try {
    let port;
    for(let i=0;i<60;i++) {try{port=fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];break;}catch{} await sleep(250);}
    if(!port)throw Error('Isolated browser did not start');
    const browser=await (await fetch('http://127.0.0.1:'+port+'/json/version')).json();
    socket=new WebSocket(browser.webSocketDebuggerUrl);
    await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
    let next=0;const pending=new Map();
    socket.onmessage=e=>{const v=JSON.parse(e.data),p=pending.get(v.id);if(p){pending.delete(v.id);v.error?p.reject(Error(JSON.stringify(v.error))):p.resolve(v.result);}};
    send=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const id=++next;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params,sessionId}));});
    const {targetId}=await send('Target.createTarget',{url:'about:blank'});
    const {sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});
    const call=(method,params={})=>send(method,params,sessionId);
    const evaluate=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
    await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
    await call('Page.enable');
    await call('Page.navigate',{url:'http://127.0.0.1:8765'});
    for(let i=0;i<40;i++){if(await evaluate("document.querySelectorAll('#cards .card').length===3"))break;await sleep(250);}
    if(!await evaluate("document.querySelectorAll('#cards .card').length===3"))throw Error('Dashboard did not render');
    const out=path.join(__dirname,'../outputs/investigation-screens');fs.mkdirSync(out,{recursive:true});
    const capture=async(name)=>{const layout=await call('Page.getLayoutMetrics');const size=layout.cssContentSize;const shot=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,clip:{x:0,y:0,width:size.width,height:size.height,scale:1}});fs.writeFileSync(path.join(out,name+'.png'),Buffer.from(shot.data,'base64'));};
    await capture('01-overview');
    await evaluate("document.querySelector('[data-tab=visits]').click()");
    await capture('02-visits-review');
    await evaluate("document.querySelector('[data-tab=investigation]').click()");
    await sleep(1000);
    await capture('04-investigation');
    const playback=await evaluate(`(async()=>{
      const now=Date.now()/1000;
      const clips=await(await fetch('/api/evidence?start='+(now-60)+'&end='+now)).json();
      if(!clips.length)throw Error('No current source clips');
      const v=document.getElementById('motionVideo');v.muted=true;v.src='/api/clips/'+clips[clips.length-1].id;
      document.getElementById('motionReview').showModal();await v.play();
      await new Promise(r=>setTimeout(r,1500));
      const result={width:v.videoWidth,height:v.videoHeight,played_seconds:v.currentTime};
      v.pause();document.getElementById('motionReview').close();return result;
    })()`);
    if(playback.width!==2560||playback.height!==1440||playback.played_seconds<=0)throw Error(JSON.stringify(playback));
    console.log(JSON.stringify({playback}));
    const transition=await evaluate(`(async()=>{
      const data=await(await fetch('/api/investigation/motions')).json();
      const motion=data.motions.find(m=>m.clips.length>1);
      if(!motion)throw Error('Need retained multi-segment motion evidence');
      await reviewMotion(motion.id);
      const v=document.getElementById('motionVideo');v.muted=true;
      await new Promise(r=>v.addEventListener('loadedmetadata',r,{once:true}));
      v.currentTime=Math.max(0,v.duration-.3);await v.play();
      for(let i=0;i<50;i++){
        await new Promise(r=>setTimeout(r,100));
        if(document.getElementById('motionClip').value==='1'&&v.currentTime>.1)break;
      }
      const result={segment:document.getElementById('motionClip').value,played_seconds:v.currentTime,width:v.videoWidth};
      v.pause();document.getElementById('motionReview').close();return result;
    })()`);
    if(transition.segment!=='1'||transition.played_seconds<=.1||transition.width!==2560)throw Error(JSON.stringify(transition));
    console.log(JSON.stringify({transition}));
    await evaluate("document.querySelector('[data-tab=setup]').click()");
    for(let i=0;i<40;i++){if(await evaluate("document.getElementById('frameNote').textContent.startsWith('Latest analyzed frame:')"))break;await sleep(250);}
    const note=await evaluate("document.getElementById('frameNote').textContent");
    if(!note.startsWith('Latest analyzed frame:'))throw Error(note);
    await capture('03-camera-settings');
    const health=await evaluate("fetch('/api/health').then(r=>r.json())");
    fs.writeFileSync(path.join(out,'capture-info.json'),JSON.stringify({captured_at:new Date().toISOString(),camera_note:note,health},null,2));
    console.log(JSON.stringify({screens:['01-overview.png','02-visits-review.png','03-camera-settings.png','04-investigation.png'],camera_note:note,health}));
  } finally {
    if(send)await send('Browser.close').catch(()=>{});
    if(socket)socket.close();
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
