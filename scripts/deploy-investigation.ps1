# Deploy the built image, retaining the previous container and a consistent SQLite backup.
[CmdletBinding()]
param([string]$DataRoot='C:\Alex\data\tapo-cat-monitor')
$ErrorActionPreference='Stop'
$catScript=Join-Path $PSScriptRoot 'cat-watch.ps1'
. $catScript -Action Status -DataRoot $DataRoot
$catHealth=Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 5
$catAnalysis=Invoke-RestMethod 'http://127.0.0.1:8765/api/analysis' -TimeoutSec 5
if($catHealth.capture_busy -or $catHealth.live_model_loaded -or $catAnalysis.phase -in @('checking','processing','stage_complete') -or $catAnalysis.owner) {
    throw 'Finish capture, active analysis and owned-model cleanup before deployment.'
}
$catController=Join-Path $PSScriptRoot 'analysis-controller.ps1'
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object {
    $_.ProcessId -ne $PID -and $_.CommandLine -like ('*'+$catController+'*')
} | ForEach-Object {Stop-Process -Id $_.ProcessId}
$catStamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$catOldName='cat-watch-rollback-'+$catStamp
Invoke-Podman @('--connection',$Connection,'image','exists',$Image) | Out-Null
$catLabel=Invoke-Podman @('--connection',$Connection,'inspect',$Container,'--format','{{.Config.Labels.app}}')
if ($catLabel -ne 'cat-watch') { throw 'Expected the existing cat-watch container.' }
$catBackup="/data/backups/pre-investigation-$catStamp.sqlite3"
$catBackupCode="import sqlite3,pathlib; p=pathlib.Path('$catBackup'); p.parent.mkdir(exist_ok=True); a=sqlite3.connect('file:/data/catwatch.sqlite3?mode=ro',uri=True); b=sqlite3.connect(str(p)); a.backup(b); print(b.execute('PRAGMA integrity_check').fetchone()[0]); b.close(); a.close()"
$catIntegrity=Invoke-Podman @('--connection',$Connection,'exec',$Container,'python','-c',$catBackupCode)
if ($catIntegrity.Trim() -ne 'ok') { throw 'SQLite backup failed validation.' }
Invoke-Podman @('--connection',$Connection,'stop','--time','35',$Container) | Out-Null
Invoke-Podman @('--connection',$Connection,'rename',$Container,$catOldName) | Out-Null
try {
    & $catScript -Action Start -DataRoot $DataRoot
    $catRecord=@{deployed_utc=[DateTime]::UtcNow.ToString('o');previous_container=$catOldName;backup=$catBackup;image=$Image}
    $catRecord | ConvertTo-Json | Set-Content (Join-Path $AppData "deployment-$catStamp.json") -Encoding UTF8
    Write-Output "Deployment verified. Previous container: $catOldName. Backup: $catBackup"
} catch {
    Write-Output "Deployment needs attention. Previous container retained as $catOldName; database backup at $catBackup."
    throw
}
