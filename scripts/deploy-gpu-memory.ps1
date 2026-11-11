# Scoped code-only upgrade. Build and native capacity validation happen beforehand.
[CmdletBinding()]
param(
    [ValidateSet('Plan','Apply')][string]$Action='Plan',
    [string]$Image='localhost/cat-watch:0.5.3',
    [Parameter(Mandatory=$true)][string]$ExpectedImageId,
    [string]$ExpectedPreviousImageId='1a50a36141c6a0f13ccbd0855588968d2eaa4a5f0236dca83e4173ace3c3f1a7',
    [string]$DataRoot='C:\Alex\data\tapo-cat-monitor',
    [Parameter(Mandatory=$true)][string]$EvidencePath
)
$ErrorActionPreference='Stop'
$env:PATHEXT=[Environment]::GetEnvironmentVariable('PATHEXT','Machine')
$podman=Join-Path $env:LOCALAPPDATA 'Programs\Podman\podman.exe'
$connection='podman-machine-default-root'
$appData=Join-Path $DataRoot 'cat-watch'
$launcher=Join-Path $PSScriptRoot 'cat-watch.ps1'
function Podman([string[]]$Arguments) {
    $output=& $podman --connection $connection @Arguments
    if($LASTEXITCODE -ne 0){throw 'Scoped deployment command failed'}
    return $output
}
function Save-Receipt {
    [IO.File]::WriteAllText($EvidencePath,($receipt|ConvertTo-Json -Depth 8)+"`n",(New-Object Text.UTF8Encoding($false)))
}
$current=(Podman @('inspect','cat-watch')|ConvertFrom-Json)[0]
$candidate=(Podman @('image','inspect',$Image)|ConvertFrom-Json)[0]
if($current.Config.Labels.app -ne 'cat-watch' -or !$current.State.Running -or $current.Image -ne $ExpectedPreviousImageId){throw 'Live deployment does not match the reviewed source image'}
if($candidate.Id -ne $ExpectedImageId -or $candidate.Labels.'cat-watch.patch' -ne 'shared-gpu-memory'){throw 'Candidate does not match the validated patch'}
if(!(Test-Path (Join-Path $appData '.cat-watch-data'))){throw 'Missing application ownership marker'}
$writers=@(Podman @('ps','--format','{{.Names}}')|Where-Object {$_ -ne 'cat-watch' -and $_ -match '^(cat-watch|label-studio)'})
if($writers.Count){throw 'Another related container is running; leave recording unchanged and inspect writers'}
$health=Invoke-RestMethod http://127.0.0.1:8765/api/health -TimeoutSec 10
$learning=Invoke-RestMethod http://127.0.0.1:8765/api/learning/status -TimeoutSec 15
$qwen=Invoke-RestMethod http://127.0.0.1:11434/health -TimeoutSec 10
if(!$qwen.ready -or $health.camera -ne 'connected' -or !$learning.config.continuous -or $learning.config.training){throw 'Expected recording, resident Qwen and training paused before the handoff'}
$files=@(Get-ChildItem $appData -File -Filter '*.sqlite3*')+@(Get-ChildItem (Join-Path $appData 'learning') -File -Filter '*.sqlite3*')
$bytes=($files|Measure-Object Length -Sum).Sum
if((Get-PSDrive C).Free -lt $bytes*1.1+3000000000){throw 'Insufficient backup space'}
$stamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$previous='cat-watch-before-gpu-memory-'+$stamp
$backup=Join-Path $DataRoot ('gpu-memory-backup-'+$stamp)
$receipt=[ordered]@{prepared_at=[DateTime]::UtcNow.ToString('o');state='prepared';image=$Image;image_id=$candidate.Id;previous_image_id=$current.Image;previous_container=$previous;backup=$backup;backup_scope='Quiescent application and learning databases with any sidecars; existing media remain in place';before=@{frames=$health.frames_analyzed;capture_gaps=$health.capture_gaps;counts=$learning.counts;continuous=$learning.config.continuous;calibration_id=$learning.config.calibration_id;qwen_digest=$qwen.models[0].digest};database_bytes_estimate=$bytes}
if($Action -eq 'Plan'){$receipt|ConvertTo-Json -Depth 8;return}
Save-Receipt
$renamed=$false
try {
    $receipt.stop_requested_at=[DateTime]::UtcNow.ToString('o'); Save-Receipt
    Podman @('stop','--time','35','cat-watch')|Out-Null
    $receipt.stopped_at=[DateTime]::UtcNow.ToString('o')
    New-Item -ItemType Directory (Join-Path $backup 'learning') -Force|Out-Null
    # Enumerate again after shutdown, including journals if shutdown left any.
    $files=@(Get-ChildItem $appData -File -Filter '*.sqlite3*')+@(Get-ChildItem (Join-Path $appData 'learning') -File -Filter '*.sqlite3*')
    $checks=@()
    foreach($file in $files){
        $relative=$file.FullName.Substring($appData.Length).TrimStart('\')
        $destination=Join-Path $backup $relative
        Copy-Item $file.FullName $destination
        $hash=(Get-FileHash $file.FullName -Algorithm SHA256).Hash
        if($hash -ne (Get-FileHash $destination -Algorithm SHA256).Hash){throw 'Database snapshot checksum mismatch'}
        $checks+=@{file=$relative;bytes=$file.Length;sha256=$hash.ToLower()}
    }
    Copy-Item (Join-Path $appData '.cat-watch-data') $backup
    $receipt.database_snapshots=$checks
    $receipt.backup_verified_at=[DateTime]::UtcNow.ToString('o'); Save-Receipt
    Podman @('rename','cat-watch',$previous)|Out-Null
    $renamed=$true
    & $launcher -Action Start -DataRoot $DataRoot -Image $Image | Out-Null
    $after=Invoke-RestMethod http://127.0.0.1:8765/api/health -TimeoutSec 10
    $next=Invoke-RestMethod http://127.0.0.1:8765/api/learning/status -TimeoutSec 15
    $qwenAfter=Invoke-RestMethod http://127.0.0.1:11434/health -TimeoutSec 10
    if($after.camera -ne 'connected' -or $after.detector -ne 'ready' -or !$next.config.continuous -or $next.config.calibration_id -ne $learning.config.calibration_id -or !$qwenAfter.ready -or $qwenAfter.models[0].digest -ne $receipt.before.qwen_digest){throw 'Post-deployment camera, calibration or Qwen checks failed'}
    $receipt.ready_at=[DateTime]::UtcNow.ToString('o')
    $receipt.stop_to_ready_seconds=[Math]::Round(([DateTimeOffset]::Parse($receipt.ready_at)-[DateTimeOffset]::Parse($receipt.stop_requested_at)).TotalSeconds,2)
    $receipt.state='deployed-training-still-paused'
    $receipt.after=@{camera=$after.camera;detector=$after.detector;continuous=$next.config.continuous;training=$next.config.training;gpu=$next.gpu;counts=$next.counts;qwen_ready=$qwenAfter.ready}
    Save-Receipt
    $receipt|ConvertTo-Json -Depth 8
} catch {
    $receipt.state='failed-restoring-previous-container'; Save-Receipt
    # This patch has no data-schema change. Roll back code over current data;
    # never overwrite newly recorded media or annotations with an old snapshot.
    if($renamed){
        $new=Podman @('ps','-a','--filter','name=^cat-watch$','--format','{{.Names}}')
        if($new){
            Podman @('stop','--time','35','cat-watch')|Out-Null
            Podman @('rename','cat-watch',('cat-watch-failed-gpu-memory-'+$stamp))|Out-Null
        }
        Podman @('rename',$previous,'cat-watch')|Out-Null
    }
    $old=(Podman @('inspect','cat-watch')|ConvertFrom-Json)[0]
    if(!$old.State.Running){& $launcher -Action Resume -DataRoot $DataRoot | Out-Null}
    $receipt.state='rolled-back-training-paused';$receipt.rollback_at=[DateTime]::UtcNow.ToString('o');Save-Receipt
    throw 'Patch deployment failed; previous container restored. Inspect the receipt; training remains paused.'
}
