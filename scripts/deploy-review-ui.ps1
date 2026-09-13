# Deploy the current image to an existing review-only app; preserve its data and rollback container.
[CmdletBinding()]
param([string]$DataRoot='C:\Alex\data\tapo-cat-monitor')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'cat-watch.ps1') -Action Status -DataRoot $DataRoot
$catInfo=(Invoke-Podman @('--connection',$Connection,'inspect',$Container) | ConvertFrom-Json)[0]
if($catInfo.Config.Labels.app -ne 'cat-watch' -or $catInfo.Config.Cmd -notcontains '--review-only'){
    throw 'This deployment requires the existing review-only container. Active monitoring is not changed.'
}
$catNewImage=Invoke-Podman @('--connection',$Connection,'image','inspect',$Image,'--format','{{.Id}}')
$catStamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$catRollback="cat-watch-review-rollback-$catStamp"
$catBackup="/data/backups/pre-review-ui-$catStamp.sqlite3"
$catBackupCode=@"
import sqlite3,pathlib,json
p=pathlib.Path('$catBackup'); p.parent.mkdir(exist_ok=True)
a=sqlite3.connect('file:/data/catwatch.sqlite3?mode=ro',uri=True); b=sqlite3.connect(str(p)); a.backup(b)
assert b.execute('pragma integrity_check').fetchone()[0]=='ok'
print(json.dumps({'motions':b.execute('select count(*) from motions').fetchone()[0],'groups':b.execute('select count(distinct group_id) from motions').fetchone()[0],'segments':b.execute('select count(*) from segments').fetchone()[0]}))
b.close(); a.close()
"@
$catBefore=Invoke-Podman @('--connection',$Connection,'exec',$Container,'python','-c',$catBackupCode) | ConvertFrom-Json
Write-Output ('Database backup verified: '+($catBefore | ConvertTo-Json -Compress))
Invoke-Podman @('--connection',$Connection,'stop','--time','20',$Container) | Out-Null
Invoke-Podman @('--connection',$Connection,'rename',$Container,$catRollback) | Out-Null
try {
    Invoke-Podman @('--connection',$Connection,'run','-d','--name',$Container,'--label','app=cat-watch',
        '--network=host','--cap-drop=all','--security-opt=no-new-privileges',
        '--log-driver=k8s-file','--log-opt=max-size=2mb',
        '--mount',"type=bind,source=$AppData,target=/data",$catNewImage,'python','-m','catwatch','--review-only') | Out-Null
    $catReady=$false
    for($i=0;$i -lt 30;$i++){
        try{$catHealth=Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 2; if($catHealth.review_only){$catReady=$true;break}}catch{}
        Start-Sleep -Seconds 1
    }
    if(!$catReady){throw 'Review dashboard did not become ready'}
    Write-Output 'Review dashboard ready; indexing saved detector results.'
    $catGroups=Invoke-RestMethod 'http://127.0.0.1:8765/api/investigation/groups?limit=1' -TimeoutSec 180
    if($catGroups.all_motions -ne $catBefore.motions -or $catGroups.all_groups -ne $catBefore.groups){throw 'Motion inventory changed unexpectedly'}
    $catCountCode="import sqlite3; c=sqlite3.connect('file:/data/catwatch.sqlite3?mode=ro',uri=True); print(c.execute('select count(*) from segments').fetchone()[0])"
    $catSegments=Invoke-Podman @('--connection',$Connection,'exec',$Container,'python','-c',$catCountCode)
    if([int]$catSegments -ne $catBefore.segments){throw 'Recording inventory changed unexpectedly'}
    $catRecord=@{deployed_utc=[DateTime]::UtcNow.ToString('o');previous_container=$catRollback;backup=$catBackup;image=$catNewImage;mode='review-only';inventory=$catBefore}
    $catRecord | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $AppData "review-ui-deployment-$catStamp.json") -Encoding UTF8
    $catRecord | ConvertTo-Json -Depth 4
} catch {
    $catFailure=$_
    $catExists=Invoke-Podman @('--connection',$Connection,'ps','-a','--filter',"name=^$Container$",'--format','{{.Names}}')
    if($catExists){
        Invoke-Podman @('--connection',$Connection,'stop','--time','10',$Container) | Out-Null
        Invoke-Podman @('--connection',$Connection,'rename',$Container,"cat-watch-review-failed-$catStamp") | Out-Null
    }
    Invoke-Podman @('--connection',$Connection,'rename',$catRollback,$Container) | Out-Null
    Invoke-Podman @('--connection',$Connection,'start',$Container) | Out-Null
    throw "Review deployment failed; previous review-only container restored. $catFailure"
}
