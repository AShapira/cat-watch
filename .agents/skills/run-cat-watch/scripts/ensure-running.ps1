# Launch the migrated RHEL deployment from the signed-in Windows session.
[CmdletBinding()]
param([string]$DataRoot='C:\Alex\data\tapo-cat-monitor')
$ErrorActionPreference='Stop'
$repository=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..\..'))
& (Join-Path $repository 'scripts\start-rhel.ps1') -DataRoot $DataRoot
$deadline=(Get-Date).AddSeconds(180)
do {
    try {
        $health=Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 3
        if(($health.camera -eq 'connected' -and $health.detector -eq 'ready') -or ($health.preparation -and $health.camera -eq 'preview')){
            Write-Output 'Dashboard: http://127.0.0.1:8765'
            $health|ConvertTo-Json -Depth 5
            return
        }
    } catch {}
    Start-Sleep -Seconds 2
} while((Get-Date) -lt $deadline)
throw 'RHEL camera readiness timed out; inspect cat-watch.service before recovery.'
