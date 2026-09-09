# cat-watch

A simple pet project, built for one household's specific requirements: one cat,
one fixed local camera, and three areas covering an eating pad, water fountain,
and litter box. It automatically counts **area visits**, keeps evidence segments,
and supports manual corrections and behavior labels.

The implementation is deliberately tailored to a particular setup: RHEL/WSL for
development, Windows Podman Desktop for containers, an NVIDIA GPU, Windows-local
storage, manual startup, and Asia/Jerusalem reports. It is an experimental personal
tool, not a general-purpose pet-monitoring product or a turnkey installation for
arbitrary cameras and operating systems. Other environments will need adaptation.

**Presence is not proof of eating, drinking, urination, or defecation.** Automatic
events start with unknown behavior. Reviewed behavior is reported separately.
This application does not measure intake or diagnose health conditions.

## Run from Windows PowerShell

The original setup keeps source in RHEL10. All application image builds and containers use Windows
`podman.exe`, Podman Desktop's existing `podman-machine-default`, and connection
`podman-machine-default-root`. No RHEL container engine is used.

This repository assumes an already-provisioned foundation: a reachable local RTSP
camera with a camera account, NVIDIA CDI working in the Podman machine, a restricted
Windows data directory, `camera.json` containing the camera's `ip`, and the DPAPI
credential described below. The private workstation foundation helper is not part
of this repository. The application scripts reuse that setup rather than installing
or reconfiguring it.

Start the existing machine in Podman Desktop. Adjust the checkout path, then:

```powershell
$catWatch = '\\wsl.localhost\RHEL10\path\to\cat-watch\scripts\cat-watch.ps1'
& $catWatch -Action Build
& $catWatch -Action Check
& $catWatch -Action Start
& $catWatch -Action Status
# When finished:
& $catWatch -Action Stop
```

If PowerShell blocks the locally written script because the UNC source is
treated as remote, launch it with a **process-only** policy override:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $catWatch -Action Start
```

No persistent execution policy, firewall, router, GPU toolkit, or machine settings
are changed. Build downloads packages and the detector weights. Runtime loads
the packaged model and performs local inference. `Check` performs real GPU model
inference with networking disabled and tests camera TCP access from Windows.

Open **http://127.0.0.1:8765** on Windows. Use **Camera & settings** to draw the
three areas. Counting starts only after all three polygons are saved. Look at the
bottom-center detection marker when drawing the standing areas. Overlapping
areas produce no assignment where the marker belongs to more than one area.
The preview is sampled and delayed; it is not a real-time video player.

Monitoring starts manually. After a reboot, start Podman Desktop's machine and
run Start again. A stale container can be removed with Stop, which preserves
Windows data. No scheduled startup is installed.

## Data and decisions

- Main-stream video is copied into approximately five-second MP4 segments,
  aligned to camera keyframes. Audio is excluded. Detection uses two frames per
  second on the GPU; recording quality is independent of inference resolution.
  Capture times anchor camera-relative timestamps to the first completed file's
  Windows modification time. RTSP latency and timestamp drift are part of the
  boundary-error calibration; these are not synchronized camera sensor times.
- A visit requires two seconds of presence. It closes after five seconds without
  presence, ending at the last observation. Both thresholds are configurable.
  Brief missing detections within a visit are bridged; duration is an estimate
  between observed boundaries, not exact behavioral time.
  A cat concealed inside a covered litter box can be missed or have an early
  visit end. Validate entrance/exit footage during calibration; visible area time
  is not a guaranteed measure of occupancy inside an opaque enclosure.
- Multiple cats interrupt tracking as ambiguous. Camera loss, processing gaps,
  restart, or a configuration change interrupt active visits. Monitoring coverage
  excludes unconfigured periods and gaps; zero recorded visits during a gap does
  not mean inactivity.
- Evidence includes about ten seconds before and after a visit where available.
  Long visits consist of consecutive clips; playback advances between segments.
  Interrupted or expired recordings may have partial evidence.
- Review can change area/times, reject events, add missed visits with overlapping
  evidence, split a visit, or merge two same-area visits at most 60 seconds apart.
  Merge/split preserve the original events as rejected, with an audit trail.
  Reports count only effective accepted decisions.
- Behavior labels are unknown, visit only, eating observed, drinking observed,
  or litter-box behavior observed. Reviewed labels are human decisions, not an
  automatically validated behavioral model. Merging resets behavior to unknown.
- Reports use Asia/Jerusalem civil dates. A crossing visit is counted on its start
  date, while duration is divided across dates. Review timestamp inputs explicitly
  use ISO 8601 with `Z` or a numeric offset. CSV exports include coverage and
  reviewed behavior counts.

## Storage and credentials

The foundation owns `C:\Alex\data\tapo-cat-monitor`, its camera configuration,
and diagnostic recordings. cat-watch owns only its `cat-watch` child directory,
marked with `.cat-watch-data`. The existing restricted Windows ACL is inherited.
RHEL may be stopped after deployment; the running image and Windows media do
not depend on a source bind mount.

The default cap is **50,000,000,000 bytes**. Application media, the rolling buffer,
SQLite database, manifest, and other files in the owned directory count toward
the cap. Container images and Podman's bounded 2 MB container log are separate.
Existing foundation diagnostics are neither counted nor deleted. The
foundation's `cap_enforced: false` flag remains historical; current app quota
status is visible in the dashboard and `/api/health`.

Retention removes old unused rolling segments, then oldest retained evidence to
leave a 64 MB recording reserve. It protects recent segments and active playback.
Older segments of a very long visit can expire. A recorder segment over 32 MB or
a stalled stream is interrupted. Checks run every two seconds; this is application
quota enforcement with a reserve, not an OS filesystem quota. Recording pauses
when the cap or the 256 MB disk-free floor prevents reservation. Lowering a cap
below current non-deletable data pauses capture until room is available.

Events, corrections, and coverage survive clip expiry. The database is not
automatically purged; if metadata consumes the budget, capture pauses instead.
SQLite uses rollback journaling and a single application owner, avoiding WAL
shared-memory assumptions on the Windows bind mount.

The existing DPAPI credential at
`%LOCALAPPDATA%\TapoCatMonitor\camera.credential.xml` is decrypted only by the
same Windows user. It travels through `podman exec` standard input to a private
Unix socket, then stays in process memory. It is not placed in environment
variables, container command metadata, the database, or logs. FFmpeg's internal
process arguments temporarily contain the authenticated RTSP URL; this follows
the foundation's trusted single-user workstation model. Never publish an
unredacted process listing from the recorder.

## Development and verification

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m pytest -q
node --check catwatch/static/app.js
```

RHEL tests use synthetic observations and temporary files, without a GPU or
camera. Run application container acceptance through the Windows script. The
image includes `/opt/python-lock.txt` and `/opt/models/SHA256SUMS` for the actual
built dependency/model inventory.

See [acceptance](docs/acceptance.md) for measured checks and the calibration/trial
procedure. Do not treat successful infrastructure or synthetic tests as measured
cat-detection accuracy.

## License

cat-watch's original code and documentation are available under the [MIT
license](LICENSE). Third-party components retain their own licenses. In particular,
the current Ultralytics detector and YOLO11n weights use AGPL-3.0 by default, so the
combined application is subject to those requirements and is not MIT-only. See
[third-party notices](THIRD_PARTY_NOTICES.md) and
[Ultralytics licensing](https://www.ultralytics.com/license).

Credentials, recordings, camera frames, local databases, model weights, and local
validation artifacts are excluded from this public source repository.
