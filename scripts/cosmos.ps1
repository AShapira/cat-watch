# Optional local reasoner. Recording works independently of this service.
[CmdletBinding()]
param([ValidateSet('Start','Status','Stop','Logs')][string]$Action='Status',
      [string]$DataRoot='C:\Alex\data\tapo-cat-monitor')
$ErrorActionPreference='Stop'
$catDeployment=Join-Path $PSScriptRoot 'cat-watch.ps1'
$catCosmosAction=$Action
. $catDeployment -Action Status -DataRoot $DataRoot
$catLock=Get-Content (Join-Path $PSScriptRoot 'cosmos.lock.json') -Raw | ConvertFrom-Json
$catCosmosContainer='cat-watch-cosmos'
$catModel=Join-Path $AppData 'models\Cosmos3-Edge'
$catInputs=Join-Path $AppData 'analysis-input'
$catExisting=Invoke-Podman @('--connection',$Connection,'ps','-a','--filter',"name=^$catCosmosContainer$",'--format','{{.Names}}')
switch ($catCosmosAction) {
    'Start' {
        if ($catExisting) {
            $catInfo=Invoke-Podman @('--connection',$Connection,'inspect',$catCosmosContainer) | ConvertFrom-Json
            if ($catInfo[0].Config.Labels.app -ne 'cat-watch-cosmos' -or $catInfo[0].ImageName -ne $catLock.image) { throw 'Existing Cosmos container does not match the pinned application image.' }
            if (!$catInfo[0].State.Running) { Invoke-Podman @('--connection',$Connection,'start',$catCosmosContainer) }
            Write-Output 'Reusing the existing pinned Cosmos service. Check Status for readiness.'
            break
        }
        if (!(Test-Path (Join-Path $catModel 'config.json'))) { throw 'Download the revision in cosmos.lock.json into cat-watch/models/Cosmos3-Edge first.' }
        $catRevisionFile=Join-Path $catModel '.cat-watch-revision'
        if (!(Test-Path $catRevisionFile) -or (Get-Content $catRevisionFile -Raw).Trim() -ne $catLock.revision) { throw 'Model revision verification marker missing or mismatched.' }
        New-Item -ItemType Directory -Path $catInputs -Force | Out-Null
        $catServeConfig=Join-Path $AppData 'cosmos-serve.yaml'
        @'
limit-mm-per-prompt:
  video: 1
  image: 0
media-io-kwargs:
  video:
    num_frames: 32
mm-processor-kwargs:
  do_resize: true
  min_pixels: 4096
  max_pixels: 3670016
'@ | Set-Content $catServeConfig -Encoding ASCII
        Invoke-Podman @('--connection',$Connection,'run','-d','--name',$catCosmosContainer,'--label','app=cat-watch-cosmos',
            '--network=host','--device','nvidia.com/gpu=all','--cap-drop=all','--security-opt=no-new-privileges',
            '--shm-size=1g','--log-driver=k8s-file','--log-opt=max-size=2mb',
            '--env','HF_HUB_OFFLINE=1','--env','HF_HUB_DISABLE_TELEMETRY=1','--env','DO_NOT_TRACK=1','--env','VLLM_NO_USAGE_STATS=1',
            '--mount',"type=bind,source=$catModel,target=/model,readonly=true",
            '--mount',"type=bind,source=$catInputs,target=/data/analysis-input,readonly=true",
            '--mount',"type=bind,source=$catServeConfig,target=/serve.yaml,readonly=true",
            '--entrypoint','vllm',$catLock.image,'serve','/model','--served-model-name',$catLock.served_model,
            '--host','127.0.0.1','--port',([string]$catLock.port),'--max-model-len',([string]$catLock.max_model_len),
            '--max-num-seqs','1','--gpu-memory-utilization',([string]$catLock.gpu_memory_utilization),
            '--enforce-eager','--allowed-local-media-path','/data/analysis-input','--config','/serve.yaml')
        Write-Output 'Cosmos starting. Check Status and Logs; readiness requires a successful local video request.'
    }
    'Status' {
        Invoke-Podman @('--connection',$Connection,'ps','-a','--filter',"name=^$catCosmosContainer$",'--format','{{.Names}} {{.Status}}')
        try { Invoke-RestMethod 'http://127.0.0.1:8766/v1/models' -TimeoutSec 3 | ConvertTo-Json -Depth 4 }
        catch { Write-Output 'Cosmos not ready; motion capture is independent.' }
    }
    'Logs' { Invoke-Podman @('--connection',$Connection,'logs','--tail','60',$catCosmosContainer) }
    'Stop' {
        if ($catExisting) {
            $catLabel=Invoke-Podman @('--connection',$Connection,'inspect',$catCosmosContainer,'--format','{{.Config.Labels.app}}')
            if ($catLabel -ne 'cat-watch-cosmos') { throw 'Unexpected container label.' }
            Invoke-Podman @('--connection',$Connection,'stop',$catCosmosContainer)
        }
    }
}
