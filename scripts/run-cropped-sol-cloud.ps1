$ErrorActionPreference='Stop'
$env:PATHEXT=[Environment]::GetEnvironmentVariable('PATHEXT','Machine')
$catCredentialPath=Join-Path $env:LOCALAPPDATA 'TapoCatMonitor\openai.credential.xml'
if(!(Test-Path $catCredentialPath)){throw 'The existing project OpenAI credential is unavailable; nothing was sent.'}
$catCredential=Import-Clixml $catCredentialPath
try {
    @{api_key=$catCredential.GetNetworkCredential().Password}|ConvertTo-Json -Compress|
        & wsl.exe -d RHEL10 -u alex -- bash /home/alex/dev/cat-watch/scripts/run-cropped-sol-campaign.sh cloud
    $catCode=$LASTEXITCODE
} finally {$catCredential=$null}
if($catCode -ne 0){throw 'Campaign stopped. Inspect the durable ledger; never reset authorization or retry an unknown request.'}
