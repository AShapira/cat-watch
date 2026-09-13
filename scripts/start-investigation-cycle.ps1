# Start only an explicitly confirmed calibration. Does not launch/unload other models.
[CmdletBinding()]
param([ValidateRange(0.25,24)][double]$Hours=8,[ValidateSet('full_frame','areas')][string]$Scope='full_frame')
$ErrorActionPreference='Stop'
$prepared=Invoke-RestMethod http://127.0.0.1:8765/api/calibration
if(!$prepared.confirmed) {throw 'Draw and confirm the areas and masks in the app before starting.'}
$token=(Invoke-RestMethod http://127.0.0.1:8765/api/session).token
$body=@{calibration_id=$prepared.id;duration_seconds=[int]($Hours*3600);motion_scope=$Scope;masks=@($prepared.masks)}
Invoke-RestMethod http://127.0.0.1:8765/api/investigation -Method Post -Headers @{'x-catwatch-token'=$token} -ContentType 'application/json' -Body ($body|ConvertTo-Json -Depth 8)
