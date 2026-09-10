# Motion investigation

Investigation records motion throughout the camera view independently of cat
detection, area assignment, GPU availability, and video descriptions. It does
not guarantee that every physical movement is detected. Untriggered video
expires after the temporary two-minute buffer, so test sensitivity before
starting the 24-hour trial.

## Native Windows deployment

Source remains in RHEL10; all containers use Windows Podman Desktop. From
PowerShell, set `$scripts` to this checkout's `scripts` directory (a WSL UNC
path is supported), then run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$scripts\camera-quality.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$scripts\camera-quality.ps1" -Apply
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$scripts\cat-watch.ps1" -Action Build
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$scripts\cat-watch.ps1" -Action Check
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$scripts\deploy-investigation.ps1"
```

The quality helper reads ONVIF encoder capabilities before requesting 2560×1440
at 15 fps. If the camera rejects that interface, use **Tapo → camera → Settings →
Video & Display → Video Quality → 2K QHD / 4MP**, then verify saved source files.
The application copies H.264 packets; it never upscales or reduces the recording
frame rate for inference. Normal keyframe boundaries add a few seconds around
the requested evidence interval. Audio remains excluded.

Deployment creates and integrity-checks an online SQLite backup in the owned
`cat-watch/backups` directory, then retains the stopped previous container as
`cat-watch-rollback-<timestamp>`. The schema migration is additive. Deployment
time is recorded in `cat-watch/deployment-<timestamp>.json`; this interruption is
a monitoring gap. No image or data pruning is performed by the deployment helper.

## Local NVIDIA descriptions

`scripts/cosmos.lock.json` pins the public Cosmos 3 Edge checkpoint revision and
vLLM container digest. Model files belong in
`C:\Alex\data\tapo-cat-monitor\cat-watch\models\Cosmos3-Edge`. Download and
verify the pinned revision with a current Hugging Face CLI (`hf`):

```bash
hf download nvidia/Cosmos3-Edge --revision a9d944e2c6a1bf9f48b92ad16348e70c5f1836ba \
  --local-dir /mnt/c/Alex/data/tapo-cat-monitor/cat-watch/models/Cosmos3-Edge \
  --exclude 'assets/*' --exclude 'images/*' --exclude 'vae/*'
hf cache verify nvidia/Cosmos3-Edge --revision a9d944e2c6a1bf9f48b92ad16348e70c5f1836ba \
  --local-dir /mnt/c/Alex/data/tapo-cat-monitor/cat-watch/models/Cosmos3-Edge
```

Omitted example assets and video VAE are intentionally not downloaded. After
checksum verification succeeds, write the exact revision to
`models/Cosmos3-Edge/.cat-watch-revision`. Then run
`cosmos.ps1 -Action Start` using native Windows PowerShell. `Status` and `Logs`
inspect the service; `Stop` releases its GPU memory. `Start` reuses or resumes an existing container after checking its label and pinned
image; configuration changes require a deliberate container replacement.

The service binds only `127.0.0.1:8766`. It mounts the model and the app's
`analysis-input` directory read-only, not the camera credentials or database.
HF offline mode and telemetry opt-outs are enabled. No cloud inference fallback
exists. The application creates bounded eight-second, 448-pixel-wide, four-fps
input clips; these do not replace original evidence. The processor pixel budget
is 32×448×256 for the whole window, not a per-frame limit. The service allows one
request at a time with a 512-token output limit and an 8,192-token context and uses 55% of GPU memory as its
initial allocation target. Verify actual VRAM and latency with the recorder and
detector active. Container/package presence alone is not video acceptance.

Model files and temporary model inputs count within the application's 50 GB
cap; container images remain in Podman's separate image storage. Generation
components are not loaded by the reasoner-only runtime, though NVIDIA's shared
checkpoint shards contain both reasoner and generator tensors.

## Operation and interpretation

Open **Investigation**, inspect the preview/mask, then select **Start 24-hour
investigation**. The initial exclusion covers the changing timestamp at the
upper left. Red rectangles are editable with two corner clicks; changes do not
alter the three visit polygons. Initial sensitivity is 0.05% changed pixels
for 0.2 seconds. Changes in lighting and shadows count as movement.

Motion events preserve ten seconds of padding. Nearby events are merged when
their padding overlaps. Long movement is split into linked 60-second chunks.
At the persisted deadline, investigation stops accepting new movement and
finishes padding. Ordinary cat monitoring continues. Restarts preserve the
original deadline and interrupt active motion records rather than inventing
coverage. Decoding/queue failures retain their affected interval as explicit
interrupted evidence, where the recording is available.

The motion list provides original video playback, thumbnails, descriptions,
and comparison results. YOLO11n at 640 pixels remains the baseline. Background
comparison evaluates YOLO11n/640, YOLO11m/640 and YOLO11m/1280 on identical
two-fps source samples with confidence >=0.1, across all object classes.
Original visit decisions continue using the configured cat confidence threshold.
No model suggestion changes reviewed behavior or calibration automatically.

Descriptions wait in a persistent queue while Cosmos is unavailable. Completed
or failed jobs can be rerun with **Analyze again**. If evidence expires before
analysis, the job reports failure; model work never pins unbounded old footage.
Seven days of diagnostic observations are retained; event and job history
survives evidence expiry. Diagnostics explain low-confidence/no-cat observations,
multiple cats, area rejection, sampling gaps, and entry progress.

## Acceptance and trial

1. Verify saved stream dimensions/fps and fresh motion-processing timestamps.
2. Run a short manually stopped acceptance session. Move at the floor, beside
   the counter-mounted fountain, and near the litter area; note the times.
3. Confirm each movement produced playable original-quality evidence with
   padding. Include shadow/light changes and verify clock-only changes do not
   trigger continuous recording. This physical check needs a person at the scene.
4. Confirm model failure does not prevent clips, and inspect a real local video
   description and detector comparison. AI descriptions remain unverified.
5. End acceptance, allow padding to finish, then start a fresh 24-hour session.
   Leave Windows and Podman running. Investigations do not install auto-start.
6. After the deadline, independently review day/night examples. Report sample
   size, missed movements, false triggers, detector recall/precision, area/rule
   rejections, gaps, storage expiry, and actual GPU resource consumption. A
   completed timer alone is not validated cat-behavior accuracy.

API additions: `GET/POST/PATCH /api/investigation`,
`POST /api/investigation/stop`, paginated `/api/investigation/motions`,
`/api/investigation/jobs`, and `/api/investigation/observations`. Motion details,
thumbnails and reanalysis are under `/api/investigation/motions/{id}`. `GET /api/investigation/report` exports session diagnostics. All writes
retain the existing session-token and local-origin controls.

NVIDIA sources: [Cosmos 3 Edge model card](https://huggingface.co/nvidia/Cosmos3-Edge)
and [reasoner runtime guidance](https://github.com/NVIDIA/cosmos/blob/main/cookbooks/cosmos3/reasoner/README.md).

## Stop and preserve everything

For a frozen investigation, copy the complete application data while its workers
are paused into a separate directory outside the application's retention root.
Keep the SQLite journal/WAL alongside the original database and record checksums.
Stop the workers before opening/recovering that database. Preserve pending jobs
as paused records; do not discard their history or claim they completed.

`scripts/review-cat-watch.ps1` launches the existing database and clips in
review-only mode after the worker container is stopped. This mode needs no camera
credentials or GPU access, permits only authenticated human group-review writes,
and starts no capture,
analysis, recovery, or automatic retention workers. It retains the stopped
container under a timestamped name. Normal monitoring must be explicitly resumed
with the normal deployment workflow.


## Reviewing saved motion groups

The Investigation page groups linked motion chunks and filters the entire dataset
before pagination. Use **Show cat candidates**, set a minimum score (default 0.4),
and optionally filter by detector, current detected area, human review, analysis
status, model disagreement, time, or group duration. Filters are saved in the URL.
"No cat detected" includes only groups with complete comparison evidence for the
selected detector; failed or missing comparisons are not treated as negatives.
A failed rerun preserves the latest successful comparison and marks the group
incomplete. Detector output is a candidate, not a human-confirmed label.

Cards use a saved cat frame when available. **Review cat evidence** seeks to the
best retained detection for the selected detector and score. The video overlay
shows saved cat boxes, their bottom-centre assignment points, and the current
saved polygons. Samples are at roughly two fps; overlays disappear when no sample
is within 0.35 seconds of the playback timestamp. Alignment uses source segment
timestamps and is approximate. This view does not reconstruct unseen frames.
Historical baseline rejection counts keep their original meaning; current polygon
assignments are explicitly identified as current. Nothing edits calibration.

Human labels are Unreviewed, Cat confirmed, No cat, or Uncertain, with optional
presence areas and notes. They are stored separately from automatic visits,
detections, and Cosmos descriptions, with an append-only change history and
version checks for concurrent tabs. A label does not certify eating or drinking.
Review-only mode permits this single authenticated PUT endpoint while capture,
reanalysis, settings changes, and automatic deletion remain disabled.

The additive tables are `motion_analysis_cache`, `motion_group_reviews`, and
`motion_group_review_history`. The compact cache indexes completed comparison
results without GPU inference. It refreshes when the latest successful job changes.

To deploy this UI to an existing review-only instance, build using
`scripts/cat-watch.ps1 -Action Build`, then run `scripts/deploy-review-ui.ps1`
from Windows PowerShell. The deployer verifies review-only mode, backs up SQLite,
retains the old container, and checks motion/group/recording counts. On failure it
restores the old review-only container; neither path starts monitoring or Cosmos.

Validation: `.venv/bin/python -m pytest -q` and
`.venv/bin/python tests/browser_investigation_review.py`. The browser check uses
synthetic video and a temporary database on port 8768. It tests filtering,
continued groups, seek/overlay controls, persistent review labels, review-only
restrictions, and mobile layout without touching live investigation labels.
