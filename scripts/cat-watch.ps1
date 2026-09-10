# Native Windows PowerShell 5.1+. RHEL supplies source only.
[CmdletBinding()]
param(
    [ValidateSet('Check','Build','Start','Stop','Status','Logs')][string]$Action = 'Status',
    [string]$DataRoot = 'C:\Alex\data\tapo-cat-monitor',
    [string]$Machine = 'podman-machine-default',
    [string]$Connection = 'podman-machine-default-root'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$env:PATHEXT = [Environment]::GetEnvironmentVariable('PATHEXT','Machine')
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$Podman = Join-Path $env:LOCALAPPDATA 'Programs\Podman\podman.exe'
if (!(Test-Path $Podman)) { $Podman = (Get-Command podman.exe -ErrorAction Stop).Source }
$Image = 'localhost/cat-watch:0.2.0'
$Container = 'cat-watch'
$AppData = Join-Path $DataRoot 'cat-watch'
$SourceRoot = Split-Path $PSScriptRoot -Parent
$CredentialFile = Join-Path $env:LOCALAPPDATA 'TapoCatMonitor\camera.credential.xml'

function Invoke-Podman {
    param([string[]]$Arguments)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $output = & $Podman @Arguments 2>&1; $code = $LASTEXITCODE }
    finally { $ErrorActionPreference = $previous }
    if ($code -ne 0) { throw "podman.exe failed (exit $code): $output" }
    return ($output | ForEach-Object { $_.ToString() }) -join "`n"
}

function Assert-Machine {
    $machines = Invoke-Podman @('machine','list','--format','json') | ConvertFrom-Json
    $selected = @($machines | Where-Object Name -eq $Machine)
    if ($selected.Count -ne 1 -or $selected[0].VMType -ne 'wsl') { throw 'Expected the existing Windows Podman WSL machine.' }
    if (!$selected[0].Running) { throw 'Start podman-machine-default in Podman Desktop, then retry.' }
    $connections = Invoke-Podman @('system','connection','list','--format','json') | ConvertFrom-Json
    $connectionItem = @($connections | Where-Object Name -eq $Connection)
    if ($connectionItem.Count -ne 1 -or $Connection -ne ($Machine + '-root')) { throw 'Connection must target the selected machine root connection.' }
    Invoke-Podman @('--connection',$Connection,'info','--format','{{.Host.Hostname}}') | Out-Null
}

Assert-Machine
switch ($Action) {
    'Check' {
        Invoke-Podman @('--connection',$Connection,'version')
        if (!(Test-Path (Join-Path $DataRoot 'camera.json'))) { throw 'Camera configuration missing; use the foundation helper.' }
        if (!(Test-Path $CredentialFile)) { throw 'Encrypted camera credential missing; use the foundation helper.' }
        $camera = Get-Content (Join-Path $DataRoot 'camera.json') -Raw | ConvertFrom-Json
        $tcp = New-Object Net.Sockets.TcpClient
        try {
            $task = $tcp.ConnectAsync([string]$camera.ip,554)
            if (!$task.Wait(5000) -or !$tcp.Connected) { throw 'Camera RTSP port unavailable.' }
        } finally { $tcp.Dispose() }
        Invoke-Podman @('--connection',$Connection,'run','--rm','--network=none','--device','nvidia.com/gpu=all','--cap-drop=all','--security-opt=no-new-privileges',$Image,'python','-m','catwatch','--check-gpu')
        Get-PSDrive -PSProvider FileSystem | Select-Object Name,Free
    }
    'Build' {
        Invoke-Podman @('--connection',$Connection,'build','--network=host','-t',$Image,'-f',(Join-Path $SourceRoot 'Containerfile'),$SourceRoot)
        Invoke-Podman @('--connection',$Connection,'image','inspect',$Image,'--format','{{.Id}}')
    }
    'Start' {
        $existing = Invoke-Podman @('--connection',$Connection,'ps','-a','--filter',"name=^$Container$",'--format','{{.Names}}')
        if ($existing) { throw 'cat-watch already exists. Use Status or Stop before Start.' }
        if (!(Test-Path $DataRoot)) { throw 'Foundation storage folder missing.' }
        New-Item -ItemType Directory -Path $AppData -Force | Out-Null
        # Marker confines recovery and retention to this application-owned subtree.
        $marker = Join-Path $AppData '.cat-watch-data'
        if (!(Test-Path $marker)) {
            if (@(Get-ChildItem -Force $AppData).Count -ne 0) { throw 'Refusing to adopt a nonempty unmarked data directory.' }
            'cat-watch-v1' | Set-Content $marker -Encoding ASCII
        }
        $camera = Get-Content (Join-Path $DataRoot 'camera.json') -Raw | ConvertFrom-Json
        $credential = Import-Clixml $CredentialFile
        $inputJson = @{ ip=$camera.ip; username=$credential.UserName; password=$credential.GetNetworkCredential().Password } | ConvertTo-Json -Compress
        Invoke-Podman @('--connection',$Connection,'run','-d','--name',$Container,'--label','app=cat-watch','--network=host','--device','nvidia.com/gpu=all','--cap-drop=all','--security-opt=no-new-privileges','--log-driver=k8s-file','--log-opt=max-size=2mb','--health-cmd','python -m catwatch --health','--health-interval','30s','--health-start-period','120s','--mount',"type=bind,source=$AppData,target=/data",$Image) | Out-Null
        # Transfer through exec stdin to a UID-restricted Unix socket, never CLI metadata.
        $previous = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $output = $inputJson | & $Podman --connection $Connection exec -i $Container python -m catwatch --credentials 2>&1
            $code = $LASTEXITCODE
        } finally { $inputJson = $null; $credential = $null; $ErrorActionPreference = $previous }
        if ($code -ne 0) { throw "cat-watch failed to start (exit $code)." }
        $ready = $false
        for ($i=0; $i -lt 90; $i++) {
            $health = $null
            try { $health = Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 2 } catch { }
            if ($health -and $health.detector -eq 'failed') { throw 'Detector initialization failed. Use Check and Logs.' }
            if ($health -and $health.detector -eq 'ready' -and $health.camera -eq 'connected') { $ready=$true; break }
            Start-Sleep -Seconds 2
        }
        if (!$ready) { throw 'Windows camera/GPU readiness check failed. Inspect Status and Logs; deployment is not accepted.' }
        Write-Output 'Dashboard: http://127.0.0.1:8765'
        $health | ConvertTo-Json -Depth 5
    }
    'Stop' {
        $existing = Invoke-Podman @('--connection',$Connection,'ps','-a','--filter',"name=^$Container$",'--format','{{.Names}}')
        if ($existing) {
            $label = Invoke-Podman @('--connection',$Connection,'inspect',$Container,'--format','{{.Config.Labels.app}}')
            if ($label -ne 'cat-watch') { throw 'Refusing to stop a container not labeled cat-watch.' }
            Invoke-Podman @('--connection',$Connection,'stop','--time','35',$Container)
            Invoke-Podman @('--connection',$Connection,'rm',$Container)
        }
        Write-Output 'Monitoring stopped; Windows data preserved.'
    }
    'Status' {
        Invoke-Podman @('--connection',$Connection,'ps','-a','--filter',"name=^$Container$",'--format','{{.Names}} {{.Status}}')
        try { Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 3 | ConvertTo-Json -Depth 5 }
        catch { Write-Output 'Dashboard unavailable.' }
    }
    'Logs' { Invoke-Podman @('--connection',$Connection,'logs','--tail','100',$Container) }
}
