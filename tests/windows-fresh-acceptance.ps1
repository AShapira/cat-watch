# Explicit short acceptance, using isolated data and the user's saved polygons.
[CmdletBinding()]
param([string]$DataRoot='C:\Alex\data\tapo-cat-monitor')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '..\scripts\cat-watch.ps1') -Action Status -DataRoot $DataRoot
$catTestName='cat-watch-fresh-acceptance'
$catTestRoot=Join-Path $DataRoot ('acceptance-fresh-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
$catSaved=Invoke-RestMethod 'http://127.0.0.1:8765/api/calibration'
$catOriginalHealth=Invoke-RestMethod 'http://127.0.0.1:8765/api/health'
if(!$catSaved.confirmed -or !$catOriginalHealth.preparation){throw 'Expected saved calibration and idle preview'}
$catSavedJson=$catSaved|ConvertTo-Json -Depth 15 -Compress
New-Item -ItemType Directory $catTestRoot|Out-Null
'cat-watch-v1'|Set-Content (Join-Path $catTestRoot '.cat-watch-data') -Encoding ASCII
$catSavedJson|Set-Content (Join-Path $catTestRoot 'user-calibration.json') -Encoding UTF8
function Send-CatCredential([string]$Name){
 $camera=Get-Content (Join-Path $DataRoot 'camera.json') -Raw|ConvertFrom-Json
 $credential=Import-Clixml $CredentialFile
 $payload=@{ip=$camera.ip;username=$credential.UserName;password=$credential.GetNetworkCredential().Password}|ConvertTo-Json -Compress
 $previous=$ErrorActionPreference;$ErrorActionPreference='Continue'
 try {$null=$payload|& $Podman --connection $Connection exec -i $Name python -m catwatch --credentials 2>&1;$code=$LASTEXITCODE}
 finally {$payload=$null;$credential=$null;$ErrorActionPreference=$previous}
 if($code -ne 0){throw 'Credential delivery failed'}
}
function Invoke-TestApi($Path,$Body){
 $token=(Invoke-RestMethod 'http://127.0.0.1:8765/api/session').token
 Invoke-RestMethod ('http://127.0.0.1:8765'+$Path) -Method Post -ContentType 'application/json' -Headers @{'x-catwatch-token'=$token} -Body ($Body|ConvertTo-Json -Depth 15 -Compress)
}
function Wait-TestPreview {
 for($i=0;$i -lt 60;$i++){
  try {$h=Invoke-RestMethod 'http://127.0.0.1:8765/api/health';if($h.camera -eq 'preview'){return $h}}catch{}
  Start-Sleep -Seconds 1
 }
 throw 'Preview not ready'
}
function Invoke-TestPython([string]$Code){
 $previous=$ErrorActionPreference;$ErrorActionPreference='Continue'
 try {$out=$Code|& $Podman --connection $Connection exec -i $catTestName python 2>&1;$code=$LASTEXITCODE}
 finally {$ErrorActionPreference=$previous}
 if($code -ne 0){throw "Acceptance Python failed: $out"}
 return ($out -join "`n")
}
$catStopped=$false
try {
 # Stop only this project's admission controller while the isolated app owns its port.
 Get-CimInstance Win32_Process -Filter "Name='powershell.exe'"|Where-Object {$_.CommandLine -match '[\\/]analysis-controller\.ps1' -and $_.ProcessId -ne $PID}|ForEach-Object {Stop-Process -Id $_.ProcessId}
 Invoke-Podman @('--connection',$Connection,'stop','cat-watch')|Out-Null;$catStopped=$true
 $existing=Invoke-Podman @('--connection',$Connection,'ps','-a','--filter',"name=^$catTestName$",'--format','{{.Names}}')
 if($existing){
  $label=Invoke-Podman @('--connection',$Connection,'inspect',$catTestName,'--format','{{.Config.Labels.app}}')
  if($label -ne 'cat-watch-acceptance'){throw 'Unexpected acceptance container'}
  Invoke-Podman @('--connection',$Connection,'rm',$catTestName)|Out-Null
 }
 Invoke-Podman @('--connection',$Connection,'run','-d','--name',$catTestName,'--label','app=cat-watch-acceptance','--network=host','--device','nvidia.com/gpu=all','--cap-drop=all','--security-opt=no-new-privileges','--mount',"type=bind,source=$catTestRoot,target=/data",$Image)|Out-Null
 Send-CatCredential $catTestName
 $preview=Wait-TestPreview
 $draft=Invoke-TestApi '/api/calibration/prepare' @{}
 $null=Invoke-TestApi '/api/calibration/confirm' @{id=$draft.id;polygons=$catSaved.config.polygons;masks=$catSaved.masks}
 $session=Invoke-TestApi '/api/investigation' @{calibration_id=$draft.id;duration_seconds=900;motion_scope='full_frame';analysis_mode='deferred';masks=$catSaved.masks}
 # Shorten only the isolated acceptance deadline: production API minimum remains 15 minutes.
 $deadline=Invoke-TestPython @'
import time
from catwatch.store import Store
s=Store('/data')
with s.db() as db:db.execute('UPDATE investigations SET deadline=?',(time.time()+45,))
print(s.investigation()['deadline'])
'@
 Start-Sleep -Seconds 12
 $before=Invoke-RestMethod 'http://127.0.0.1:8765/api/health'
 Invoke-Podman @('--connection',$Connection,'stop',$catTestName)|Out-Null
 Invoke-Podman @('--connection',$Connection,'start',$catTestName)|Out-Null
 Send-CatCredential $catTestName
 for($i=0;$i -lt 60;$i++){
  try {$inv=Invoke-RestMethod 'http://127.0.0.1:8765/api/investigation';break}catch{Start-Sleep -Seconds 1}
 }
 if([math]::Abs([double]$inv.session.deadline-[double]$deadline) -gt .001){throw ('Restart changed deadline: '+$deadline+' vs '+$inv.session.deadline)}
 $drained=$false
 for($i=0;$i -lt 90;$i++){
  $a=Invoke-RestMethod 'http://127.0.0.1:8765/api/analysis'
  if($a.capture_drained){$drained=$true;break}
  Start-Sleep -Seconds 1
 }
 if(!$drained){throw 'Capture did not stop and drain'}
 $endHealth=Invoke-RestMethod 'http://127.0.0.1:8765/api/health'
 if($endHealth.live_model_loaded -or $endHealth.capture_busy){throw 'Capture GPU resources still active'}
 # Ensure a bounded real comparison input exists even if the room remained still.
 $evidence=Invoke-TestPython @'
import json
from catwatch.store import Store
s=Store('/data');segments=s.segments()
assert segments,'No camera video captured'
with s.db() as db:
    db.execute('DELETE FROM analysis_jobs')
    db.execute('DELETE FROM motions')
clip=next(x for x in segments if x['end']-x['start']>1)
m=s.open_motion(s.investigation()['id'],clip['start'],.001)
s.update_motion(m,min(clip['end'],clip['start']+2),.001);s.close_motion(m);s.enqueue_analysis(m)
print(json.dumps({'segments':len(segments),'seconds':sum(x['end']-x['start'] for x in segments),'motion_id':m}))
'@
 # The actual Windows scheduler uses live GPU telemetry. It preserves unrelated models.
 . (Join-Path $PSScriptRoot '..\scripts\analysis-controller.ps1') -FunctionsOnly
 $catLock=Get-Content (Join-Path $PSScriptRoot '..\scripts\cosmos.lock.json') -Raw|ConvertFrom-Json
 $catOwnerFile=Join-Path $catTestRoot 'analysis-controller-owner.json'
 $gpu=Get-CatGpu
 $state=Invoke-CatApi '/api/analysis'
 for($i=0;$i -lt 120;$i++){
  Invoke-CatAnalysisStep $state
  $state=Invoke-CatApi '/api/analysis'
  if($state.phase -in @('blocked','complete')){break}
  Start-Sleep -Seconds 1
 }
 $jobs=Invoke-RestMethod 'http://127.0.0.1:8765/api/investigation/jobs'
 $receipt=@{preview=$preview;before_restart=$before;capture_end=$endHealth;deadline=[double]$deadline;evidence=($evidence|ConvertFrom-Json);gpu=$gpu;analysis=$state;jobs=$jobs;isolated_data=$catTestRoot;production_calibration_unchanged=$true}
 $receipt|ConvertTo-Json -Depth 18|Set-Content (Join-Path $catTestRoot 'acceptance.json') -Encoding UTF8
 @{isolated_data=$catTestRoot;segments=$receipt.evidence.segments;recorded_seconds=$receipt.evidence.seconds;frames_analyzed=$endHealth.frames_analyzed;analysis=$state.phase;message=$state.message;jobs=@($jobs.jobs|Select-Object kind,status)}|ConvertTo-Json -Depth 5
} finally {
 try {Invoke-Podman @('--connection',$Connection,'stop',$catTestName)|Out-Null}catch{}
 if($catStopped){
  Invoke-Podman @('--connection',$Connection,'start','cat-watch')|Out-Null
  Send-CatCredential 'cat-watch'
  $null=Wait-TestPreview
  $after=Invoke-RestMethod 'http://127.0.0.1:8765/api/calibration'
  if(($after|ConvertTo-Json -Depth 15 -Compress) -ne $catSavedJson){throw 'Production calibration changed unexpectedly'}
 }
}
