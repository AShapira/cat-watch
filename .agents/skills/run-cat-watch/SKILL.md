---
name: run-cat-watch
description: Start or reuse this project's local cat-watch app, verify camera and detector readiness, and open its dashboard in the Codex internal browser. Use when asked to run, launch, or open cat-watch.
---

# Run cat-watch

Use the existing Windows Podman deployment. Source lives in RHEL/WSL; the
dashboard and camera credentials belong to Windows. Read the repository's
`scripts/cat-watch.ps1` and Run section in `README.md` if deployment details have
changed. Resolve paths from this checkout, including when called from a subfolder.

## Start and verify

Run the bundled [ensure-running.ps1](scripts/ensure-running.ps1) through Windows
PowerShell. From the repository root in WSL:

```bash
cat_skill_script=$(wslpath -w "$PWD/.agents/skills/run-cat-watch/scripts/ensure-running.ps1")
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$cat_skill_script"
```

The helper uses the project's existing deployment functions. It reuses a running
container, resumes a stopped one and supplies its camera credentials over stdin,
or calls the project's Start action when no container exists. It waits up to
180 seconds for camera and detector readiness. Run long calls with short tool
yields and provide progress while initialization continues.

If the existing `podman-machine-default` is stopped, start that machine with
Windows `podman.exe machine start podman-machine-default`, then retry once.
Before invoking native executables from a custom PowerShell command, restore
`$env:PATHEXT = [Environment]::GetEnvironmentVariable('PATHEXT','Machine')`.
Locate Podman at `%LOCALAPPDATA%\Programs\Podman\podman.exe`, falling back to
`Get-Command podman.exe`. Use connection `podman-machine-default-root`.

Do not rebuild images, recreate containers, provision a machine, or change host
settings merely to launch the app. If recovery needs those actions, report the
specific failure and follow the user's existing authorization and host permission
policy. Do not print credentials, authenticated RTSP URLs, or recorder process
arguments. A failed startup should lead to targeted diagnostics, not a restart loop.

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

## Investigation descriptions

The approved workflow defers heavy analysis until capture ends. Do not start Cosmos merely to open the app. The Windows analysis controller checks available VRAM once, starts or reuses the pinned project model when admitted, and unloads only services it started. Insufficient VRAM leaves work queued until explicit Retry analysis.

When no investigation is active, camera `preview` with `preparation: true` is the expected ready state; no detector or recording should be running. Require the user to draw or confirm the fresh calibration before a new investigation. Never start an investigation merely to obtain a preview.
