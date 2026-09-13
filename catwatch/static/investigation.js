'use strict';
let motionMasks=[[0,0,.38,.065]],motionNext=null,motionEditing=null,motionClips=[],motionAnchor=null,motionImage=null,motionSettingsLoaded=false,sessionFiltersLoaded=false,lastGroupRefresh=0;
function motionSettings(){return {motion_buffer:Number($('motionBuffer').value)/100,crop_context:Number($('cropContext').value)/100,detector_model:'yolo11m',description_provider:'ollama',description_model:'qwen3.5:9b',description_url:'http://host.containers.internal:11434',description_timeout:Number($('descriptionTimeout').value),motion_fraction:Number($('motionFraction').value)/100,motion_seconds:Number($('motionSeconds').value),masks:motionMasks,motion_scope:$('motionScope').value,motion_fps:Number($('motionFps').value),analysis_mode:$('analysisMode').value,crop_comparison:$('cropComparison').checked,duration_seconds:Math.round(Number($('investHours').value)*3600)};}
function drawMotion(){const c=$('motionCamera'),ctx=c.getContext('2d');ctx.clearRect(0,0,c.width,c.height);if(motionImage)ctx.drawImage(motionImage,0,0,c.width,c.height);for(const [x1,y1,x2,y2] of motionMasks){ctx.fillStyle='#ef444455';ctx.fillRect(x1*c.width,y1*c.height,(x2-x1)*c.width,(y2-y1)*c.height);ctx.strokeStyle='#ff6868';ctx.strokeRect(x1*c.width,y1*c.height,(x2-x1)*c.width,(y2-y1)*c.height);}drawBufferedOutlines(ctx,c);if(motionAnchor){ctx.fillStyle='#ff6868';ctx.fillRect(motionAnchor[0]*c.width-4,motionAnchor[1]*c.height-4,8,8);}}
$('motionCamera').onclick=e=>{if(setupLocked||!calibrationDraft)return;const r=$('motionCamera').getBoundingClientRect(),p=[Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))];if(!motionAnchor)motionAnchor=p;else{const [a,b]=motionAnchor;if(Math.abs(a-p[0])>.001&&Math.abs(b-p[1])>.001&&motionMasks.length<10)motionMasks.push([Math.min(a,p[0]),Math.min(b,p[1]),Math.max(a,p[0]),Math.max(b,p[1])]);motionAnchor=null;}drawMotion();};
async function investigationHealth(){const data=await api('/api/investigation'),s=data.session,h=data.health;window.catReviewOnly=Boolean(h.review_only);
const selected=$('filterSession').value,sessionParam=new URLSearchParams(location.search).get('session_id');
$('filterSession').replaceChildren(node('option','All sessions'));$('filterSession').options[0].value='all';
for(const session of data.sessions){const o=node('option',`Session ${session.id} · ${date(session.start)}`);o.value=String(session.id);$('filterSession').append(o);}
$('filterSession').value=sessionFiltersLoaded?selected:(sessionParam&&[...$('filterSession').options].some(o=>o.value===sessionParam)?sessionParam:(sessionParam==='all'?'all':String(s?.id||'all')));sessionFiltersLoaded=true;
if(h.review_only)$('motionRetentionNote').textContent='Review-only mode: recording, model workers and automatic deletion are stopped. You can filter saved evidence and save human review labels.';$('investStatus').textContent=s?`${s.active?'Investigation active':'Investigation ended'} · ${date(s.start)} → ${date(s.end)}${s.active?' · '+duration(Math.max(0,s.end-Date.now()/1000))+' remaining':''}`:'No investigation started.';$('investStart').disabled=Boolean(h.review_only||!data.preparation?.confirmed||(s&&Date.now()/1000<s.end+5));$('investStop').disabled=Boolean(h.review_only)||!s?.active;if(s?.active&&!motionSettingsLoaded){motionMasks=structuredClone(s.settings.masks);$('motionFraction').value=s.settings.motion_fraction*100;$('motionSeconds').value=s.settings.motion_seconds;$('motionScope').value=s.settings.motion_scope;$('motionFps').value=s.settings.motion_fps;$('analysisMode').value=s.settings.analysis_mode;$('cropComparison').checked=s.settings.crop_comparison;$('investHours').value=s.settings.duration_seconds/3600;$('motionBuffer').value=(s.settings.motion_buffer??0)*100;$('cropContext').value=(s.settings.crop_context??.5)*100;$('descriptionTimeout').value=s.settings.description_timeout??180;motionSettingsLoaded=true;}
$('analysisStatus').textContent=data.analysis?.message||'Heavy analysis starts only after capture and a successful GPU check.';
$('retryAnalysis').disabled=!s||Date.now()/1000<s.end+5||['checking','processing','stage_complete'].includes(data.analysis?.phase)||Boolean(h.review_only);
for(const id of ['motionBuffer','cropContext','descriptionTimeout','motionScope','investHours','motionFraction','motionSeconds','motionFps','analysisMode','cropComparison','clearMasks','resetMasks','saveOverlap'])$(id).disabled=Boolean(s&&Date.now()/1000<s.end+5);
const items=[['Capture',h.camera],['Motion',`${h.motion_analysis} · ${h.motion_frames||0} frames · lag ${h.motion_lag_seconds??'?'}s`],['Objects',`${h.detector} · ${h.frames_analyzed||0} frames analyzed · ${h.cat_frames||0} cat frames`],['Video AI',h.video_description||'Unavailable'],['Comparison',h.detector_comparison||'Idle'],['Queue / delay',`${h.motion_queue||0} video segments · ${h.detector_queue||0} detector frames${h.motion_lag_seconds>15?' · Processing is behind':''}`],...Object.entries(h.area_motion_scores||{}).map(([a,v])=>[names[a],`${(v*100).toFixed(2)}% changed`]),['Recording gaps',`${h.capture_gaps||0} capture interruptions`],['Detector sampling',`${h.dropped_detection_frames||0} samples skipped · ${((h.frames_analyzed||0)/Math.max(1,(h.frames_analyzed||0)+(h.dropped_detection_frames||0))*100).toFixed(1)}% of submitted samples analyzed`]];$('investHealth').replaceChildren(...items.map(([title,value])=>{const el=node('div',undefined,'card');el.append(node('h3',title),node('span',value));return el;}));$('motionQuality').textContent=h.source?`Saved source: ${h.source.width} × ${h.source.height}, ${h.source.fps} fps. ${h.source.width<2560?'Camera is below the requested 1440p resolution; adjust Video Quality in Tapo.':''}`:'Waiting for source video metadata.';
if(h.review_only)$('motionQuality').textContent='Original saved video is available inside each motion group.';
}

let groupData=null,motionLoadVersion=0,groupLoadVersion=0,loadedGroupCount=0;
const reviewNames={unreviewed:'Unreviewed',cat_confirmed:'Cat confirmed',no_cat:'No cat',uncertain:'Uncertain'};
const overlapFields={eating_pad:'overlapEating',water_fountain:'overlapWater',litter_box:'overlapLitter'};
function overlapLabel(d){return d.areas.length?d.areas.map(a=>`${areaName(a)} · ${Math.round(d.overlaps[a]*100)}% overlap`).join(' + '):areaName(d.location);}
const areaName=a=>names[a]||{outside:'Outside all areas',overlap:'Overlapping areas',unknown:'Area uncertain'}[a]||a;
function groupFilters(){
  const p=new URLSearchParams({presence:$('filterPresence').value,motion_area:$('filterMotionArea').value,cat:$('filterCat').value,confidence:$('filterConfidence').value,area:$('filterArea').value,review:$('filterReview').value,model:$('filterModel').value,analysis:$('filterAnalysis').value,min_duration:$('filterMinDuration').value||'0'});
  if($('filterSession').value!=='all')p.set('session_id',$('filterSession').value);
  if($('filterDisagreement').checked)p.set('disagreement','true');
  for(const [id,key] of [['filterStart','start'],['filterEnd','end']])if($(id).value)p.set(key,String(new Date($(id).value).getTime()/1000));
  if($('filterMaxDuration').value)p.set('max_duration',$('filterMaxDuration').value);
  const url=new URL(location.href);for(const key of ['presence','cat','confidence','area','review','model','analysis','min_duration','max_duration','start','end','disagreement','session_id','motion_area']){url.searchParams.delete(key);if(p.has(key))url.searchParams.set(key,p.get(key));}if($('filterSession').value==='all')url.searchParams.set('session_id','all');history.replaceState(null,'',url);
  return p;
}
function restoreMotionFilters(){
  const p=new URLSearchParams(location.search);
  for(const [key,id] of [['presence','filterPresence'],['motion_area','filterMotionArea'],['cat','filterCat'],['confidence','filterConfidence'],['area','filterArea'],['review','filterReview'],['model','filterModel'],['analysis','filterAnalysis'],['min_duration','filterMinDuration'],['max_duration','filterMaxDuration']]){if(!p.has(key))continue;const field=$(id);if(key==='model'&&![...field.options].some(o=>o.value===p.get(key))){const o=node('option',p.get(key));o.value=p.get(key);field.append(o);}if(field.tagName==='SELECT'&&![...field.options].some(o=>o.value===p.get(key)))continue;field.value=p.get(key);}
  $('filterDisagreement').checked=p.get('disagreement')==='true';
  for(const [key,id] of [['start','filterStart'],['end','filterEnd']])if(p.has(key)&&Number.isFinite(Number(p.get(key)))){const d=new Date(Number(p.get(key))*1000);if(Number.isFinite(d.getTime()))$(id).value=new Date(d-d.getTimezoneOffset()*60000).toISOString().slice(0,16);}
}
async function loadMotions(older=false){
  const version=++motionLoadVersion,p=groupFilters();
  if(older&&motionNext!==null)p.set('offset',String(motionNext));
  $('motionMore').disabled=true;$('motionCount').textContent='Loading saved motion groups…';
  try{
    const data=await api('/api/investigation/groups?'+p);lastGroupRefresh=Date.now();
    if(version!==motionLoadVersion)return;
    const savedModel=$('filterModel').value;$('filterModel').replaceChildren(...['all',...(data.models||[])].map(m=>{const o=node('option',m==='all'?'Any saved detector':m);o.value=m;return o;}));$('filterModel').value=(data.models||[]).includes(savedModel)?savedModel:'all';
    $('areaMetrics').replaceChildren(...Object.entries(data.area_metrics).map(([a,m])=>{const c=node('div',undefined,'card');c.append(node('h3',names[a]),node('p',`${m.motion_groups} motion groups · ${m.cat_groups} cat groups`),node('small',`${m.reviewed_missed_groups} reviewed cats without a detector match`));return c;}));
    motionNext=data.next_offset;$('motionMore').hidden=motionNext===null;
    if(!older){$('motionEvents').replaceChildren();loadedGroupCount=0;}
    for(const g of data.groups){
      const card=node('article',undefined,'event');card.dataset.groupId=g.id;
      const thumb=node('img');thumb.src=`/api/investigation/groups/${g.id}/thumbnail?model=${encodeURIComponent($('filterModel').value)}`;thumb.alt=g.best_stamp?'Frame from a saved cat detection':'First retained motion frame';thumb.width=200;thumb.loading='lazy';thumb.onerror=()=>thumb.remove();card.append(thumb);
      const body=node('div',undefined,'text');body.append(node('strong',`Group #${g.id} · ${duration(g.duration)} · ${g.motion_count} motion ${g.motion_count===1?'entry':'entries'}`),node('p',`${date(g.start)} — ${date(g.end)}`));
      const tags=node('div',undefined,'group-tags');
      tags.append(node('span',g.cat_detected?'Cat candidate':g.analysis_complete?'No cat above threshold':'Analysis incomplete','tag'));
      if(g.best_confidence!==null)tags.append(node('span',`Best cat score ${g.best_confidence.toFixed(2)}`,'tag'));
      tags.append(node('span',`Human review: ${reviewNames[g.review.status]}`,'tag'));
      body.append(tags,node('p',`Motion: ${g.motion_areas.length?g.motion_areas.map(areaName).join(' · '):'Area not measured'}`),node('p',`Cat: ${g.areas.length?g.areas.map(areaName).join(' · '):'No area match at this threshold'}`));
      const peak=g.peak_unknown?(g.peak>0?`Peak at least ${(g.peak*100).toFixed(2)}%; some measurements unknown`:'Peak unknown — analysis gap'):`Peak ${(g.peak*100).toFixed(2)}%`;
      body.append(node('small',`${peak}${g.disagreement?' · Larger detector only':''}`));
      const review=node('button',g.best_stamp?'Review cat evidence':'Review movement');review.onclick=()=>reviewGroup(g.id).catch(error);card.append(body,review);$('motionEvents').append(card);
    }
    loadedGroupCount+=data.groups.length;
    $('motionCount').textContent=`Showing ${loadedGroupCount} of ${data.total} matching groups · ${data.all_groups} total groups / ${data.all_motions} motion entries. Times: Asia/Jerusalem.`;
    if(!loadedGroupCount)$('motionEvents').append(node('p','No groups match these filters. Reset filters or include incomplete analysis to broaden the review.'));
  }finally{if(version===motionLoadVersion)$('motionMore').disabled=false;}
}
function groupReviewError(e){$('motionReviewError').hidden=false;$('motionReviewError').textContent=e.message;}
function reviewAreaControls(){
  const enabled=$('groupReviewStatus').value==='cat_confirmed';$('groupBehaviors').disabled=$('groupReviewStatus').value!=='cat_confirmed';$('groupReviewAreas').disabled=!enabled;
  if(!enabled){$('groupReviewAreas').querySelectorAll('input').forEach(i=>i.checked=false);$('groupBehaviors').querySelectorAll('input').forEach(i=>i.checked=false);}
}
function fillGroupReview(){
  const r=groupData.review;$('groupReviewStatus').value=r.status;$('groupReviewNotes').value=r.notes;
  $('groupReviewAreas').querySelectorAll('input').forEach(i=>i.checked=r.areas.includes(i.value));$('groupBehaviors').querySelectorAll('input').forEach(i=>i.checked=r.behaviors.includes(i.value));reviewAreaControls();
  $('groupReviewHistory').replaceChildren(...groupData.history.map(h=>node('p',`${date(h.stamp)} · ${reviewNames[h.current.status]} · ${[...h.current.areas.map(areaName),...h.current.behaviors].join(', ')||'No labels'}${h.current.notes?' · '+h.current.notes:''}`)));
  if(!groupData.history.length)$('groupReviewHistory').append(node('p','No human review saved yet.'));
}
async function reviewGroup(id){
  const version=++groupLoadVersion;$('motionReviewError').hidden=true;$('groupReviewSaved').textContent='';
  const data=await api('/api/investigation/groups/'+id);if(version!==groupLoadVersion)return;
  groupData=data;fillAreaViews();motionEditing=data.motions[0].id;motionClips=data.clips;
  $('motionTitle').textContent=`Motion group #${id}`;
  $('motionEvidence').textContent=`${date(data.start)} — ${date(data.end)} · ${data.motions.length} motion entries · ${data.clips.length} retained source segments. Playback includes available pre/post-roll.`;
  $('reanalyzeMotion').disabled=Boolean(window.catReviewOnly)||data.motions.some(m=>m.open)||!data.clips.length;
  $('motionClip').replaceChildren(...motionClips.map((c,i)=>{const o=node('option',`${i+1}: ${date(c.start)}`);o.value=i;return o;}));
  $('overlayModel').replaceChildren(...data.models.map(m=>{const o=node('option',m);o.value=m;return o;}));
  const preferred=$('filterModel').value;
  if(data.models.includes(preferred))$('overlayModel').value=preferred;
  else if(data.samples.length){const best=data.samples.reduce((a,b)=>Math.max(...a.detections.map(d=>d.confidence))>=Math.max(...b.detections.map(d=>d.confidence))?a:b);$('overlayModel').value=best.model;}
  $('overlayConfidence').value=$('filterConfidence').value;
  $('jumpToCat').disabled=!data.samples.length;
  $('motionDescriptions').replaceChildren();
  for(const j of data.descriptions){$('motionDescriptions').append(node('p',`Motion #${j.motion_id}: ${j.status}${j.error?' · '+j.error:''}`));for(const w of j.windows)$('motionDescriptions').append(node('p',`${date(w.start)} — ${date(w.end)}: ${w.text}`));}
  if(!data.descriptions.length)$('motionDescriptions').append(node('p','No saved video description.'));
  $('motionDiagnostics').textContent=JSON.stringify({baseline_rejection_reasons:data.baseline_reasons,area_basis:data.area_basis,detectors:data.models,cat_sample_count:data.samples.length},null,2);
  fillGroupReview();
  if(!$('motionReview').open)$('motionReview').showModal();
  const best=bestOverlaySample();selectMotionClip(0,best?.stamp);drawMotionOverlay();
}
// Keep existing per-motion links compatible with grouped review.
async function reviewMotion(id){const m=await api('/api/investigation/motions/'+id);return reviewGroup(m.group_id);}
function bestOverlaySample(){
  if(!groupData)return null;
  const samples=groupData.samples.filter(s=>s.model===$('overlayModel').value&&s.detections.some(d=>d.confidence>=Number($('overlayConfidence').value)));
  return samples.reduce((a,b)=>!a||Math.max(...b.detections.map(d=>d.confidence))>Math.max(...a.detections.map(d=>d.confidence))?b:a,null);
}
function selectMotionClip(index,stamp){
  const v=$('motionVideo');v.pause();
  if(stamp!==undefined){const matched=motionClips.findIndex(c=>c.start<=stamp&&c.end>=stamp);if(matched>=0)index=matched;else{$('overlayNote').textContent='The detection timestamp has no retained video segment.';}}
  v.onloadedmetadata=null;v.removeAttribute('src');v.load();
  if(!motionClips.length){$('overlayNote').textContent='No retained video is available for this group.';drawMotionOverlay();return;}
  $('motionClip').value=index;
  v.onloadedmetadata=()=>{v.currentTime=Math.max(0,motionClips[index].play_start-motionClips[index].start);if(stamp!==undefined)v.currentTime=Math.max(motionClips[index].play_start-motionClips[index].start,Math.min(motionClips[index].play_end-motionClips[index].start-.01,stamp-motionClips[index].start));drawMotionOverlay();};
  v.src='/api/clips/'+motionClips[index].id;
}
function drawMotionOverlay(){
  drawAreaView();
  const canvas=$('motionOverlay'),v=$('motionVideo'),rect=v.getBoundingClientRect(),ctx=canvas.getContext('2d');
  canvas.width=Math.max(1,Math.round(rect.width));canvas.height=Math.max(1,Math.round(rect.height));ctx.clearRect(0,0,canvas.width,canvas.height);
  if(!groupData||!v.videoWidth||!motionClips.length)return;
  const clip=motionClips[Number($('motionClip').value)],stamp=clip.start+v.currentTime;
  const ratio=Math.min(canvas.width/v.videoWidth,canvas.height/v.videoHeight),w=v.videoWidth*ratio,h=v.videoHeight*ratio,x0=(canvas.width-w)/2,y0=(canvas.height-h)/2;
  const candidates=groupData.samples.filter(s=>s.model===$('overlayModel').value);
  const closest=candidates.reduce((a,b)=>!a||Math.abs(b.stamp-stamp)<Math.abs(a.stamp-stamp)?b:a,null);
  const sample=closest&&Math.abs(closest.stamp-stamp)<=groupData.overlay_max_age_seconds?closest:null;
  const cats=sample?sample.detections.filter(d=>d.confidence>=Number($('overlayConfidence').value)):[];
  $('overlayNote').textContent=cats.length?`${date(sample.stamp)} · ${sample.model} · ${cats.map(d=>`${d.confidence.toFixed(2)}: ${overlapLabel(d)}`).join(' · ')}`:'No saved cat box at this timestamp and threshold. This is not a confirmed absence.';
  if(!$('showMotionOverlay').checked)return;
  ctx.lineWidth=2;ctx.font='14px system-ui';
  for(const [area,pts] of Object.entries(groupData.polygons)){
    if(!pts.length)continue;ctx.strokeStyle=colors[area];ctx.fillStyle=colors[area];ctx.beginPath();pts.forEach(([x,y],i)=>i?ctx.lineTo(x0+x*w,y0+y*h):ctx.moveTo(x0+x*w,y0+y*h));ctx.closePath();ctx.stroke();ctx.fillText(names[area],x0+pts[0][0]*w,Math.max(15,y0+pts[0][1]*h-5));
  }
  for(const d of cats){const[a,b,x,y]=d.box;ctx.strokeStyle='#ffff55';ctx.fillStyle='#ffff55';ctx.strokeRect(x0+a*w,y0+b*h,(x-a)*w,(y-b)*h);ctx.fillText(`cat ${d.confidence.toFixed(2)} · ${overlapLabel(d)}`,x0+a*w,Math.max(15,y0+b*h-6));}
}
$('motionClip').onchange=()=>selectMotionClip(Number($('motionClip').value));
$('motionVideo').ontimeupdate=drawMotionOverlay;$('motionVideo').onseeked=drawMotionOverlay;
$('motionVideo').onended=()=>{const next=Number($('motionClip').value)+1;if(next<motionClips.length){selectMotionClip(next);$('motionVideo').play().catch(()=>{});}};
$('overlayModel').onchange=drawMotionOverlay;$('overlayConfidence').onchange=drawMotionOverlay;$('showMotionOverlay').onchange=drawMotionOverlay;
window.addEventListener('resize',drawMotionOverlay);
action('jumpToCat',()=>{const sample=bestOverlaySample();if(sample)selectMotionClip(0,sample.stamp);else $('overlayNote').textContent='No cat samples meet the selected model and score.';});
$('groupReviewStatus').onchange=reviewAreaControls;
$('groupReviewForm').onsubmit=async e=>{
  e.preventDefault();if(!groupData)return;const gid=groupData.id,version=groupLoadVersion;
  $('saveGroupReview').disabled=true;$('motionReviewError').hidden=true;
  try{
    const body={status:$('groupReviewStatus').value,areas:[...$('groupReviewAreas').querySelectorAll('input:checked')].map(i=>i.value),behaviors:[...$('groupBehaviors').querySelectorAll('input:checked')].map(i=>i.value),notes:$('groupReviewNotes').value,version:groupData.review.version};
    const saved=await api(`/api/investigation/groups/${gid}/review`,'PUT',body);
    if(version!==groupLoadVersion)return;
    groupData.review=saved;const fresh=await api('/api/investigation/groups/'+gid);
    if(version!==groupLoadVersion)return;groupData.history=fresh.history;fillGroupReview();$('groupReviewSaved').textContent=' Review saved.';await loadMotions();
  }catch(e){groupReviewError(e);}finally{$('saveGroupReview').disabled=false;}
};
$('motionFilters').onsubmit=e=>{e.preventDefault();loadMotions().catch(error);};
action('catQuickFilter',()=>{$('filterCat').value='detected';return loadMotions();});
action('resetMotionFilters',()=>{const session=$('filterSession').value;$('motionFilters').reset();$('filterSession').value=session;return loadMotions();});
$('filterSession').onchange=()=>loadMotions().catch(error);
action('investStart',async()=>{const prepared=await api('/api/calibration');const s=await api('/api/investigation','POST',{...motionSettings(),calibration_id:prepared?.id});calibrationDraft=null;sessionFiltersLoaded=false;const url=new URL(location.href);url.searchParams.set('session_id',s.id);history.replaceState(null,'',url);motionSettingsLoaded=false;await investigationHealth();await loadMotions();});
action('investStop',async()=>{await api('/api/investigation/stop','POST',{});await investigationHealth();});
action('investRefresh',async()=>{await investigationHealth();await loadMotions();});
action('motionMore',()=>loadMotions(true));
action('clearMasks',()=>{motionMasks=[];motionAnchor=null;drawMotion();});
action('resetMasks',()=>{motionMasks=[[0,0,.38,.065]];motionAnchor=null;drawMotion();});
action('saveMotionSettings',()=>{throw Error('Save and confirm setup before starting. Active settings are fixed.');});
action('retryAnalysis',async()=>{const sid=$('filterSession').value;await api('/api/analysis/retry','POST',sid==='all'?{}:{session_id:Number(sid)});await investigationHealth();});
action('closeMotion',()=>{$('motionVideo').pause();$('motionReview').close();});
$('motionReview').addEventListener('close',()=>{groupLoadVersion++;$('motionVideo').pause();});
action('reanalyzeMotion',async()=>{if(!groupData||window.catReviewOnly)return;for(const m of groupData.motions)if(!m.open)await api(`/api/investigation/motions/${m.id}/analyze`,'POST',{});await reviewGroup(groupData.id);});
async function investigationBoot(){restoreMotionFilters();const settings=await api('/api/investigation/area-settings');for(const [area,id] of Object.entries(overlapFields))$(id).value=Math.round(settings.area_overlap[area]*100);await investigationHealth();await loadMotions();setInterval(()=>{if(!$('investigation').hidden){investigationHealth().then(()=>{if(!window.catReviewOnly&&Date.now()-lastGroupRefresh>30000&&loadedGroupCount<=24&&!$('motionReview').open&&!document.activeElement?.closest('form'))return loadMotions();}).catch(error);}},5000);}
$('overlapForm').onsubmit=async e=>{
  e.preventDefault();$('saveOverlap').disabled=true;$('overlapError').hidden=true;$('overlapSaved').textContent='';
  try{
    const area_overlap=Object.fromEntries(Object.entries(overlapFields).map(([area,id])=>[area,Number($(id).value)/100]));
    await api('/api/investigation/area-settings','PUT',{area_overlap});config=await api('/api/config');
    await loadMotions();
    if(groupData&&$('motionReview').open)await reviewGroup(groupData.id);
    $('overlapSaved').textContent=' Next investigation thresholds saved. Confirm the calibration again before starting.';
  }catch(e){$('overlapError').textContent=e.message;$('overlapError').hidden=false;}
  finally{$('saveOverlap').disabled=false;}
};
investigationBoot().catch(error);

$('groupBehaviors').onchange=e=>{if(e.target.checked){$('groupBehaviors').querySelectorAll('input').forEach(i=>{if(i!==e.target&&(i.value==='unclear'||e.target.value==='unclear'))i.checked=false;});}};

$('motionVideo').addEventListener('timeupdate',()=>{if(!motionClips.length)return;const i=Number($('motionClip').value),c=motionClips[i],v=$('motionVideo');if(v.currentTime>=c.play_end-c.start-.04&&!v.paused){v.pause();if(i+1<motionClips.length){selectMotionClip(i+1);v.play().catch(()=>{});}}});

bindPaddedPlayback($('motionVideo'),()=>motionClips,() => Number($('motionClip').value));

// Preview and detector share the same buffered-mask implementation on the server.
let bufferedOutlines={},regionPreviewKey='',regionPreviewTimer=null;
function drawBufferedOutlines(ctx,c){ctx.save();ctx.setLineDash([8,6]);ctx.lineWidth=2;for(const[area,contours]of Object.entries(bufferedOutlines)){ctx.strokeStyle=colors[area];for(const pts of contours){ctx.beginPath();pts.forEach(([x,y],i)=>i?ctx.lineTo(x*c.width,y*c.height):ctx.moveTo(x*c.width,y*c.height));ctx.closePath();ctx.stroke();}}ctx.restore();}
function scheduleRegionPreview(){
  if(!calibrationDraft)return;
  const body={polygons,masks:motionMasks,motion_buffer:Number($('motionBuffer').value)/100},key=JSON.stringify(body);
  if(key===regionPreviewKey)return;regionPreviewKey=key;clearTimeout(regionPreviewTimer);
  regionPreviewTimer=setTimeout(async()=>{try{const d=await api('/api/investigation/preview-regions','POST',body);if(regionPreviewKey!==key)return;bufferedOutlines=d.outlines;draw();drawMotion();}catch(e){error(e);}},180);
}
$('motionBuffer').oninput=()=>scheduleRegionPreview();
$('cropContext').oninput=()=>draw();
$('motionCamera').addEventListener('click',scheduleRegionPreview);
$('clearMasks').addEventListener('click',scheduleRegionPreview);$('resetMasks').addEventListener('click',scheduleRegionPreview);
function sourceRegions(){
  if(!groupData)return [];
  const context=groupData.crop_context,regions=Object.entries(groupData.polygons).map(([area,pts])=>{const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]),dx=(Math.max(...xs)-Math.min(...xs))*context,dy=(Math.max(...ys)-Math.min(...ys))*context;return{areas:[area],box:[Math.max(0,Math.min(...xs)-dx),Math.max(0,Math.min(...ys)-dy),Math.min(1,Math.max(...xs)+dx),Math.min(1,Math.max(...ys)+dy)]};});
  const food=regions.filter(r=>['eating_pad','water_fountain'].includes(r.areas[0]));
  if(food.length===2){const[a,b]=food.map(r=>r.box);if(Math.max(a[0],b[0])<Math.min(a[2],b[2])&&Math.max(a[1],b[1])<Math.min(a[3],b[3]))return regions.filter(r=>!food.includes(r)).concat([{areas:['eating_pad','water_fountain'],box:[Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.max(a[2],b[2]),Math.max(a[3],b[3])]}]);}
  return regions;
}
function fillAreaViews(){const options=[{areas:['full'],box:[0,0,1,1]},...sourceRegions()];$('areaView').replaceChildren(...options.map(r=>{const o=node('option',r.areas[0]==='full'?'Full frame':r.areas.map(areaName).join(' + '));o.value=r.areas.join('+');return o;}));$('areaView').selectedIndex=options.length>1?1:0;}
function drawAreaView(){
  const v=$('motionVideo'),c=$('areaCanvas');if(!groupData||v.readyState<2||!v.videoWidth){$('saveAreaSnapshot').disabled=true;return;}
  $('saveAreaSnapshot').disabled=false;
  const r=sourceRegions().find(r=>r.areas.join('+')===$('areaView').value),b=r?.box||[0,0,1,1];
  const x=Math.floor(b[0]*v.videoWidth),y=Math.floor(b[1]*v.videoHeight),w=Math.ceil(b[2]*v.videoWidth)-x,h=Math.ceil(b[3]*v.videoHeight)-y;
  if(c.width!==w||c.height!==h){c.width=w;c.height=h;}c.getContext('2d').drawImage(v,x,y,w,h,0,0,w,h);
  $('areaResolution').textContent=`${w} × ${h} original source pixels · zoom enlarges display only. Snapshot excludes overlays.`;
  $('areaViewport').className='area-viewport '+$('areaZoom').value;
}
$('areaView').onchange=drawAreaView;$('areaZoom').onchange=drawAreaView;
$('motionVideo').addEventListener('play',()=>{function step(){if(!$('motionReview').open||$('motionVideo').paused)return;drawAreaView();requestAnimationFrame(step);}requestAnimationFrame(step);});
action('saveAreaSnapshot',()=>{drawAreaView();if($('saveAreaSnapshot').disabled)return;const c=$('areaCanvas');c.toBlob(blob=>{if(!blob)return;const a=document.createElement('a'),url=URL.createObjectURL(blob);a.href=url;a.download=`cat-watch-group-${groupData.id}-${$('areaView').value}-${$('motionVideo').currentTime.toFixed(2)}.png`;a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);},'image/png');});
