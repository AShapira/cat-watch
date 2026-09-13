// Run with native Windows Node 22+ against a fresh headless Edge profile on port 9227.
// Reads the deployed app and plays a clip; does not change areas or visit decisions.
const fs = require('node:fs');
const path = require('node:path');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
(async () => {
  const target = await (await fetch('http://127.0.0.1:9227/json/version')).json();
  const socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject) => {socket.onopen=resolve; socket.onerror=reject;});
  let next=0;
  const pending = new Map();
  socket.onmessage = event => {
    const item=JSON.parse(event.data), task=pending.get(item.id);
    if(task){pending.delete(item.id);item.error?task.reject(Error(JSON.stringify(item.error))):task.resolve(item.result);}
  };
  function send(method,params={},sessionId){return new Promise((resolve,reject)=>{const id=++next;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params,sessionId}));});}
  const {targetId}=await send('Target.createTarget',{url:'http://127.0.0.1:8765'});
  const {sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});
  const evaluate=async expression=>{
    const response=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true},sessionId);
    if(response.exceptionDetails)throw Error(JSON.stringify(response.exceptionDetails));
    return response.result.value;
  };
  for(let i=0;i<30;i++){
    if(await evaluate("document.querySelectorAll('#cards .card').length===3"))break;
    await sleep(500);
  }
  if(!await evaluate("document.querySelectorAll('#cards .card').length===3"))throw Error('Dashboard did not render');
  await evaluate("document.querySelector('[data-tab=setup]').click()");
  await sleep(6000);
  const media=await evaluate(`(async()=>{
    const now=Date.now()/1000;
    const clips=await(await fetch('/api/evidence?start='+(now-30)+'&end='+now)).json();
    if(!clips.length)throw Error('No camera segments');
    const video=document.getElementById('video');
    video.src='/api/clips/'+clips[clips.length-1].id;video.muted=true;
    document.getElementById('review').showModal();
    await video.play();
    await new Promise(resolve=>setTimeout(resolve,1500));
    return {width:video.videoWidth,height:video.videoHeight,duration:video.duration,played_seconds:video.currentTime};
  })()`);
  if(!(media.played_seconds>0))throw Error('Playback did not advance');
  const result={browser:target.Browser,platform:await evaluate('navigator.platform'),media};
  fs.mkdirSync(path.join(__dirname,'../outputs'),{recursive:true});
  fs.writeFileSync(path.join(__dirname,'../outputs/windows-browser-check.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify(result));
  await send('Target.closeTarget',{targetId});
  await send('Browser.close'); // This endpoint belongs only to the test's isolated profile.
  socket.close();
})().catch(error=>{console.error(error.message);process.exit(1);});
