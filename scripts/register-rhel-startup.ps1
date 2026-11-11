[CmdletBinding()]
param([string]$InstallDirectory='C:\Alex\data\tapo-cat-monitor\rhel-runtime')
$ErrorActionPreference='Stop'
$name='CatWatchRHEL'
$description='Owned by cat-watch; starts its RHEL Podman service with a private credential handoff at sign-in.'
$existing=Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if($existing -and $existing.Description -ne $description){throw 'An unrelated task already uses this name'}
$script=Join-Path $InstallDirectory 'start-rhel.ps1'
if(!(Test-Path $script)){throw 'Install the startup helper first'}
$user=[Security.Principal.WindowsIdentity]::GetCurrent().Name
$action=New-ScheduledTaskAction -Execute (Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe') -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$settings=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 3) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal=New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $name -Description $description -Action $action -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $user) -Principal $principal -Settings $settings -Force | Out-Null
Get-ScheduledTask -TaskName $name | Select-Object TaskName,State
