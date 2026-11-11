[CmdletBinding()]
param([string]$Image='localhost/cat-watch:0.5.3', [string]$Connection='podman-machine-default-root')
$ErrorActionPreference='Stop'
$env:PATHEXT=[Environment]::GetEnvironmentVariable('PATHEXT','Machine')
$podman=Join-Path $env:LOCALAPPDATA 'Programs\Podman\podman.exe'
$source=Split-Path $PSScriptRoot -Parent
& $podman --connection $Connection build --network=host -t $Image -f (Join-Path $source 'Containerfile.learning') $source
if($LASTEXITCODE -ne 0) {throw 'Learning image build failed; the existing deployment was not modified.'}
& $podman --connection $Connection image inspect $Image --format '{{.Id}}'
