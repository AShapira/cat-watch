'use strict';
let labelingOffset=0, activeSnapshot=null;
function taskRow(t){
  const row=node('article',undefined,'event');
  row.append(node('strong',`Investigation ${t.session_id} · group ${t.group_id}`),node('p',t.state+(t.error?' · '+t.error:'')));
  if(t.url){const link=node('a','Review in Label Studio');link.href=t.url;link.target='_blank';link.rel='noopener';row.append(link);}
  return row;
}
async function labelingRefresh(more=false){
  const status=await api('/api/labeling/status');
  $('labelingStatus').textContent=status.enabled?`${status.reviewed} of ${status.tasks} tasks reviewed · ${status.error||'Local integration configured'}${status.last_success?' · Last sync '+date(status.last_success):''}${status.capture_busy?' · Clip export waits for capture to end':''}`:(status.error||'Label Studio is not configured. Use scripts/label-studio.ps1 and the local setup guide.');
  $('datasetUsage').textContent=`Permanent dataset: ${(status.used_bytes/1e9).toFixed(2)} / ${(status.cap_bytes/1e9).toFixed(0)} GB. Existing dataset clips are never automatically deleted.`;
  $('openLabelStudio').hidden=!status.enabled;if(status.url)$('openLabelStudio').href=status.project_id?`${status.url}/projects/${status.project_id}/data`:status.url;
  for(const id of ['retryLabeling','exportInvestigation','snapshotDataset'])$(id).disabled=!status.enabled;
  $('labelingJobs').replaceChildren(...status.jobs.map(j=>node('p',`Investigation ${j.session_id}, group ${j.group_id}: ${j.state}${j.error?' · '+j.error:''}`)));
  if(!more){labelingOffset=0;$('labelingTasks').replaceChildren();}
  const tasks=await api(`/api/labeling/tasks?offset=${labelingOffset}&limit=50`);
  $('labelingTasks').append(...tasks.tasks.map(taskRow));labelingOffset+=tasks.tasks.length;$('labelingMore').hidden=labelingOffset>=tasks.total;
  const report=await api('/api/activity-reports');
  $('activityCoverage').textContent=`${duration(report.reviewed_seconds)} reviewed · ${duration(report.activities.unclear.seconds)} unclear · ${duration(report.conflict_seconds)} conflicting. Unreviewed time is not inactivity.`;
  $('activitySummary').replaceChildren(...Object.entries(report.activities).filter(([,v])=>v.seconds>0).map(([name,value])=>{const c=node('div',undefined,'card');c.append(node('h3',name.replaceAll('_',' ')),node('strong',duration(value.seconds)),node('p',`${value.bouts} observed intervals`));return c;}));
  const investigations=await api('/api/investigation');
  const selected=$('labelingSession').value;
  $('labelingSession').replaceChildren(...investigations.sessions.map(s=>{const o=node('option',`#${s.id} · ${date(s.start)}`);o.value=s.id;return o;}));
  if(selected)$('labelingSession').value=selected;
  if(activeSnapshot){const snapshot=await api(`/api/datasets/exports/${activeSnapshot}`);$('snapshotStatus').textContent=`Dataset snapshot: ${snapshot.state}${snapshot.error?' · '+snapshot.error:''}`;
    if(snapshot.state==='complete'){$('snapshotFiles').replaceChildren(...['manifest.json','intervals.jsonl','clips.jsonl','annotations.jsonl','taxonomy.json','guide.md'].map(name=>{const p=node('p'),a=node('a',name);a.href=`/api/datasets/exports/${activeSnapshot}/files/${name}`;p.append(a);return p;}));activeSnapshot=null;}
    else if(snapshot.state==='failed')activeSnapshot=null;
  }
}
action('refreshLabeling',()=>labelingRefresh());action('labelingMore',()=>labelingRefresh(true));
action('retryLabeling',async()=>{await api('/api/labeling/reconcile','POST',{});await labelingRefresh();});
action('exportInvestigation',async()=>{const id=Number($('labelingSession').value);if(!id)throw Error('Choose an investigation');await api(`/api/labeling/investigations/${id}/export`,'POST',{});await labelingRefresh();});
action('snapshotDataset',async()=>{const r=await api('/api/datasets/exports','POST',{});activeSnapshot=r.id;$('snapshotFiles').replaceChildren();await labelingRefresh();});
labelingRefresh().catch(error);setInterval(()=>{if(!$('labeling').hidden)labelingRefresh().catch(error);},10000);
