# Label Studio integration acceptance — 14 September 2026

Implementation branch: `codex/label-studio-review`, based on the existing local
`4be0015` cat-watch checkout. The running Windows monitor was not restarted or
reconfigured. No real human activity labels were imported or deleted.

## Verified

- 104 Python tests passed. New coverage includes one-based inclusive to zero-based
  half-open intervals, single-frame labels, gaps, explicit negatives and coverage,
  uncertain/multiple-cat exclusions, revisions, conflicts, lost task creation
  responses, task deletion, source deduplication, fractional FPS, 120-second clip
  splits, quotas, interrupted exports, webhook authentication, read-only guards,
  snapshot checksums/recovery, tampered media and invalid-configuration isolation.
- Both existing isolated Chromium suites passed after replacing the removed review
  controls: calibration and capture controls; grouped filters, source seeking,
  overlays, Label Studio handoff, mobile layout; no JavaScript errors.
- Actual Label Studio Community 1.23.0 was installed in a separate test environment
  and exercised against disposable SQLite state. The real API accepted the project
  configuration, managed local-storage registration, actual authenticated webhook delivery and
  personal-token refresh. The browser successfully played a copied 2560×1440
  camera segment containing 90 frames at measured 14.677963942154552 FPS.
- Browser edit/save/reload preserved activity ranges, notes and per-region boundary
  flags. First/last frame selection matched the manifest. The Label Studio server was stopped and restarted with the same state, and a fresh bridge instance
  reconciled completed annotations, produced checksum-verified snapshots, and
  removed annotations/tasks from current totals after their deletion in Label
  Studio. The diagnostics hyperlink worked as a link; media used authenticated
  ranged responses.
- Native Windows PowerShell parsed all four changed deployment helpers without
  syntax errors. The official 1.23.0 OCI image digest was resolved from Docker Hub
  and recorded in `scripts/label-studio.lock.json`.

The copied footage, credentials, screenshots and generated databases remain in
isolated temporary directories and are excluded from Git. No cloud model was used
for activity inference. The annotation in the acceptance test is test data, not a
human-reviewed behavioral claim about the real recording.

## Reproduce

Use a separate Python environment; optional dependencies are pinned in
`requirements-labeling-test.txt`. Supply a local FFmpeg binary and installed
Chromium executable. The test refuses to run if its test port is occupied and
requires a new output directory.

```bash
python -m pytest -q
CATWATCH_TEST_CHROMIUM=/path/to/chrome python tests/browser_smoke.py
CATWATCH_TEST_CHROMIUM=/path/to/chrome python tests/browser_investigation_review.py
python tests/label_studio_acceptance.py \
  --label-studio /test-venv/bin/label-studio \
  --ffmpeg /path/to/ffmpeg --chromium /path/to/chrome \
  --output /tmp/cat-watch-labeling-acceptance-new
```

Set `CATWATCH_TEST_FFMPEG` for pytest when FFmpeg is not on PATH. By default the
real-service harness uses the committed synthetic clip. Add `--source` with a
readable recording to verify camera media; it copies that source into test storage.
The harness uses ports 18769/18770, stops its own Label Studio process on completion,
and writes `acceptance.json` into the output directory.

## Deployment validation still required

The pinned Windows Podman image and bind mounts have not been launched by this
change. Before calling production deployment accepted, use the deployment guide
to verify the native Windows startup/ACLs, loopback access, authenticated playback,
PAT setup, real webhook delivery, next completed investigation export, and a backup
restore rehearsal. This requires a separately approved deployment window. The
implementation tests do not establish activity-model accuracy or training quality.
