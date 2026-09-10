# Acceptance record

## Automated checks

RHEL tests cover visit debounce, stationary presence, pass-bys, transitions,
interruptions/recovery, ambiguous polygons, midnight/DST reporting, original
observation preservation, transactional split/merge, quota expiry, playback
protection, disk exhaustion, unowned-file preservation, local-origin controls,
reviewed behavior counts, CSV generation, and HTTP range playback.

### Verified on 2026-09-09

- RHEL: **16 tests passed**; JavaScript syntax checks passed. One test-library
  deprecation warning remains (Starlette's AnyIO portal type alias).
- Isolated Chromium UI smoke: drawing and saving three polygons, reviewing an
  event, and updating its report passed with no JavaScript errors. Synthetic
  events used a temporary test database, never the live camera database.
- Windows `podman.exe` build passed on `podman-machine-default-root`.
  Image `localhost/cat-watch:0.1.0`:
  `859abf9686739ee812562218ffbd85ddf8c69a89a94d545c207f8396f76f3304`.
- Real YOLO model inference passed on **NVIDIA GeForce RTX 5080**, including a
  separate `--network=none` GPU check. The running app reports detector ready.
- Existing encrypted credentials successfully authenticated the camera. Live
  capture produced bounded main-stream MP4 segments and fresh preview frames.
- Native **Windows Edge 152.0.4191.66**, in an isolated temporary profile, rendered
  the dashboard and decoded/played a **1280 x 720** evidence segment. Its measured
  duration was 5.475456 seconds; playback advanced beyond 1.5 seconds. The test
  browser and its temporary profile were removed after verification.
- Both Windows and the Podman machine reported a listener only on
  **127.0.0.1:8765**. No router or firewall settings changed. This is host binding
  evidence; no separate physical LAN device was used for an external probe.
- The app data folder inherited the restricted Windows ACL: no unexpected allow
  identities beyond the Windows user, administrators, and SYSTEM.
- Manual Stop/Start passed with Windows data preserved and subsequent GPU/camera
  readiness. Native rolling-file expiry kept unconfigured preview storage bounded;
  forced quota/disk-exhaustion cases were tested with temporary RHEL data.

The timestamp implementation was corrected during native acceptance: segmentation
uses relative camera PTS, anchored to the first completed file's modification
time. Epoch PTS directly supplied to FFmpeg caused invalid initial boundaries.

### Pending as of 2026-09-09

The live deployment is waiting for the user to draw and save the three actual
areas. Area calibration, the 30-visit labeled accuracy sample, and the 24-hour
activity trial are **not complete**. No measured cat-detection accuracy is claimed.

The inspected live view shows a covered litter box. A cat hidden inside may cease
to be detectable: v1 measures visible area presence, not guaranteed time inside
the enclosure. Include entry, hidden occupancy, and exit in litter-area calibration;
do not interpret an early automatic end as proof that the cat left the box.

## Camera calibration (requires local review)

1. In Camera & settings, draw each of the three standing areas, then save them.
   Check the yellow detection marker against the boundaries while the cat moves.
2. Gather at least ten independently reviewed visits per area, including pass-bys,
   stationary visits, boundary movement, and both day/night lighting. Keep the
   labels and clips in Windows application storage, outside Git.
3. For a fixed review period, independently list expected visits and their times;
   compare these against the automatic **original** observations, before edits.
   Match visits one-to-one by area and temporal overlap. Count unmatched expected
   visits as false negatives and unmatched automatic visits as false positives.
4. Record precision = TP/(TP+FP), recall = TP/(TP+FN), and median absolute start/end
   boundary error for matched visits. Targets: precision and recall >=90%, median
   boundary error <=3 seconds. Results must include sample size and lighting.
   If thresholds or areas are tuned, measure again on a separate sample.
5. Behavior labels are a review workflow; no automatic behavior accuracy is claimed.

## 24-hour trial

After calibration, record the start time and keep Windows powered on with the
Podman machine and app running. At the end, export the report and record:

- elapsed period, coverage and all gaps, with reasons where known;
- visit counts per area, review corrections, and playable evidence samples;
- data usage, configured cap and whether capture ever paused;
- day/night samples and the calibration metrics above.

A trial with unconfigured areas is not an activity-monitoring trial. The trial is
complete only after 24 elapsed hours and review of these results. Manual stop,
Windows restart, or camera outage must be reported as gaps, not silently omitted.

## Motion investigation rollout — 2026-09-10

- Additive migration and Windows deployment passed. Current 0.2.0 image:
  `c124b8a8759cd7dd879dd219edac81038983508316419458ec8f3557f1d41001`.
  Integrity-checked backups and stopped rollback containers were retained for
  deployments at 03:31:17 and 03:47:13 UTC. The second restart produced a recorded
  seven-second gap between the last diagnostic and application recovery, plus
  four skipped detector samples during model startup. This gap record does not
  measure every frame lost while the camera connection restarted.
- ONVIF capabilities confirmed 2560×1440 support. The native Windows quality
  helper applied and read back H.264, 2560×1440, 15 fps. Saved-file probing and
  Windows browser decoding confirmed original 1440p; per-segment average fps
  varies around 15 because camera packet timestamps are uneven. Motion processes
  every decoded frame. Analysis timestamps use frame index / segment average
  fps; the recorded stream is unchanged.
- **28 tests passed**, including synthetic video motion without a GPU, debounce,
  timestamp masking, shadow/light changes, linked continuous movement, retention,
  quota/leases, durable jobs/deadlines, and four-fps video input sampling. Isolated
  Chromium checked investigation controls, editable masks and stop, with no JS
  errors. Quota tests used temporary data, never live recordings.
- Windows Edge played 2560×1440 evidence and automatically advanced from segment
  0 to segment 1. Screenshots are in ignored `outputs/investigation-screens/`.
  Codex's internal-browser opening was queued. Its Computer Use helper failed
  before initialization with a WSL working-directory URI error, so playback
  inside that exact browser remains a manual acceptance item.
- Captured real motion while Cosmos was unavailable and during its initial
  out-of-memory startup failure. Retained evidence survived the app redeployment.
  YOLO11n/640, YOLO11m/640 and YOLO11m/1280 completed comparison on the same clips.
- Cosmos 3 Edge reasoner-only vLLM loaded BF16 weights (4.67 GiB). The initial
  50% allocation could not fit the requested context; 55% started successfully.
  Startup reported approximately 8.74 GiB total allocation including KV cache.
  A subsequent whole-GPU reading was 12,643 MiB, including detection and Windows.
  WDDM per-process memory reporting returned N/A. Stopping only Cosmos reduced
  total use to 2,906 MiB: a differential estimate of 9,737 MiB (9.51 GiB),
  within the 10 GiB target. This is not a guaranteed upper bound across all clips.
- Found and fixed a video pixel-budget mistake: the processor limits pixels
  across the whole window. The corrected 32×448×256 budget and disabled thinking
  produced concise real-video responses, with 32 sampled frames per full window.
  Earlier descriptions were marked failed and excluded from normal display;
  corrected reanalysis remains unverified model output. Some descriptions still
  confuse animals or miss subtle motion, so no behavior accuracy is claimed.
- Initial acceptance diagnostics included 14 cat candidate frames above the
  production threshold, all rejected by area assignment. A reviewed source frame
  shows the cat on the floor outside the saved polygons. This demonstrates one
  present failure path; it cannot explain every earlier unretained hour.

The saved polygons and counter-mounted fountain were preserved. The user has
agreed to perform physical movement checks. Confirmation that floor, fountain,
and litter checks are complete is still pending. Session 1 is the acceptance
session; a fresh 24-hour trial must start only after those checks and padding
verification. Day/night labeled review and measured recall remain pending.

The final saved Cosmos serving configuration also passed a fresh container start
and a 32-frame real-video request. Whole-GPU usage was 12,261 MiB with the service
active versus the earlier 2,906 MiB baseline without it (approximately 9.14 GiB
incremental use). Capture remained connected during this separate service restart.

## User-requested stop — 2026-09-10 evening

The user stopped the noisy investigation. The live API showed motion lag of
approximately 731 seconds and detector lag of 875 seconds; a fresh authenticated
Stop request did not promptly complete. This establishes severe backlog and an
unresponsive stop path, without proving one underlying performance cause.

Both containers were paused before archiving. The frozen copy contains 4,618
files, 10,705,473,804 bytes, and a SHA-256 manifest, under Windows
`C:\Alex\data\tapo-cat-monitor\investigation-archives\session-1-20260910T173413Z`.
It is outside automatic application retention. It includes all remaining media,
database/journal files, existing results, inputs, models and earlier backups.
Data that had already expired before this copy cannot be recovered by archiving.

The worker containers were then stopped, the session stop time persisted, open
motions marked interrupted, and queued/running analysis records paused. A
separate consistent stopped-state SQLite backup accompanies the untouched frozen
copy. Database integrity passed. This session is stopped, not a completed and
validated 24-hour trial. The new review-only mode passed its read/write boundary
test; the complete automated suite now has 29 passing tests.

## Investigation review tools — 2026-09-10 evening

Deployed grouped motion cards, saved-detector confidence/area/model filters,
analysis and human-review filters, source-video overlays with jump-to-cat, and
versioned human labels with append-only history. Missing or failed analysis is
excluded from negative evidence; failed reruns retain previous positive results.
Area overlays use current saved polygons and the existing bottom-centre rule.
No detector, polygon or visit-recognition algorithm was changed.

- The automated suite passed all 35 tests. The isolated investigation browser
  test passed filtering, video seeking, overlays, label persistence/history and
  mobile layout. The existing browser smoke test also passed.
- Native Windows Edge verified the deployed app: 36 candidate groups at score
  0.4, original 2560-pixel-wide video playback, and a YOLO11m/1280 overlay on
  group 208. Live acceptance did not save any human labels. Results and screenshots
  are in ignored `outputs/investigation-review/`.
- Inventory before and after deployment matched: 206 motion entries, 145 groups,
  and 1,717 source segments. A consistent database backup passed integrity check
  at `/data/backups/pre-review-ui-20260910T195713Z.sqlite3`. The previous stopped
  review container is `cat-watch-review-rollback-20260910T195713Z`.
- Deployed image ID:
  `0004bafe378dfbefb916a737c94546721a664300d0d26ad503a29b73ecd3f3c9`.
  The live API confirmed review-only mode, camera stopped and video description
  stopped. Recording, model workers and automatic retention remain disabled;
  authenticated human review is the permitted mutation.

These checks establish review-tool behavior, not improved cat-presence accuracy.
Human-reviewed examples are still needed to evaluate changes to the three areas.
