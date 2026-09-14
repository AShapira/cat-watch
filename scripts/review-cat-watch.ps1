# Open existing data without camera credentials, GPU inference, recording or retention.
[CmdletBinding()]
param([string]$DataRoot='C:\Alex\data\tapo-cat-monitor')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'cat-watch.ps1') -Action Status -DataRoot $DataRoot
$existing=Invoke-Podman @('--connection',$Connection,'ps','-a','--filter',"name=^$Container$",'--format','{{.Names}}')
if($existing){
    $info=Invoke-Podman @('--connection',$Connection,'inspect',$Container) | ConvertFrom-Json
    if($info[0].Config.Labels.app -ne 'cat-watch'){throw 'Unexpected container label.'}
    if($info[0].State.Running){throw 'Stop the existing worker before launching review-only mode.'}
    $previous='cat-watch-stopped-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    Invoke-Podman @('--connection',$Connection,'rename',$Container,$previous) | Out-Null
}
$labelingMounts=@(Get-LabelingMounts)
Invoke-Podman (@('--connection',$Connection,'run','-d','--name',$Container,'--label','app=cat-watch',
    '--network=host','--cap-drop=all','--security-opt=no-new-privileges',
    '--log-driver=k8s-file','--log-opt=max-size=2mb',
    '--mount',"type=bind,source=$AppData,target=/data") + $labelingMounts + @($Image,'python','-m','catwatch','--review-only')) | Out-Null
for($i=0;$i -lt 30;$i++){
    try{
        $h=Invoke-RestMethod http://127.0.0.1:8765/api/health -TimeoutSec 2
        if($h.review_only){Write-Output 'Review-only dashboard ready: http://127.0.0.1:8765'; return}
    }catch{}
    Start-Sleep -Seconds 1
}
throw 'Review-only dashboard did not become ready.'
