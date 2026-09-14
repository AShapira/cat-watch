# Local CPU-only Label Studio. Does not start, stop or replace cat-watch.
[CmdletBinding()]
param(
    [ValidateSet('Configure','Pull','Start','Stop','Status','Credentials','UsePAT')][string]$Action='Status',
    [string]$DataRoot='C:\Alex\data\tapo-cat-monitor',
    [string]$Machine='podman-machine-default',
    [string]$Connection='podman-machine-default-root'
)
$requestedAction=$Action
. (Join-Path $PSScriptRoot 'cat-watch.ps1') -Action Status -DataRoot $DataRoot -Machine $Machine -Connection $Connection
$Action=$requestedAction
$labelRoot=Join-Path $DataRoot 'cat-watch-label-studio'
$private=Join-Path $labelRoot 'private'
$state=Join-Path $labelRoot 'state'
$dataset=Join-Path $DataRoot 'cat-watch-dataset'
$labelContainer='cat-watch-label-studio'
$lock=Get-Content (Join-Path $PSScriptRoot 'label-studio.lock.json') -Raw | ConvertFrom-Json
function Write-PrivateText([string]$Path,[string]$Value) {
    [IO.File]::WriteAllText($Path,$Value,(New-Object Text.UTF8Encoding($false)))
}
function New-Secret {
    $bytes=New-Object byte[] 32
    $rng=[Security.Cryptography.RandomNumberGenerator]::Create()
    try {$rng.GetBytes($bytes)} finally {$rng.Dispose()}
    return [Convert]::ToBase64String($bytes)
}
switch ($Action) {
    'Configure' {
        if(Test-Path (Join-Path $private 'integration.json')) {throw 'Already configured; existing credentials are preserved.'}
        if((Test-Path $labelRoot) -and @(Get-ChildItem -Force $labelRoot).Count) {throw 'Refusing to adopt nonempty Label Studio storage.'}
        New-Item -ItemType Directory -Force -Path $private,$state,$dataset | Out-Null
        # Only the current Windows account and SYSTEM can read service credentials.
        $identity=[Security.Principal.WindowsIdentity]::GetCurrent().Name
        & icacls.exe $private /inheritance:r /grant:r "${identity}:(OI)(CI)F" 'SYSTEM:(OI)(CI)F' | Out-Null
        if($LASTEXITCODE -ne 0){throw 'Could not restrict the credential directory.'}
        Write-PrivateText (Join-Path $private 'token') (New-Secret)
        Write-PrivateText (Join-Path $private 'webhook') (New-Secret)
        Write-PrivateText (Join-Path $private 'bootstrap.json') (@{username='catwatch@localhost';password=(New-Secret)} | ConvertTo-Json)
        Write-PrivateText (Join-Path $private 'integration.json') (@{
            dataset_root='/dataset';url='http://127.0.0.1:8767';token_file='/labeling-private/token';token_type='legacy';
            webhook_secret_file='/labeling-private/webhook';cap_bytes=100000000000;disk_floor_bytes=5000000000
        } | ConvertTo-Json)
        Copy-Item (Join-Path $PSScriptRoot 'label-studio-bootstrap.py') (Join-Path $private 'bootstrap.py')
        'Configured local credentials and separate storage. Run Pull, then Start. Enable cat-watch mounts on its next approved restart.'
    }
    'Pull' {Invoke-Podman @('--connection',$Connection,'pull',$lock.image)}
    'Start' {
        if(!(Test-Path (Join-Path $private 'integration.json'))){throw 'Run Configure first.'}
        $existing=Invoke-Podman @('--connection',$Connection,'ps','-a','--filter',"name=^$labelContainer$",'--format','{{.Names}}')
        if($existing){
            $info=Invoke-Podman @('--connection',$Connection,'inspect',$labelContainer) | ConvertFrom-Json
            if($info[0].Config.Labels.app -ne 'cat-watch-label-studio'){throw 'Unexpected container ownership.'}
            $expectedImage=Invoke-Podman @('--connection',$Connection,'image','inspect',$lock.image,'--format','{{.Id}}')
            if($info[0].Image -ne $expectedImage){throw 'Existing container does not use the pinned image; preserve its state and replace it during an approved upgrade.'}
            Invoke-Podman @('--connection',$Connection,'start',$labelContainer) | Out-Null
        } else {
            Invoke-Podman @('--connection',$Connection,'run','-d','--name',$labelContainer,'--label','app=cat-watch-label-studio',
                '--network=host','--cap-drop=all','--security-opt=no-new-privileges','--cpus=2','--memory=4g',
                '--log-driver=k8s-file','--log-opt=max-size=2mb',
                '--mount',"type=bind,source=$state,target=/label-studio/data",
                '--mount',"type=bind,source=$private,target=/private,ro=true",
                '--mount',"type=bind,source=$dataset,target=/dataset,ro=true",
                '--entrypoint','python',$lock.image,'/private/bootstrap.py') | Out-Null
        }
        $ready=$false
        for($i=0;$i -lt 60;$i++){
            try {
                $null=Invoke-RestMethod 'http://127.0.0.1:8767/health' -TimeoutSec 2
                $ready=$true;break
            } catch {Start-Sleep -Seconds 2}
        }
        if(!$ready){throw 'Label Studio did not become ready; inspect its container logs.'}
        if(!(Test-Path (Join-Path $private 'pat'))){
            $token=[IO.File]::ReadAllText((Join-Path $private 'token')).Trim()
            $response=Invoke-RestMethod 'http://127.0.0.1:8767/api/token/' -Method Post -ContentType 'application/json' -Body '{}' -Headers @{Authorization=('Token '+$token)}
            Write-PrivateText (Join-Path $private 'pat') $response.token
            $token=$null;$response=$null
        }
        $config=Get-Content (Join-Path $private 'integration.json') -Raw | ConvertFrom-Json
        $config.token_file='/labeling-private/pat';$config.token_type='pat'
        Write-PrivateText (Join-Path $private 'integration.json') ($config | ConvertTo-Json)
        'Label Studio is ready with a personal access token: http://127.0.0.1:8767. Use Credentials to open local login details.'
    }
    'Stop' {
        $info=Invoke-Podman @('--connection',$Connection,'inspect',$labelContainer) | ConvertFrom-Json
        if($info[0].Config.Labels.app -ne 'cat-watch-label-studio'){throw 'Unexpected container ownership.'}
        Invoke-Podman @('--connection',$Connection,'stop','--time','30',$labelContainer)
    }
    'Status' {Invoke-Podman @('--connection',$Connection,'ps','-a','--filter',"name=^$labelContainer$",'--format','{{.Names}} {{.Status}}')}
    'Credentials' {Start-Process notepad.exe -ArgumentList ('"'+(Join-Path $private 'bootstrap.json')+'"')}
    'UsePAT' {
        $secure=Read-Host 'Paste a personal access token created in local Label Studio' -AsSecureString
        $ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try {Write-PrivateText (Join-Path $private 'pat') ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr))}
        finally {[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)}
        $config=Get-Content (Join-Path $private 'integration.json') -Raw | ConvertFrom-Json
        $config.token_file='/labeling-private/pat';$config.token_type='pat'
        Write-PrivateText (Join-Path $private 'integration.json') ($config | ConvertTo-Json)
        'PAT configured. Apply at the next approved cat-watch restart.'
    }
}
