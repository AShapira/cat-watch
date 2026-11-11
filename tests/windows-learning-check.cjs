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
    await call('Page.navigate',{url:'http://127.0.0.1:8765/#today'});
    let ready=false;
    for (let i=0; i<60; i++) {
      ready=await evaluate("Boolean(document.getElementById('reviewCount') && Number(document.getElementById('reviewCount').textContent)>0 && !document.getElementById('today').hidden)");
      if (ready) break;
      await sleep(250);
    }
    if (!ready) throw Error('Today screen did not finish loading its decision count');
    const today=await evaluate("({title:document.title,decisions:Number(document.getElementById('reviewCount').textContent),tabs:[...document.querySelectorAll('nav [data-tab]')].map(n=>n.dataset.tab),error:document.getElementById('error').hidden?null:document.getElementById('error').textContent})");
    if (today.error || !['today','decisions','timeline','learning','setup'].every(t=>today.tabs.includes(t))) throw Error('Today navigation or API error');
    await evaluate("document.querySelector('[data-tab=learning]').click()");
    let learningReady=false;
    for (let i=0; i<40; i++) {
      learningReady=await evaluate("!document.getElementById('learning').hidden && document.getElementById('learningCounts').textContent.includes('Curated clips')");
      if (learningReady) break;
      await sleep(250);
    }
    if (!learningReady) throw Error('Learning screen failed to load');
    const learning=await evaluate("({trainDisabled:document.getElementById('trainModel').disabled,progressPresent:document.getElementById('episodeProgress').textContent.includes('independent episodes'),error:document.getElementById('error').hidden?null:document.getElementById('error').textContent})");
    if (!learning.trainDisabled || !learning.progressPresent || learning.error) throw Error('Learning gates or display are incorrect');
    await call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
    await evaluate("document.querySelector('[data-tab=today]').click()");
    await sleep(500);
    const mobileFits=await evaluate('document.documentElement.scrollWidth<=window.innerWidth+1');
    if (!mobileFits || errors.length) throw Error('Mobile layout or browser runtime errors');
    const result={checked_at:new Date().toISOString(),browser:'native Windows Edge',today,learning,mobile_fits:mobileFits,javascript_errors:errors,private_images_inspected:false,labels_modified:false,calibration_modified:false};
    const output=process.argv[2] ? path.resolve(process.argv[2]) : path.join(__dirname,'../docs/development-evidence/2026-11-02-windows-ui.json');
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
