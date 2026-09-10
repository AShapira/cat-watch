# Run in Windows PowerShell; source may be on the RHEL10 UNC share.
[CmdletBinding()]
param(
    [string]$DataRoot = 'C:\Alex\data\tapo-cat-monitor'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$catRepository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..\..'))
$catDeployment = Join-Path $catRepository 'scripts\cat-watch.ps1'

# Reuse the maintained engine selection, PATHEXT fix, and machine validation.
. $catDeployment -Action Status -DataRoot $DataRoot

$catExisting = Invoke-Podman @('--connection',$Connection,'ps','-a','--filter',"name=^$Container$",'--format','{{.Names}}')
if (!$catExisting) {
    & $catDeployment -Action Start -DataRoot $DataRoot
} else {
    $catLabel = Invoke-Podman @('--connection',$Connection,'inspect',$Container,'--format','{{.Config.Labels.app}}')
    if ($catLabel -ne 'cat-watch') { throw 'Existing container is not labeled cat-watch.' }
    $catState = Invoke-Podman @('--connection',$Connection,'inspect',$Container,'--format','{{.State.Status}}')
    if ($catState -in @('exited','stopped','created')) {
        # Read prerequisites before starting; never serialize secrets to disk or logs.
        $catCamera = Get-Content (Join-Path $DataRoot 'camera.json') -Raw | ConvertFrom-Json
        $catCredential = Import-Clixml $CredentialFile
        $catPayload = $null
        try {
            $catPayload = @{ ip=$catCamera.ip; username=$catCredential.UserName; password=$catCredential.GetNetworkCredential().Password } | ConvertTo-Json -Compress
            Invoke-Podman @('--connection',$Connection,'start',$Container) | Out-Null
            $catPreviousPreference = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                $catTransferOutput = $catPayload | & $Podman --connection $Connection exec -i $Container python -m catwatch --credentials 2>&1
                $catTransferCode = $LASTEXITCODE
            } finally {
                $ErrorActionPreference = $catPreviousPreference
                $catTransferOutput = $null
            }
            if ($catTransferCode -ne 0) { throw 'Camera credential delivery failed; inspect container status.' }
        } finally {
            $catPayload = $null
            $catCredential = $null
        }
    } elseif ($catState -ne 'running') {
        throw "Container state '$catState' needs diagnosis before startup."
    }
}

$catDeadline = (Get-Date).AddSeconds(180)
$catHealth = $null
do {
    $catHealth = $null
    try {
        $catHealth = Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 3
    } catch { }
    if ($catHealth) {
        if ($catHealth.detector -eq 'failed') {
            $catHealth | ConvertTo-Json -Depth 5
            throw 'Detector initialization failed; dashboard is available for diagnosis.'
        }
        if ($catHealth.camera -eq 'connected' -and $catHealth.detector -eq 'ready') {
            Write-Output 'Dashboard: http://127.0.0.1:8765'
            $catHealth | ConvertTo-Json -Depth 5
            return
        }
    }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $catDeadline)

if ($catHealth) { $catHealth | ConvertTo-Json -Depth 5 }
throw 'Camera/detector readiness timed out. Check live status before taking recovery actions.'
