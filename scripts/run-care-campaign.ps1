[CmdletBinding()]
param([ValidateSet('Build','Prepare','Cloud','Report','Refresh','Serve')][string]$Stage='Report')
$ErrorActionPreference='Stop'
$env:PATHEXT=[Environment]::GetEnvironmentVariable('PATHEXT','Machine')
$podman=Join-Path $env:LOCALAPPDATA 'Programs\Podman\podman.exe'
$connection='podman-machine-default-root'
$source=Split-Path $PSScriptRoot -Parent
$image='localhost/cat-watch:care-20261104'
$data='C:\Alex\data\tapo-cat-monitor\cat-watch'
$credentialPath=Join-Path $env:LOCALAPPDATA 'TapoCatMonitor\openai.credential.xml'
if(!(Test-Path (Join-Path $data '.cat-watch-data'))){throw 'Missing application ownership marker'}
if($Stage -eq 'Build') {
    $base=& $podman --connection $connection image inspect localhost/cat-watch:0.5.3 --format '{{.Id}}'
    if($LASTEXITCODE -ne 0 -or $base -ne '540a4e088dd95c017766509195324f951e88e0c611048e9fd4a6fce291d5610f'){throw 'Unexpected base image'}
    & $podman --connection $connection build --pull=never --network=none -t $image -f (Join-Path $source 'Containerfile.campaign') $source
    if($LASTEXITCODE -ne 0){throw 'Comparison image build failed'}
    & $podman --connection $connection image inspect $image --format '{{.Id}}'
    return
}
$labels=& $podman --connection $connection image inspect $image --format '{{json .Labels}}'
if($LASTEXITCODE -ne 0 -or ($labels|ConvertFrom-Json).'cat-watch.purpose' -ne 'focused-care-candidates-2026-11-04'){throw 'Unexpected comparison image'}
$arguments=@('--connection',$connection,'run','--rm','-i','--name','cat-watch-care-batch',
    '--network=host','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges',
    '--pids-limit=256','--memory=2g','--cpus=2','--tmpfs','/tmp:rw,size=512m',
    '--env','PYTHONDONTWRITEBYTECODE=1','--env','OPENBLAS_NUM_THREADS=1',
    '--mount',('type=bind,source='+$data+',target=/data'),$image,
    'python','-u','-m','catwatch.learning.campaign',$Stage.ToLower())
if($Stage -eq 'Serve') {
    $arguments=@('--connection',$connection,'run','-d','--name','cat-watch-care-review',
        '--restart=unless-stopped','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges',
        '--pids-limit=256','--memory=2g','--cpus=2','--tmpfs','/tmp:rw,size=512m',
        '--publish','127.0.0.1:8767:8767','--env','OPENBLAS_NUM_THREADS=1',
        '--env','PYTHONDONTWRITEBYTECODE=1',
        '--mount',('type=bind,source='+$data+',target=/data'),$image,
        'python','-u','-m','catwatch.learning.campaign','serve')
}
if($Stage -eq 'Cloud') {
    if(!(Test-Path $credentialPath)){throw 'Save the project API key with configure-learning-secret.ps1 -Service OpenAI first'}
    $credential=Import-Clixml $credentialPath
    try {
        # The plaintext exists transiently in this process and the runner stdin.
        # It never enters process arguments, environment metadata, or saved logs.
        @{api_key=$credential.GetNetworkCredential().Password}|ConvertTo-Json -Compress|& $podman @arguments
        $code=$LASTEXITCODE
    } finally {$credential=$null}
} else {
    & $podman @arguments
    $code=$LASTEXITCODE
}
if($code -ne 0){throw 'Comparison stopped. Inspect its durable cost ledger before continuing; do not delete or reset it.'}
