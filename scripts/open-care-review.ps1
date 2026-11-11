# Loopback-only transport for the isolated review container. No cloud credential.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$env:PATHEXT=[Environment]::GetEnvironmentVariable('PATHEXT','Machine')
$podman=Join-Path $env:LOCALAPPDATA 'Programs\Podman\podman.exe'
try {
    $live=Invoke-RestMethod http://127.0.0.1:8767/api/batch -TimeoutSec 3
    if($live.items.Count -eq 100){Write-Output 'Care review is already reachable on localhost:8767';return}
} catch {}
$connections=& $podman system connection list --format json|ConvertFrom-Json
$connection=@($connections|Where-Object Name -eq 'podman-machine-default-root')[0]
$uri=[Uri]$connection.URI
if($uri.Host -ne '127.0.0.1' -or $uri.UserInfo -ne 'root'){throw 'Unexpected Podman transport; no tunnel started'}
# Read the PUBLIC SSH host key directly from the local WSL machine. This avoids
# trust-on-first-use or disabling SSH host verification. Never read a private key.
$public=& wsl.exe -d podman-machine-default -u root -- cat /etc/ssh/ssh_host_ed25519_key.pub
if($LASTEXITCODE -ne 0 -or $public -notmatch '^ssh-ed25519 [A-Za-z0-9+/=]+'){throw 'Cannot verify the local machine public host key'}
$parts=$public.Trim().Split(' ')
$folder=Join-Path $env:LOCALAPPDATA 'TapoCatMonitor'
$known=Join-Path $folder 'care-review-known-hosts'
('['+$uri.Host+']:'+$uri.Port+' '+$parts[0]+' '+$parts[1])|Set-Content -Encoding ascii $known
$stderr=Join-Path $folder 'care-review-tunnel-error.log'
$tunnelArguments=@('-N','-T','-i',('"'+$connection.Identity+'"'),'-p',$uri.Port,
    '-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
    '-o',('UserKnownHostsFile="'+$known+'"'),'-o','ExitOnForwardFailure=yes',
    '-o','ServerAliveInterval=30','-o','ServerAliveCountMax=3',
    '-L','127.0.0.1:8767:127.0.0.1:8767',($uri.UserInfo+'@'+$uri.Host))
$process=Start-Process -FilePath (Get-Command ssh.exe).Source -ArgumentList $tunnelArguments -WindowStyle Hidden -PassThru -RedirectStandardError $stderr -RedirectStandardOutput (Join-Path $folder 'care-review-tunnel-output.log')
$ready=$false
for($i=0;$i -lt 20;$i++){
    if($process.HasExited){throw 'Local tunnel exited; see its local error log'}
    try{$result=Invoke-RestMethod http://127.0.0.1:8767/api/batch -TimeoutSec 5;if($result.items.Count -eq 100){$ready=$true;break}}catch{}
    Start-Sleep -Milliseconds 250
}
if(!$ready){Stop-Process -Id $process.Id;throw 'Loopback review connection failed; only the new tunnel was stopped'}
@{started_at=[DateTime]::UtcNow.ToString('o');process_id=$process.Id;url='http://localhost:8767/';bind='127.0.0.1';host_key_verified_from_local_wsl=$true}|ConvertTo-Json|Set-Content -Encoding utf8 (Join-Path $folder 'care-review-tunnel.json')
Write-Output 'Care review is ready at http://localhost:8767/ through a verified loopback-only tunnel'
