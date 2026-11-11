[CmdletBinding()]
param([string]$DataRoot='C:\Alex\data\tapo-cat-monitor')
$ErrorActionPreference='Stop'
$env:PATHEXT=[Environment]::GetEnvironmentVariable('PATHEXT','Machine')
$OutputEncoding=New-Object System.Text.UTF8Encoding($false)
$camera=Get-Content (Join-Path $DataRoot 'camera.json') -Raw | ConvertFrom-Json
$credential=Import-Clixml (Join-Path $env:LOCALAPPDATA 'TapoCatMonitor\camera.credential.xml')
$services=@{}
foreach($entry in @(@('telegram_token','telegram.credential.xml'),@('openai_api_key','openai.credential.xml'))){
    $path=Join-Path $env:LOCALAPPDATA ('TapoCatMonitor\'+$entry[1])
    if(Test-Path $path){$secret=Import-Clixml $path;$services[$entry[0]]=$secret.GetNetworkCredential().Password}
}
$payload=@{ip=[string]$camera.ip;username=$credential.UserName;password=$credential.GetNetworkCredential().Password;services=$services}|ConvertTo-Json -Compress
try {
    $payload | & (Join-Path $env:WINDIR 'System32\wsl.exe') -d RHEL10 -u alex --exec /usr/bin/python3 /home/alex/.local/share/cat-watch/runtime/rhel-bootstrap.py
    if($LASTEXITCODE -ne 0){throw 'RHEL credential handoff or startup failed'}
} finally {$payload=$null;$credential=$null;$services=$null;$secret=$null}
