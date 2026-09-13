# Replace application code while preserving an active investigation's id and deadline.
[CmdletBinding()]
param([string]$DataRoot='C:\Alex\data\tapo-cat-monitor')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'cat-watch.ps1') -Action Status -DataRoot $DataRoot
$catBefore=Invoke-RestMethod 'http://127.0.0.1:8765/api/investigation' -TimeoutSec 10
if(!$catBefore.session.active -or $catBefore.health.camera -ne 'connected'){throw 'Expected active camera investigation'}
$catInfo=(Invoke-Podman @('--connection',$Connection,'inspect',$Container) | ConvertFrom-Json)[0]
if($catInfo.Config.Labels.app -ne 'cat-watch'){throw 'Unexpected container label'}
$catPrevious='cat-watch-cycle-repair-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
Invoke-Podman @('--connection',$Connection,'stop','--time','35',$Container) | Out-Null
Invoke-Podman @('--connection',$Connection,'rename',$Container,$catPrevious) | Out-Null
# Keep the existing data and retained pre-cycle database backup. No schema reset or new session.
& (Join-Path $PSScriptRoot 'cat-watch.ps1') -Action Start -DataRoot $DataRoot
$catAfter=Invoke-RestMethod 'http://127.0.0.1:8765/api/investigation' -TimeoutSec 10
if($catAfter.session.id -ne $catBefore.session.id -or $catAfter.session.deadline -ne $catBefore.session.deadline){throw 'Session identity or deadline changed'}
Write-Output ('Resumed session '+$catAfter.session.id+' with its original deadline. Previous container: '+$catPrevious)
