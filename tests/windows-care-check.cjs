// Read-only native Edge acceptance. No screenshots, footage inspection, decisions or calibration writes.
const fs = require('node:fs'), path = require('node:path'), os = require('node:os');
const {spawn} = require('node:child_process');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
(async () => {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'catwatch-learning-check-'));
  const edge = spawn('C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', [
    '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank'
  ], {stdio: 'ignore'});
  let socket, send;
  try {
    let port;
    for (let i=0; i<60; i++) {
      try {port=fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0]; break;} catch {}
      await sleep(250);
    }
    if (!port) throw Error('Isolated Edge did not start');
    const browser = await (await fetch('http://127.0.0.1:'+port+'/json/version')).json();
    socket = new WebSocket(browser.webSocketDebuggerUrl);
    await new Promise((resolve,reject) => {socket.onopen=resolve; socket.onerror=reject;});
    let id=0;
    const pending=new Map(), errors=[];
    socket.onmessage = event => {
      const value=JSON.parse(event.data), request=pending.get(value.id);
      if (request) {pending.delete(value.id); value.error?request.reject(Error(JSON.stringify(value.error))):request.resolve(value.result);}
      if (value.method==='Runtime.exceptionThrown') errors.push(value.params.exceptionDetails.text);
    };
    send = (method,params={},sessionId) => new Promise((resolve,reject) => {
      const n=++id; pending.set(n,{resolve,reject}); socket.send(JSON.stringify({id:n,method,params,sessionId}));
    });
    const {targetId} = await send('Target.createTarget',{url:'about:blank'});
    const {sessionId} = await send('Target.attachToTarget',{targetId,flatten:true});
    const call = (method,params={}) => send(method,params,sessionId);
    const evaluate = async expression => {
      const result=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
      if (result.exceptionDetails) throw Error(result.exceptionDetails.text);
      return result.result.value;
    };
    await call('Runtime.enable'); await call('Page.enable');
    await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
    await call('Page.navigate',{url:'http://127.0.0.1:8767/'});
    let ready=false;
    for (let i=0;i<100;i++) {
      ready=await evaluate("Boolean(document.getElementById('stats')?.textContent.includes('/ 100 reviewed') && document.getElementById('video')?.readyState>=2)");
      if(ready) break;
      await sleep(250);
    }
    if(!ready) throw Error('Focused review did not load its clip and video');
    await evaluate("document.getElementById('video').play()");
    await sleep(1000);
    const review=await evaluate("({title:document.title,stats:document.getElementById('stats').textContent,visibleCards:document.querySelectorAll('#queue button').length,videoReady:document.getElementById('video').readyState,videoTime:document.getElementById('video').currentTime,cropWidth:document.getElementById('canvas').width,cropHeight:document.getElementById('canvas').height,message:document.getElementById('message').textContent})");
    await evaluate("document.getElementById('video').pause()");
    if(!review.stats.includes('Training suspended')||review.videoTime<=0||!review.visibleCards) throw Error('Review readiness failed');
    await call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
    await sleep(500);
    const mobileFits=await evaluate('document.documentElement.scrollWidth<=window.innerWidth+1');
    if(!mobileFits||errors.length) throw Error('Mobile layout or JavaScript errors');
    const result={checked_at:new Date().toISOString(),browser:'native Windows Edge',review,mobile_fits:mobileFits,javascript_errors:errors,private_images_inspected:false,screenshots_taken:false,labels_modified:false};
    const output=process.argv[2] ? path.resolve(process.argv[2]) : path.join(__dirname,'../docs/development-evidence/2026-11-04-care-windows-ui.json');
    fs.mkdirSync(path.dirname(output),{recursive:true}); fs.writeFileSync(output,JSON.stringify(result,null,2)+'\n');
    console.log(JSON.stringify(result));
  } finally {
    if (send) await send('Browser.close').catch(()=>{});
    if (socket) socket.close();
    if (edge.exitCode===null) await Promise.race([new Promise(r=>edge.once('exit',r)),sleep(3000)]);
    // Only this test's newly created temporary profile is removed.
    fs.rmSync(profile,{recursive:true,force:true,maxRetries:3,retryDelay:300});
  }
})().catch(error=>{console.error(error.message); process.exitCode=1;});
