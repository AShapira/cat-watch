# Runs the real controller's single-step scheduler with engine/network boundaries replaced.
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '..\scripts\analysis-controller.ps1') -FunctionsOnly
$catLock=Get-Content (Join-Path $PSScriptRoot '..\scripts\cosmos.lock.json') -Raw|ConvertFrom-Json
$catOwnerFile=Join-Path ([IO.Path]::GetTempPath()) ('cat-controller-test-'+[guid]::NewGuid()+'.json')
$Connection='test';$Machine='test'
function Assert($Condition,$Message){if(!$Condition){throw $Message}}
function Reset-State {
 $script:state=[pscustomobject]@{session_id=1;attempt=1;phase='checking';allowed_kind=$null;owner=$null;checked_kinds=@();skipped=@();capture_drained=$true;pending=@{video_description=1;detector_comparison=1};message=''}
 $script:gpuCalls=0;$script:readyCalls=0;$script:starts=0;$script:stops=0;$script:ready=$false;$script:failStart=$false;$script:failGpu=$false;$script:free=16000;$script:started=$false
}
function Get-CatGpu {$script:gpuCalls++;if($script:failGpu){throw 'GPU unavailable'};return @{total=16000;free=$script:free}}
function Test-CatCosmos {$script:readyCalls++;return $script:ready}
function Start-CatCosmos {$script:starts++;if($script:failStart){throw 'Startup failed'};$script:ready=$true;$script:started=$true}
function Invoke-CatApi($Path,$Method='GET',$Body=$null) {
 if($Path -eq '/api/analysis/control'){
  foreach($k in $Body.Keys){$script:state.$k=$Body[$k]}
 }elseif($Path -eq '/api/analysis/retry'){$script:state.phase='checking';$script:state.attempt++}
 return $script:state
}
function Invoke-Podman($Arguments) {
 if($Arguments -contains 'ps'){return ''}
 if($Arguments -contains 'inspect'){return '[{"Id":"owned-1","State":{"StartedAt":"stamp-1"},"Config":{"Labels":{"app":"cat-watch-cosmos"}}}]'}
 if($Arguments -contains 'stop'){$script:stops++;return ''}
 throw 'Unexpected engine operation'
}
try {
 Reset-State;$script:free=100
 Invoke-CatAnalysisStep $state
 Assert ($state.phase -eq 'blocked' -and $starts -eq 0 -and $state.skipped.Count -eq 2) 'Insufficient capacity should queue both stages'
 $calls=$gpuCalls+$readyCalls
 1..3|ForEach-Object {Invoke-CatAnalysisStep $state}
 Assert (($gpuCalls+$readyCalls) -eq $calls) 'Blocked work must not automatically retry admission'
 $state.phase='checking';$state.attempt++;$state.checked_kinds=@();$state.skipped=@();$script:ready=$true
 Invoke-CatAnalysisStep $state
 Assert ($state.allowed_kind -eq 'video_description' -and $starts -eq 0) 'Ready Cosmos must work despite low comparison memory'
 $state.phase='stage_complete';$state.allowed_kind=$null;$state.pending.video_description=0
 Invoke-CatAnalysisStep $state
 Assert ($state.phase -eq 'blocked' -and $stops -eq 0) 'Preexisting service must remain running'
 Reset-State;$script:failStart=$true
 Invoke-CatAnalysisStep $state
 Assert ($starts -eq 1 -and !$state.owner -and $state.skipped.Count -eq 1) 'Failed start with no running service must remain retryable'
 Reset-State;$script:failGpu=$true
 Invoke-CatAnalysisStep $state
 Assert ($state.phase -eq 'blocked' -and $starts -eq 0) 'Unavailable GPU must leave work queued'
 Reset-State
 Invoke-CatAnalysisStep $state
 Assert ($state.allowed_kind -eq 'video_description' -and $starts -eq 1 -and $state.owner.container_id -eq 'owned-1') 'Controller should own its successful startup'
 $state.phase='stage_complete';$state.allowed_kind=$null;$state.pending.video_description=0
 Invoke-CatAnalysisStep $state
 Assert ($stops -eq 1 -and $state.allowed_kind -eq 'detector_comparison' -and !$state.owner) 'Descriptions and comparisons must be sequential and owned Cosmos released'
 $state.phase='stage_complete';$state.allowed_kind=$null;$state.pending.detector_comparison=0
 Invoke-CatAnalysisStep $state
 Assert ($state.phase -eq 'complete') 'Completed stages should finish the attempt'
 Reset-State
 Stop-OwnedCosmos ([pscustomobject]@{container_id='another';started_at='stamp-1'})
 Assert ($stops -eq 0) 'Mismatching service identity must be preserved'
 'Controller acceptance passed: capacity, unavailable GPU, ready reuse, explicit retry, startup failure, sequential stages and ownership.'
} finally {if(Test-Path $catOwnerFile){Remove-Item $catOwnerFile}}
# New investigations share Qwen without Cosmos admission, ownership, or unloading.
Reset-State
$state | Add-Member -NotePropertyName description_settings -NotePropertyValue @{description_provider='ollama';description_model='qwen3.5:9b';description_timeout=180}
$script:sharedCalls=0
function Test-CatSharedModel($Settings) {$script:sharedCalls++;Assert ($Settings.description_model -eq 'qwen3.5:9b') 'Wrong shared model'}
$script:free=100
Invoke-CatAnalysisStep $state
Assert ($sharedCalls -eq 1 -and $state.allowed_kind -eq 'video_description' -and $starts -eq 0 -and !$state.owner -and $gpuCalls -eq 0) 'Shared model must not require a separate Cosmos reservation'
$state.phase='stage_complete';$state.allowed_kind=$null;$state.pending.video_description=0
Invoke-CatAnalysisStep $state
Assert ($state.phase -eq 'blocked' -and $stops -eq 0) 'Unavailable comparison must not unload shared Qwen'
Reset-State
$state | Add-Member -NotePropertyName description_settings -NotePropertyValue @{description_provider='ollama'}
function Test-CatSharedModel($Settings) {throw 'Shared server unavailable'}
Invoke-CatAnalysisStep $state
Assert ($state.allowed_kind -eq 'detector_comparison' -and $starts -eq 0 -and $stops -eq 0) 'Shared startup failure should preserve jobs and allow independently admitted comparison'
'Shared Qwen controller checks passed.'
