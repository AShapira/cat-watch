'use strict';
const $=id=>document.getElementById(id);
const names={eating_pad:'Eating pad',water_fountain:'Water fountain',litter_box:'Litter box'};
const colors={eating_pad:'#3bea94',water_fountain:'#54caff',litter_box:'#ed9cf9'};
let calibrationDraft=null,setupLocked=false,cameraBusy=false;
let token='',config={},polygons={},next=null,selected=new Set(),editing=null,clips=[],frame=null,boxes=[];
const duration=s=>`${Math.floor(s/60)}m ${Math.round(s%60)}s`;
const date=s=>new Date(s*1000).toLocaleString('en-GB',{timeZone:'Asia/Jerusalem'});
const iso=s=>new Date(s*1000).toISOString();
function error(e){$('error').hidden=false;$('error').textContent=e.message;}
async function api(path,method='GET',body){const r=await fetch(path,{method,headers:{'Content-Type':'application/json','X-Catwatch-Token':token},body:body===undefined?undefined:JSON.stringify(body)});if(!r.ok){let d;try{d=await r.json();}catch{d={detail:r.statusText};}throw Error(typeof d.detail==='string'?d.detail:JSON.stringify(d.detail));}return r.json();}
function node(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
function action(id,fn){$(id).addEventListener('click',()=>Promise.resolve().then(fn).catch(error));}
function selectTabFromLocation(){
  const sections=[...document.querySelectorAll('.tab')];
  const tab=sections.find(s=>s.id===location.hash.slice(1))?.id||'overview';
  sections.forEach(s=>s.hidden=s.id!==tab);
}
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{location.hash=b.dataset.tab;});
window.addEventListener('hashchange',selectTabFromLocation);
selectTabFromLocation();
async function health(){const h=await api('/api/health');setupLocked=!h.preparation&&!h.review_only&&h.camera!=='stopped';for(const id of ['saveAreas','clear','refreshCalibration','saveSettings'])$(id).disabled=setupLocked||Boolean(h.review_only);$('health').textContent=`${h.camera} · ${h.message}${h.frame_age_seconds===null?'':` · frame ${h.frame_age_seconds}s ago`}`;const s=h.storage;$('storage').textContent=s.used_bytes===undefined?'Storage check pending':`${(s.used_bytes/1e9).toFixed(3)} / ${(s.cap_bytes/1e9).toFixed(2)} GB used · ${s.recording_allowed?'recording reserve available':'recording paused'}`;}
async function reports(){const days=$('days').value;const r=await api(`/api/reports?days=${days}`);$('export').href=`/api/reports.csv?days=${days}`;$('cards').replaceChildren();for(const [area,name] of Object.entries(names)){const rows=r.rows.filter(x=>x.area===area),sum=k=>rows.reduce((a,x)=>a+x[k],0);const c=node('div',undefined,'card');c.append(node('h3',name),node('strong',String(sum('visits'))),node('span',`${duration(sum('duration_seconds'))} in area`),node('small',`${sum('reviewed_visits')} reviewed · ${sum('interrupted_visits')} interrupted`));$('cards').append(c);}const coverage=r.rows.filter(x=>x.area==='eating_pad');const observed=coverage.reduce((a,x)=>a+x.observed_seconds,0),total=coverage.reduce((a,x)=>a+x.period_seconds,0);$('coverage').textContent=`Frames analyzed coverage: ${total?(100*observed/total).toFixed(1):0}% (${duration(observed)}). Unobserved periods are gaps, not inactivity.`;$('report').replaceChildren();for(const row of r.rows){const tr=node('tr');const behaviors=Object.entries(row.behaviors).filter(([k,v])=>v).map(([k,v])=>`${k.replaceAll('_',' ')}: ${v}`).join(', ')||'None labeled';for(const text of [row.date,names[row.area],row.visits,duration(row.duration_seconds),behaviors])tr.append(node('td',String(text)));$('report').append(tr);}}
async function events(older=false){const r=await api('/api/events'+(older&&next?`?before=${next}`:''));if(!older){$('events').replaceChildren();selected.clear();}next=r.next_before;$('more').hidden=!next;for(const e of r.events){const card=node('article',undefined,'event'),check=node('input');check.type='checkbox';check.disabled=e.open||e.rejected;check.onchange=()=>check.checked?selected.add(e.id):selected.delete(e.id);check.setAttribute('aria-label',`Select visit ${e.id}`);const text=node('div',undefined,'text');text.append(node('strong',`#${e.id} ${names[e.area]} · ${duration(e.duration_seconds)}`),node('p',`${date(e.start)} — ${date(e.end)}`),node('span',`${e.open?'In progress':e.interrupted?'Interrupted':'Completed'} · ${e.rejected?'Rejected':e.reviewed?'Reviewed':'Automatic'} · Evidence ${e.evidence}`,'tag'));const button=node('button','Review');button.disabled=e.open;button.onclick=()=>openReview(e.id).catch(error);card.append(check,text,button);$('events').append(card);}if(!$('events').children.length)$('events').append(node('p','No visits yet. Define the three areas in Camera & settings, then leave monitoring running.'));}
function setClips(items){clips=items;$('clip').replaceChildren();for(const [i,c] of items.entries()){const option=node('option',`${i+1}: ${date(c.start)} (${duration(c.end-c.start)})`);option.value=i;$('clip').append(option);}$('video').pause();$('video').removeAttribute('src');$('video').load();if(items.length)selectVisitClip(0);$('evidenceState').textContent=items.length?`${items.length} retained evidence segments. Segment boundaries may include nearby activity.`:'No retained evidence for these times.';}
async function openReview(id){editing=id;const e=id===null?{area:'eating_pad',start:Date.now()/1000-60,end:Date.now()/1000,behavior:'unknown',rejected:false,clips:[]}:await api(`/api/events/${id}`);$('reviewTitle').textContent=id===null?'Add missed visit':`Review visit #${id}`;$('editArea').value=e.area;$('start').value=iso(e.start);$('end').value=iso(e.end);$('behavior').value=e.behavior;$('rejected').checked=e.rejected;$('splitAt').value=iso((e.start+e.end)/2);$('splitTools').hidden=id===null;$('history').textContent=id===null?'Manual entry':JSON.stringify({original:e.original,history:e.history},null,2);$('reviewError').textContent='';setClips(e.clips);$('review').showModal();}
function stamp(id){const text=$(id).value;if(!/(Z|[+-]\d{2}:\d{2})$/.test(text))throw Error('Include Z or a UTC offset in each timestamp.');const v=Date.parse(text)/1000;if(!Number.isFinite(v))throw Error('Invalid timestamp');return v;}
$('reviewForm').onsubmit=async e=>{e.preventDefault();try{const body={area:$('editArea').value,start:stamp('start'),end:stamp('end'),behavior:$('behavior').value,rejected:$('rejected').checked};await api(editing===null?'/api/events':`/api/events/${editing}`,editing===null?'POST':'PATCH',body);$('review').close();await events();await reports();}catch(e){$('reviewError').textContent=e.message;}};
function selectVisitClip(index){const v=$('video');$('clip').value=String(index);v.onloadedmetadata=()=>{v.currentTime=Math.max(0,clips[index].play_start-clips[index].start);};v.src=`/api/clips/${clips[index].id}`;}
$('clip').onchange=()=>selectVisitClip(Number($('clip').value));
$('video').onended=()=>{const n=Number($('clip').value)+1;if(n<clips.length){selectVisitClip(n);$('video').play().catch(()=>{});}};
function bindPaddedPlayback(video,getClips,getIndex){
  video.addEventListener('timeupdate',()=>{
    const c=getClips()[getIndex()];if(!c||video.readyState<1)return;
    const begin=Math.max(0,c.play_start-c.start),end=Math.min(video.duration,c.play_end-c.start);
    if(video.currentTime<begin-.05){video.currentTime=begin;return;}
    if(video.currentTime>=end-.02&&!video.paused){video.pause();video.currentTime=end;video.onended?.();}
    else if(video.currentTime>end+.05)video.currentTime=end;
  });
}
bindPaddedPlayback($('video'),()=>clips,()=>Number($('clip').value));
action('close',()=>{$('video').pause();$('review').close();});
action('findEvidence',async()=>{try{setClips(await api(`/api/evidence?start=${stamp('start')}&end=${stamp('end')}`));}catch(e){$('reviewError').textContent=e.message;}});
action('split',async()=>{try{await api(`/api/events/${editing}/split`,'POST',{at:stamp('splitAt')});$('review').close();await events();await reports();}catch(e){$('reviewError').textContent=e.message;}});
action('merge',async()=>{if(selected.size!==2)throw Error('Select exactly two completed visits.');await api('/api/merge','POST',{ids:[...selected]});await events();await reports();});
action('add',()=>openReview(null));action('refresh',()=>events());action('more',()=>events(true));$('days').onchange=()=>reports().catch(error);
function draw(){if(typeof scheduleRegionPreview==='function')scheduleRegionPreview();const c=$('camera'),ctx=c.getContext('2d');ctx.clearRect(0,0,c.width,c.height);if(frame)ctx.drawImage(frame,0,0,c.width,c.height);for(const [area,pts] of Object.entries(polygons)){if(!pts.length)continue;ctx.beginPath();pts.forEach(([x,y],i)=>i?ctx.lineTo(x*c.width,y*c.height):ctx.moveTo(x*c.width,y*c.height));ctx.closePath();ctx.strokeStyle=colors[area];ctx.lineWidth=4;ctx.stroke();ctx.fillStyle=colors[area]+'30';ctx.fill();ctx.fillStyle=colors[area];ctx.font='22px sans-serif';ctx.fillText(names[area],pts[0][0]*c.width,pts[0][1]*c.height-8);}if(typeof drawBufferedOutlines==='function')drawBufferedOutlines(ctx,c);for(const d of boxes){const[a,b,x,y]=d.box;ctx.strokeStyle='#ffff55';ctx.lineWidth=3;ctx.strokeRect(a*c.width,b*c.height,(x-a)*c.width,(y-b)*c.height);ctx.fillStyle='#ffff55';ctx.fillText(`${d.label||'cat'} ${d.confidence===undefined?'':Math.round(d.confidence*100)+'%'} · ${d.areas?.length?d.areas.map(a=>names[a]).join(' + '):'Outside areas'}`,(a*c.width),Math.max(24,b*c.height-5));}}
$('camera').onclick=e=>{if(setupLocked||!calibrationDraft)return;const rect=$('camera').getBoundingClientRect(),area=$('area').value;polygons[area]??=[];if(polygons[area].length>=20)return;polygons[area].push([(e.clientX-rect.left)/rect.width,(e.clientY-rect.top)/rect.height]);draw();};
action('clear',()=>{if(setupLocked)return;polygons[$('area').value]=[];draw();});
action('saveAreas',async()=>{
  if(!calibrationDraft)throw Error('Refresh the camera image first.');
  calibrationDraft=await api('/api/calibration/confirm','POST',{id:calibrationDraft.id,polygons,masks:motionMasks});
  config=calibrationDraft.config;
  $('frameNote').textContent='Areas and masks saved and confirmed. Ready for an investigation; recording has not started.';
  await investigationHealth();
});
action('refreshCalibration',async()=>{
  await api('/api/calibration/preview','POST',{});calibrationDraft=null;
  $('frameNote').textContent='Fetching a fresh camera image…';await camera(true);
});
action('saveSettings',async()=>{config=await api('/api/config','PUT',{storage_cap_gb:Number($('cap').value),enter_seconds:Number($('enter').value),leave_seconds:Number($('leave').value),confidence:Number($('confidence').value)});await health();});
async function camera(refresh=false){
  if($('setup').hidden||setupLocked||calibrationDraft||cameraBusy)return;
  cameraBusy=true;
  try{
    const saved=await api('/api/calibration');
    if(!refresh&&saved&&!saved.used)calibrationDraft=saved;
    else{
      try{calibrationDraft=await api('/api/calibration/prepare','POST',{});}catch(e){$('frameNote').textContent=e.message;return;}
    }
    if(saved?.masks)motionMasks=structuredClone(saved.masks);
    const image=await fetch('/api/calibration/image');
    if(!image.ok)throw Error('Calibration image unavailable; refresh it.');
    if(frame)frame.close();frame=await createImageBitmap(await image.blob());
    if(motionImage)motionImage.close();motionImage=await createImageBitmap(frame);
    boxes=[];$('frameNote').textContent=calibrationDraft.confirmed?'Areas and masks saved and confirmed. Ready for an investigation; recording has not started.':`Calibration image: ${date(calibrationDraft.frame_stamp)}. Draw all three areas, review masks, then save.`;
    draw();drawMotion();
  }finally{cameraBusy=false;}
}
async function boot(){token=(await api('/api/session')).token;config=await api('/api/config');polygons=structuredClone(config.polygons);$('cap').value=config.storage_cap_gb;$('enter').value=config.enter_seconds;$('leave').value=config.leave_seconds;$('confidence').value=config.confidence;await Promise.all([health(),reports(),events()]);await camera();setInterval(()=>{health().catch(error);camera().catch(error);},5000);setInterval(()=>{if(!$('overview').hidden)reports().catch(error);if(!$('visits').hidden&&!$('review').open&&selected.size===0)events().catch(error);},30000);}
boot().catch(error);
