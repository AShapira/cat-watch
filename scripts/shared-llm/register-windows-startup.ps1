# Launch the owned WSL user service at Windows logon. No machine wake or credentials.
[CmdletBinding()]
param([string]$Distribution='RHEL10',[string]$LinuxUser='alex')
$ErrorActionPreference='Stop'
$name='SharedLocalQwen'
$description='Owned by catwatch-shared-llm; starts the GPU-resident local inference service at sign-in.'
$previous=Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if($previous -and $previous.Description -ne $description){throw 'Refusing to replace an unrelated startup task'}
if($Distribution -notmatch '^[a-zA-Z0-9_-]+$' -or $LinuxUser -notmatch '^[a-zA-Z0-9_-]+$'){throw 'Invalid distribution or user name'}
$user=[Security.Principal.WindowsIdentity]::GetCurrent().Name
$action=New-ScheduledTaskAction -Execute (Join-Path $env:WINDIR 'System32\wsl.exe') -Argument "-d $Distribution -u $LinuxUser --exec /usr/bin/systemctl --user start shared-qwen.service"
$trigger=New-ScheduledTaskTrigger -AtLogOn -User $user
$principal=New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
Register-ScheduledTask -TaskName $name -Description $description -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
$task=Get-ScheduledTask -TaskName $name
[ordered]@{task=$task.TaskName;state=[string]$task.State;run_level=[string]$task.Principal.RunLevel;wake_to_run=$task.Settings.WakeToRun;start_when_available=$task.Settings.StartWhenAvailable;action=$task.Actions.Arguments}|ConvertTo-Json
