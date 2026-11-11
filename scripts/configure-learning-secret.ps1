# Run interactively on Windows. No secret is accepted as a command-line argument.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][ValidateSet('Telegram','OpenAI')][string]$Service)
$ErrorActionPreference='Stop'
$folder=Join-Path $env:LOCALAPPDATA 'TapoCatMonitor'
New-Item -ItemType Directory -Force $folder | Out-Null
$secret=Read-Host "Enter $Service token (stored with Windows DPAPI for this user)" -AsSecureString
if($secret.Length -eq 0) {throw 'Empty token was not saved.'}
$credential=New-Object System.Management.Automation.PSCredential($Service,$secret)
$credential | Export-Clixml (Join-Path $folder ($Service.ToLower()+'.credential.xml'))
$secret=$null; $credential=$null
Write-Output 'Credential saved. It takes effect on the next application start. This does not enable messages or approve cloud batches.'
