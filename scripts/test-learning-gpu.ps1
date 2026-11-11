[CmdletBinding()]
param([string]$Image='localhost/cat-watch:0.5.3', [switch]$FullPipeline)
$ErrorActionPreference='Stop'
$env:PATHEXT=[Environment]::GetEnvironmentVariable('PATHEXT','Machine')
$podman=Join-Path $env:LOCALAPPDATA 'Programs\Podman\podman.exe'
$name=if($FullPipeline){'learning-pipeline-smoke.py'}else{'learning-gpu-smoke.py'}
$script=Get-Content (Join-Path $PSScriptRoot $name) -Raw
$script | & $podman --connection podman-machine-default-root run --rm -i --network=none --read-only --tmpfs /tmp:rw,size=8g --device nvidia.com/gpu=all --cap-drop=all --security-opt=no-new-privileges $Image python -
if($LASTEXITCODE -ne 0) {throw 'GPU smoke failed; no live data or deployment was modified.'}
