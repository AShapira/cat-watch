# Host-side, one-attempt GPU admission. No engine socket is exposed to the app.
[CmdletBinding()]
param([string]$DataRoot='C:\Alex\data\tapo-cat-monitor',[switch]$FunctionsOnly)
$ErrorActionPreference='Stop'
$env:PATHEXT=[Environment]::GetEnvironmentVariable('PATHEXT','Machine')
function Invoke-CatApi([string]$Path,[string]$Method='GET',$Body=$null) {
    if($Method -ne 'GET') {
        $session=Invoke-RestMethod 'http://127.0.0.1:8765/api/session' -TimeoutSec 5
        $catHeaders=@{'x-catwatch-token'=$session.token}
        return Invoke-RestMethod ("http://127.0.0.1:8765"+$Path) -Method $Method -Headers $catHeaders -ContentType 'application/json' -Body ($Body|ConvertTo-Json -Depth 12 -Compress) -TimeoutSec 10
    }
    return Invoke-RestMethod ("http://127.0.0.1:8765"+$Path) -TimeoutSec 5
}
function Get-CatGpu {
    $raw=Invoke-Podman @('machine','ssh',$Machine,'/usr/lib/wsl/lib/nvidia-smi','--query-gpu=memory.total,memory.free','--format=csv,noheader,nounits')
    $rows=@($raw -split "`n" | Where-Object { $_ -match '^\s*\d+\s*,\s*\d+\s*$' })
    if($rows.Count -ne 1) { throw 'Expected one identifiable NVIDIA GPU' }
    $parts=$rows[0].Split(',')
    return @{total=[double]$parts[0];free=[double]$parts[1]}
}
function Test-CatCosmos {
    try {
        $models=Invoke-RestMethod 'http://127.0.0.1:8766/v1/models' -TimeoutSec 5
        if (@($models.data | Where-Object id -eq $catLock.served_model).Count -ne 1) { return $false }
        $body=@{model=$catLock.served_model;max_tokens=1;messages=@(@{role='user';content='Reply OK.'})}|ConvertTo-Json -Depth 6
        $reply=Invoke-RestMethod 'http://127.0.0.1:8766/v1/chat/completions' -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 30
        return ($null -ne $reply.choices)
    } catch { return $false }
}
function Test-CatSharedModel($Settings) {
    # Same shared service, reached through Windows loopback. Never unload it.
    $model=$Settings.description_model
    $loaded=Invoke-RestMethod 'http://127.0.0.1:11434/api/ps' -TimeoutSec 5
    if(@($loaded.models | Where-Object name -eq $model).Count -eq 1) {return}
    $body=@{model=$model;stream=$false}|ConvertTo-Json
    Invoke-RestMethod 'http://127.0.0.1:11434/api/generate' -Method Post -ContentType 'application/json' -Body $body -TimeoutSec $Settings.description_timeout | Out-Null
    $loaded=Invoke-RestMethod 'http://127.0.0.1:11434/api/ps' -TimeoutSec 5
    if(@($loaded.models | Where-Object name -eq $model).Count -ne 1) {throw 'Shared Qwen model did not become ready; use Retry analysis'}
}
function Save-CatControl($State,[string]$Phase,$Kind,[string]$Message,$Owner,$Checked,$Skipped) {
    return Invoke-CatApi '/api/analysis/control' 'PUT' @{session_id=$State.session_id;attempt=$State.attempt;phase=$Phase;allowed_kind=$Kind;message=$Message;owner=$Owner;checked_kinds=@($Checked);skipped=@($Skipped)}
}
function Stop-OwnedCosmos($Owner) {
    if (!$Owner) { return }
    if (!$Owner.container_id) {
        if(Test-Path $catOwnerFile) {
            $receipt=Get-Content $catOwnerFile -Raw|ConvertFrom-Json
            if($receipt.session_id -eq $Owner.session_id -and $receipt.attempt -eq $Owner.attempt) {$Owner=$receipt}
            else {throw 'Cosmos ownership is unresolved; it has been left running'}
        } else {throw 'Cosmos ownership is unresolved; it has been left running'}
    }
    $raw=Invoke-Podman @('--connection',$Connection,'inspect','cat-watch-cosmos')
    $info=@($raw|ConvertFrom-Json)[0]
    if($info.Id -eq $Owner.container_id -and $info.State.StartedAt -eq $Owner.started_at -and $info.Config.Labels.app -eq 'cat-watch-cosmos') {
        Invoke-Podman @('--connection',$Connection,'stop','cat-watch-cosmos') | Out-Null
        if(Test-Path $catOwnerFile) {Remove-Item $catOwnerFile}
    }
}
function Start-CatCosmos { & (Join-Path $PSScriptRoot 'cosmos.ps1') -Action Start -DataRoot $DataRoot | Out-Null }
function Invoke-CatAnalysisStep($state) {
        if(!$state.session_id) {return}
        if($state.phase -eq 'waiting_capture' -and $state.capture_drained) {
            $state=Invoke-CatApi '/api/analysis/retry' 'POST' @{}
        }
        if($state.phase -in @('blocked','complete')) {
            if($state.owner) {
                try {Stop-OwnedCosmos $state.owner;Save-CatControl $state $state.phase $null $state.message $null $state.checked_kinds $state.skipped|Out-Null} catch {Write-Warning 'Project Cosmos cleanup needs attention; ownership has been preserved.'}
            }
            return
        }
        if($state.phase -notin @('checking','stage_complete')) {return}
        $checked=@($state.checked_kinds);$skipped=@($state.skipped);$owner=$state.owner
        # Once descriptions finish, release an owned server before comparison admission.
        if($state.phase -eq 'stage_complete' -and $owner) {
            Stop-OwnedCosmos $owner;$owner=$null
            $state=Save-CatControl $state 'checking' $null 'Checking remaining analysis stage' $owner $checked $skipped
        }
        $next=$null
        foreach($kind in @('video_description','detector_comparison')) {
            if($checked -contains $kind) {continue}
            $checked+= $kind
            if($state.pending.$kind -eq 0) {continue}
            try {
                if($kind -eq 'video_description') {
                    if($state.description_settings.description_provider -eq 'ollama') {
                        Test-CatSharedModel $state.description_settings
                    } elseif(!(Test-CatCosmos)) {
                        $gpu=Get-CatGpu
                        $required=$gpu.total*[double]$catLock.gpu_memory_utilization+1024
                        if($gpu.free -lt $required) {throw "Cosmos needs $([math]::Ceiling($required)) MiB available; $($gpu.free) MiB is free"}
                        $existing=Invoke-Podman @('--connection',$Connection,'ps','--filter','name=^cat-watch-cosmos$','--format','{{.Names}}')
                        if($existing) {throw 'An existing Cosmos service is running but not ready'}
                        # Save ownership intent before starting; reconcile it with the exact container after launch.
                        $owner=@{starting=$true;container_id=$null;started_at=$null;session_id=$state.session_id;attempt=$state.attempt}
                        $state=Save-CatControl $state 'checking' $null 'Starting the project Cosmos model' $owner $checked $skipped
                        Start-CatCosmos
                        $info=@((Invoke-Podman @('--connection',$Connection,'inspect','cat-watch-cosmos')|ConvertFrom-Json))[0]
                        $owner=@{container_id=$info.Id;started_at=$info.State.StartedAt;starting=$false;session_id=$state.session_id;attempt=$state.attempt}
                        $owner|ConvertTo-Json|Set-Content $catOwnerFile -Encoding UTF8
                        $state=Save-CatControl $state 'checking' $null 'Waiting for Cosmos readiness' $owner $checked $skipped
                        $ready=$false
                        for($i=0;$i -lt 60;$i++) {
                            if(Test-CatCosmos) {$ready=$true;break}
                            Start-Sleep -Seconds 5
                        }
                        if(!$ready) {throw 'Cosmos startup did not become ready'}
                    }
                } else {
                    $gpu=Get-CatGpu
                    $required=([double]$catLock.comparison_memory_gib+1)*1024
                    if($gpu.free -lt $required) {throw "Detector comparison needs $required MiB available; $($gpu.free) MiB is free"}
                }
                $next=$kind;break
            } catch {
                $skipped+= "$kind unavailable: $($_.Exception.Message)"
                if($owner -and !$owner.container_id) {
                    # A failed start that created no running service must remain retryable.
                    $running=Invoke-Podman @('--connection',$Connection,'ps','--filter','name=^cat-watch-cosmos$','--format','{{.Names}}')
                    if(!$running){$owner=$null}
                }
                if($owner -and $owner.container_id) {Stop-OwnedCosmos $owner;$owner=$null}
            }
        }
        if($next) {
            Save-CatControl $state 'processing' $next ("Processing "+$next) $owner $checked $skipped | Out-Null
        } else {
            if($owner) {Stop-OwnedCosmos $owner;$owner=$null}
            $phase=if($skipped.Count){'blocked'}else{'complete'}
            $message=if($skipped.Count){($skipped -join '; ')+'. Use Retry analysis for another check.'}else{'Heavy analysis complete; project-owned GPU models released.'}
            Save-CatControl $state $phase $null $message $null $checked $skipped | Out-Null
        }
}
if($FunctionsOnly) {return}
$catMutex=New-Object Threading.Mutex($false,'Local\CatWatchAnalysisController')
if (!$catMutex.WaitOne(0)) { return }
. (Join-Path $PSScriptRoot 'cat-watch.ps1') -Action Status -DataRoot $DataRoot
$catLock=Get-Content (Join-Path $PSScriptRoot 'cosmos.lock.json') -Raw | ConvertFrom-Json
$catHeaders=@{}
$catOwnerFile=Join-Path $AppData 'analysis-controller-owner.json'
$catUnavailable=0
$state=$null
try {
    while($true) {
        try {$state=Invoke-CatApi '/api/analysis';$catUnavailable=0} catch {
            $catUnavailable++
            if($catUnavailable -ge 12) { break }
            Start-Sleep -Seconds 5;continue
        }
        try {Invoke-CatAnalysisStep $state} catch {
            Write-Warning ('Analysis controller paused: '+$_.Exception.Message)
            try {
                $state=Invoke-CatApi '/api/analysis'
                Save-CatControl $state 'blocked' $null 'Controller failed; queued work needs explicit Retry analysis.' $state.owner @() @()|Out-Null
            } catch {Write-Warning 'Unable to persist controller failure; stopping to avoid repeated admission.';break}
        }
        Start-Sleep -Seconds 2
    }
} finally {
    $catMutex.ReleaseMutex();$catMutex.Dispose()
}
