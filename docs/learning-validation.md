# Learning implementation validation — 2026-11-02

At this pre-deployment checkpoint, the implementation was in the working tree;
no commit, push, live upgrade, private image upload, or real Telegram delivery
had been performed. The later authorized live upgrade is recorded below.

| Check | Observed result |
| --- | --- |
| Full Python regression suite | 106 passed; one dependency deprecation warning |
| Final learning-specific suite after adding shadow rejection | 27 passed (includes one additional test beyond that full run) |
| Chromium desktop/mobile acceptance | Passed navigation, review, undo, disabled read-only actions, actual decoded crop pixels, no JS errors, no mobile overflow |
| Native RTX 5080 GPU smoke | Head and last-block forward/backward finite; Safetensors round-trip matched |
| Native full generated-video pipeline | Passed checkpoint interruption/resume, both training variants, independent test evaluation, FFmpeg extraction and live classifier; no alert-qualified class |
| PowerShell parser | All project scripts parsed successfully |
| Upgrade Plan action | Read-only plan succeeded; existing cat-watch remained stopped on 0.4.0 |
| Source hygiene | `git diff --check` and Python compilation passed |

The native pipeline ran with networking disabled, no live-data mount and temporary
container storage. It tested generated pixels, not the cat's behavior accuracy.
Browser screenshots are generated fixtures in `.artifacts/learning-ui/`.
The later final image changes concerned initial crop rendering, outbound crop
limits, and rejection of failed shadow candidates; these have browser/unit
coverage. Training and live-inference mechanics are unchanged from the passing
native pipeline.

Final image: `localhost/cat-watch:0.5.0`, immutable ID
`1873e968a101c03dea10799858feba6caa0f5c05c13286b1ae11e155a6b17f0b`.
The upgrade helper has only been run with `-Action Plan`. Its Apply path is
prepared and syntax-checked, but has not been run against the real workstation.
It backs up and checksums the application data, preserves the old stopped
container, and starts the new version. A live upgrade requires the user's
workstation-change confirmation. Fresh camera calibration is still required to
start continuous recording.

Open acceptance items: real timed labels and independent recording days, a
running configured local teacher, real-world model metrics/shadow observation,
and optional Telegram configuration plus an authorized delivery test. No
behavior quality, autonomous live alerting, or external delivery claim is made.


## Authorized live upgrade — 2026-11-02, 09:09 UTC

The user approved the Windows upgrade. Apply completed after verifying a full
snapshot (1,927 files; 9,817,682,118 bytes). The previous container remains
`cat-watch-before-learning-20261102T085928Z`; the backup directory is
`cat-watch-upgrade-20261102T085928Z` under the existing Windows data parent.
The running container is healthy and matches the image identity above.

Native Windows Edge checked Today and Learning against the live app, the ten-item
review queue, training gate, mobile layout and absence of JavaScript errors.
Camera preview is fresh at 2560×1440; recording and the detector remain stopped.
No labels or calibration were changed by the acceptance check.

The archive still reports 10 investigations, 217 groups and 17 group reviews.
At the snapshot the learning worker had 576 curated area clips; import completed
and extraction continued. These are crop-level cards, not independent confirmed
behavior examples. Suggestions and timed human reviews were both zero. The local
Qwen/Ollama dependency is unavailable; training is not ready. Telegram remains
disabled, and Telegram/cloud credentials are unconfigured.

See the [development journal](development-log.md),
[deployment snapshot](development-evidence/2026-11-02-upgrade.json), and
[native browser evidence](development-evidence/2026-11-02-windows-ui.json).
These observations supersede only the earlier deployment-pending status; they
do not establish real-cat accuracy, shadow qualification, or external delivery.

## 2026-11-02 — live collection recovery, version 0.5.2

The user confirmed the saved areas with the litter-box cover restored. Session 11
started at 09:25 UTC. Its first health timeout exposed an unbounded scan of protected
historical diagnostics; subsequent verification exposed filesystem accounting
holding the source database lock. Both were repaired, with previous containers
and checksummed data snapshots preserved. The detailed failure/recovery history
is in [the development journal](development-log.md#9-2026-11-02--confirmed-areas-first-collection-and-two-live-only-bottlenecks).

- Full repository run: **111 passed**, one existing deprecation warning,
  16.09 seconds (`.venv/bin/python -m pytest -q`).
- Targeted recording/retention run: **30 passed** after both corrections.
- Native PowerShell syntax validation passed.
- Current image: `localhost/cat-watch:0.5.2`, immutable ID
  `1a50a36141c6a0f13ccbd0855588968d2eaa4a5f0236dca83e4173ace3c3f1a7`.
- Three live probes at 09:49:35–09:50:05 UTC: **running healthy**, connected camera,
  ready RTX 5080 detector, advancing detection counts, 11–77 ms health responses.
  Capture gaps were zero after the last restart; three detector samples were
  dropped during this short interval. Earlier startup/repair gaps remain real.
- Native Edge Today/Learning/mobile acceptance passed during collection, without
  private image inspection or changes to labels or calibration.
- Teacher remains unavailable: 928 prepared review clips, zero suggestions and
  zero human-reviewed learning clips at 09:50. No real-cat model or Telegram
  delivery was qualified by this check.

See the [final progress evidence](development-evidence/2026-11-02-collection-final-progress.json),
[final status](development-evidence/2026-11-02-collection-final-health.json) and
[native UI result](development-evidence/2026-11-02-collection-ui.json).
