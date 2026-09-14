# Fresh investigation validation — 12 September 2026

The user saved the new areas and confirmed calibration before application testing began. The historical archive was verified separately before the earlier destructive reset.

## Results

- 67 Python tests pass: multi-area matching, independent presence, unique groups, human behavior/history/conflicts, immutable calibration snapshots, required fresh confirmation, Broad/Focused motion, configurable durations, restart recovery, five-second evidence windows/grouping/readiness, deferred admission and failure recovery.
- Both isolated Playwright suites pass: area drawing and confirmation, confirmation surviving reload, capture controls and locking, review filters and overlays, behavior labels, historical thresholds, mobile layout, and no JavaScript errors.
- Native Windows PowerShell controller checks pass using the real scheduler with engine/network boundaries replaced: low/unavailable memory, ready-service reuse, explicit retry, startup failure, sequential stages, exact ownership matching, and preservation of pre-existing services.
- A controlled Windows Podman run used a separate temporary database and the user's polygons. Its API duration was 15 minutes; only the isolated test deadline was shortened to 45 seconds. The container restarted during capture and preserved that deadline. Eight full-frame camera segments contained 37.07 seconds of footage; the restart accounts for the capture gap. Fifteen detector frames were analyzed after restart. Capture stopped after the deadline plus five seconds, queues drained, and the live detector was released.
- A bounded two-second interval from that real recording completed the packaged detector comparisons, including the three area crops. Cosmos descriptions remained queued: the actual admission check required 9,991 MiB while 5,580 MiB was free. No unrelated GPU service was stopped. Actual Cosmos startup and unload were not exercised in this run because memory admission correctly rejected startup; those branches were exercised through the native controller boundary tests.
- Final Windows Edge acceptance passes against the deployed app: calibration confirmed, original calibration ID unchanged, Broad / eight hours selected, Start enabled, camera preview active, detector unloaded, and no investigation started.
- The production database passes SQLite integrity checking and has zero investigations, motions, visits, segments, and analysis jobs. One Windows analysis controller is running, idle until capture completes.
- All ten standalone historical highlight files were checksum-verified again. Original investigations and their full archives remain removed.

## Evidence and reproduction

Generated acceptance records and screenshots are in `outputs/fresh-refactor/` (not committed). `windows-capture-acceptance.json` records the isolated native capture; `windows-setup-check.json` records final production readiness.

Run from the repository root:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python tests/browser_smoke.py
.venv/bin/python tests/browser_investigation_review.py
```

Native Windows controller boundary checks: `tests/controller-acceptance.ps1`. The explicit short live-camera check is `tests/windows-fresh-acceptance.ps1`; it temporarily uses the app's port, isolates its database, and restores the idle production preview and saved calibration afterward. `tests/windows-setup-check.cjs` performs read-only checks in a separate headless Edge profile.

The deployed image is `localhost/cat-watch:0.3.0`, SHA-256 `309a931ffac2b276ea0053e541f7b910f03824d03ea0c22c2c8364de9eefb135`.

These checks validate the workflow, not cat-behavior accuracy. Actual cat appearances in the newly positioned areas still need review during the next investigation. The full eight-hour investigation has deliberately not been started.

## Focused capture and shared Qwen checkpoint — 13 September 2026

The updated app is deployed for calibration, with Focused / 20% per-side trigger buffer / 50% analysis crop context / eight hours / deferred analysis selected. Five-second pre/post padding and original presence polygons remain in use. The short Windows camera acceptance run is pending the user's fresh calibration confirmation; no new investigation has started.

- 80 Python tests pass, including native-pixel crop mapping and duplicate suppression, buffered masks and exclusions, immutable snapshots, independent overlapping presence filters and unique group counts, sustained presence without bridging evidence gaps, historical queue isolation, Qwen checkpoint reuse, bounded overload retries, and timeout recovery.
- Both isolated Playwright suites pass, including buffer previews, capture locking, dynamic model filters, native crop playback, zoom, PNG download dimensions, human review, and mobile layout. Windows controller boundary tests pass for shared-service reuse, unavailable service, independent comparison admission, and preserving services owned by other applications.
- A standalone request to the existing shared Qwen3.5-9B used 16 timestamped 510×489 source crops. It completed in 6.49 seconds with 4,166 input tokens and 65 output tokens. Model digest and reported VRAM use were unchanged afterward. The answer was cautious but speculated about eating or drinking; this verifies the interface, not behavior accuracy. Suggestions remain separate from human labels. This request did not consume any historical analysis job.
- Before/after hashes of historical investigation, motion, observation, job, event, review/history, and segment records match. All 1,110 retained media paths and sizes match; 136 historical Cosmos descriptions remain queued. Media contents were not rehashed in this read-only preservation check.
- Deployed Windows Edge checks confirm a fresh unconfirmed calibration draft, all three buffered outlines, the next-run defaults, native 2560×1440 preview, stopped detector, no capture, and Start disabled until confirmation.

Evidence is under `outputs/focused-qwen/` (not committed). The dedicated Windows setup check is `tests/windows-focused-check.cjs`; it may prepare an unconfirmed draft but never saves polygons or starts capture. The short camera test remains `tests/windows-fresh-acceptance.ps1` and must only run after user confirmation.

The deployed image is `localhost/cat-watch:0.4.0`, SHA-256 `092c5fd6a70ef856f65d06aad146944a2fd600315849b7ce1b9643f8e340808b`. Rollback container `cat-watch-rollback-20260913T180118Z` and SQLite backup `/data/backups/pre-investigation-20260913T180118Z.sqlite3` are retained. Live cropped-detector throughput, representative day/night accuracy review, and the complete Windows capture-to-Qwen path still require acceptance; the previous broad investigation is not evidence of those new behaviors.

## 0.3.0 source release validation — 13 September 2026

The release checkout passed all 67 Python tests, both isolated Playwright suites, the native Windows controller boundary tests, and JavaScript syntax checks. Live camera, GPU inference, and deployment acceptance were not repeated for this source release; the deployment observations above are the 12 September checkpoint. No GitHub Actions workflows are configured.
