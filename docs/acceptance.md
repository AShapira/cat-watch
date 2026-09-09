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

### Pending

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
