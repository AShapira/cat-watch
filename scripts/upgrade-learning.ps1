# Prepare first. Apply requires deliberate invocation after reviewing Plan output.
[CmdletBinding()]
param([ValidateSet('Plan','Apply')][string]$Action='Plan',
      [string]$DataRoot='C:\Alex\data\tapo-cat-monitor')
$ErrorActionPreference='Stop'
$upgradeAction=$Action
. (Join-Path $PSScriptRoot 'cat-watch.ps1') -Action Status -DataRoot $DataRoot
$existing=Invoke-Podman @('--connection',$Connection,'ps','-a','--filter','name=^cat-watch$','--format','{{.Names}}')
if (!$existing) {throw 'No existing cat-watch deployment. Use cat-watch.ps1 -Action Start for a fresh deployment.'}
$info=Invoke-Podman @('--connection',$Connection,'inspect','cat-watch') | ConvertFrom-Json
if($info[0].Config.Labels.app -ne 'cat-watch') {throw 'Unexpected container label.'}
if($info[0].State.Running) {throw 'Stop recording and the application before upgrading; no service was changed.'}
$writers=Invoke-Podman @('--connection',$Connection,'ps','--format','{{.Names}}')
if(@($writers -split "`n" | Where-Object {$_ -match '^cat-watch|label-studio'}).Count) {
    throw 'A cat-watch or Label Studio writer is running. Stop it before taking the upgrade snapshot.'
}
$imageId=Invoke-Podman @('--connection',$Connection,'image','inspect',$Image,'--format','{{.Id}}')
$stamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$backup=Join-Path $DataRoot ('cat-watch-upgrade-'+$stamp)
$saved='cat-watch-before-learning-'+$stamp
[ordered]@{image=$Image;image_id=$imageId;data=$AppData;backup=$backup;preserved_container=$saved;
           effects='Snapshot application data, preserve stopped container, start new local agent; continuous recording remains opt-in after calibration.'} | ConvertTo-Json
if($upgradeAction -ne 'Apply') {return}
if(!(Test-Path (Join-Path $AppData '.cat-watch-data'))) {throw 'Application ownership marker missing.'}
if(Test-Path (Join-Path $AppData 'learning\agent.sqlite3')) {throw 'This helper is for the first learning upgrade; existing learning state requires a separate reviewed upgrade.'}
if(@(Get-ChildItem $AppData -Filter '*-wal' -Recurse).Count -or @(Get-ChildItem $AppData -Filter '*-journal' -Recurse).Count) {
    throw 'Database journal is present; investigate database shutdown before snapshotting.'
}
$bytes=(Get-ChildItem $AppData -File -Recurse -Force | Measure-Object Length -Sum).Sum
$drive=Get-PSDrive -Name ([IO.Path]::GetPathRoot($DataRoot).Substring(0,1))
if($drive.Free -lt $bytes*1.1+3000000000) {throw 'Insufficient disk space for a verified backup and reserve; nothing was changed.'}
New-Item -ItemType Directory $backup | Out-Null
Copy-Item -Path (Join-Path $AppData '*') -Destination $backup -Recurse -Force
# PowerShell wildcard handling of dotfiles is explicit for the ownership marker.
Copy-Item (Join-Path $AppData '.cat-watch-data') $backup -Force
$files=@(Get-ChildItem $AppData -File -Recurse -Force)
foreach($file in $files) {
    $relative=$file.FullName.Substring($AppData.Length).TrimStart('\')
    $copy=Join-Path $backup $relative
    if(!(Test-Path $copy) -or (Get-FileHash $file.FullName -Algorithm SHA256).Hash -ne (Get-FileHash $copy -Algorithm SHA256).Hash) {
        throw 'Snapshot verification failed; deployment was not changed.'
    }
}
Invoke-Podman @('--connection',$Connection,'rename','cat-watch',$saved) | Out-Null
[ordered]@{previous_container=$saved;previous_image=$info[0].ImageName;backup=$backup;created=$stamp} |
    ConvertTo-Json | Set-Content (Join-Path $DataRoot ('learning-upgrade-'+$stamp+'.json')) -Encoding UTF8
& (Join-Path $PSScriptRoot 'cat-watch.ps1') -Action Start -DataRoot $DataRoot -Image $Image
Write-Output "Old deployment preserved as $saved. Verified snapshot: $backup"
