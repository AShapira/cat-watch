---
name: run-cat-watch
description: Start or reuse this project's local cat-watch app, verify camera and detector readiness, and open its dashboard in the Codex internal browser. Use when asked to run, launch, or open cat-watch.
---

# Run cat-watch

Use the rootless RHEL Podman deployment introduced on 9 November 2026. Active
data are in `/home/alex/.local/share/cat-watch/data`; the old Windows deployment
and its data are rollback copies. Read `docs/rhel-runtime.md` and the current
journal if recovery or migration details matter.

## Start and verify

Run [ensure-running.ps1](scripts/ensure-running.ps1) through Windows PowerShell,
using its Windows/UNC path. The helper starts or reuses `cat-watch.service` in
RHEL and supplies DPAPI camera credentials through stdin into private runtime
memory. It waits up to 180 seconds for camera readiness. A setup-only preview
is also a valid ready state when no investigation is active.

Do not start `podman-machine-default`, its old cat-watch container or the legacy
analysis controller. Do not rebuild, reset data or change calibration merely to
launch the app. Use targeted diagnostics for a failed start instead of a restart
loop. Never print credentials or recorder process arguments.

Quiet mode follows the Windows console display state: on/dimmed/unknown/stale
means quiet; only a fresh off state permits heavy work. Preserve the separate
training pause in both modes. Check `/api/health` performance state and
`/api/learning/status` alongside camera, detector, frame age and recording reserve.
See `docs/rhel-runtime.md` for service and display-watcher recovery.

## Open the internal browser

When the dashboard responds, discover/call `mcp__codex_app__open_in_codex` with:

```json
{"target":{"type":"browser","url":"http://127.0.0.1:8765"}}
```

Omit `threadId` to target the current task. Open the dashboard even if its health
reports a camera or detector problem, and describe that problem accurately.
Use the tool result as evidence of the browser action: `queued` means queued,
not confirmed visible. If the tool is unavailable, provide the dashboard link
and state that the internal tab could not be opened. Do not launch an external
browser with `Start-Process`, `cmd /c start`, or `xdg-open` unless requested.

Finish with the dashboard link and concise live status. Active investigation readiness
requires `camera: connected` and `detector: ready`; also check `calibrated`, frame
age, and `storage.recording_allowed`. If uncalibrated, direct the user to
Camera & settings to draw the three areas. Do not silently modify calibration.

## Recording authorization

Resume an existing authorized continuous session using its saved confirmed
calibration. When no investigation is active, preview with `preparation: true`
is the expected ready state. Require fresh calibration confirmation before a
new investigation; do not start recording merely to obtain a preview.
