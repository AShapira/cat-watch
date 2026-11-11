# RHEL runtime and automatic quiet mode

The 9 November 2026 migration uses rootless Podman in RHEL10/WSL. RHEL shares
the Windows workstation; this is not a separate physical server. See the
[development journal](development-log.md) for the actual deployment checkpoint
and measurements. The user authorized this migration and keeping training paused.

## Locations and startup

- Active data: `/home/alex/.local/share/cat-watch/data`, on Linux ext4.
- Runtime: `/home/alex/.local/share/cat-watch/runtime`.
- Service: the user's `cat-watch.service`; container: `cat-watch` in RHEL's
  rootless Podman store. `runtime/deployment.json` pins the exact image identity.
- Dashboard: <http://127.0.0.1:8765>.
- Windows rollback data: `C:\Alex\data\tapo-cat-monitor\cat-watch`.
- Windows migration receipts: `C:\Alex\data\tapo-cat-monitor\rhel-migration-20261109`.
- Display signal: `C:\Alex\data\tapo-cat-monitor\display-state\state.json`.

Use `scripts/start-rhel.ps1` from Windows PowerShell to start or reuse the service.
The `CatWatchRHEL` Windows sign-in task invokes an installed copy of this helper.
It decrypts the existing Windows DPAPI credentials and passes JSON through stdin
to `rhel-bootstrap.py`. The only Linux credential copy is mode 0600 in the user's
private `/run/user/<uid>/cat-watch-credentials` tmpfs directory, mounted read-only
in the container. The launcher maps host UID 1001 to packaged UID 1000 explicitly, preserving private file permissions. This permits service recovery without writing credentials to
the image, persistent data, shell arguments or container environment metadata.
The application still uses its existing in-process service credential handling.

```bash
systemctl --user status cat-watch.service
podman stats --no-stream cat-watch
curl --fail http://127.0.0.1:8765/api/health
curl --fail http://127.0.0.1:8765/api/learning/status
```

After WSL alone is terminated/restarted, the tmpfs credential copy is gone.
Run the Windows startup helper again; a Windows sign-in also runs it. The service
does not start recording with invented credentials or a new calibration. Existing
continuous monitoring resumes its saved authorized session; a new session still
requires confirmed camera areas. Do not use the old Windows container or analysis
controller for normal startup.

## Screen rule and resource budgets

`CatWatchDisplayState` is a limited, interactive Windows sign-in task running
`watch-display.ps1`. It subscribes to `GUID_CONSOLE_DISPLAY_STATE` through
`RegisterPowerSettingNotification`, immediately writes changes and refreshes a
heartbeat every five seconds. It does not use keyboard inactivity, a screen saver
or session locking as a substitute for display power.

| Windows display signal | App policy |
| --- | --- |
| On or dimmed | Quiet mode |
| Off, with a fresh heartbeat | Background analysis allowed |
| Unknown, unreadable, malformed or over 20 seconds old | Quiet mode |

Quiet mode continues stream-copy recording, CPU motion analysis and single-job
clip extraction with two FFmpeg decoder/encoder threads and one filter thread.
It stops admitting Qwen labels, behavior-model inference and legacy heavy
analysis. Detector work is paced at a one-frame-per-second wall-time ceiling (two outside
quiet mode), with a bounded queue holding one source segment’s ten samples. Actual detection coverage can be lower because source segments
arrive in batches; raw recording and motion collection are independent. The
health API reports discarded detector samples rather than claiming full coverage.

Cat-watch requests carry a display-management header. The shared-model gateway
rechecks the display after queue admission and closes the particular upstream
request when quiet mode begins, including during image prefill. The worker returns
that job to the queue without consuming a failure attempt. Interactive requests
from other clients are not subject to this cat-watch rule. Qwen stays resident.
GPU cancellation propagation has finite latency; no fixed GPU percentage is
promised by CPU limits.

The app container has a three-logical-CPU quota, lower CPU scheduling weight,
6 GiB RAM with no additional swap allowance, 256 tasks, a 512 MiB temporary
filesystem and lower process/I/O priority. These apply in both modes. Qwen has
its existing shared-service allocation and one generation slot. Linux CPU
weights do not reserve Windows CPU cores. No global WSL CPU/RAM setting was
changed. A 5 GiB free-space floor protects the RHEL filesystem; the existing
50 GB recording and 20 GB learning budgets remain in force.

`CATWATCH_TRAINING_PAUSED=1` independently locks training in both modes. Settings,
the training API, worker and direct training entrypoint enforce it. Screen-off
events never enable training. The dashboard displays quiet mode and disables
training controls while this deployment lock is active.

## Data preservation and rollback

The migration copies a stopped source and verifies every destination SHA-256.
The original Windows deployment, active data and older archives are retained.
The copied databases are checked before startup. Migrated registered media are
protected from automatic retention; unregistered leftovers are preserved outside
the active `media` directory. Future unregistered recording tails are also preserved in `recovery-media` on restart. Existing crop overrides, reviews, suggestions and
calibration are retained. The native crop worker retires its old online queue
bridges at startup, as designed in 0.5.5.

Do not start two recorders or point two writers at one database. To roll back,
stop the RHEL service, preserve any data collected since migration, and reconcile
that data before deliberately resuming the retained Windows deployment. The old
copy is a migration-time snapshot, not an up-to-date replica. The migration
marker makes the ordinary Windows launcher refuse accidental resume.

The RHEL virtual disk was expanded using Windows `Resize-VHD` after an offline
WSL resize encountered a reconnect race; `resize2fs` then grew ext4 online.
The approved capacity is 1,200 GiB (1,288,490,188,800 bytes). The VHD is dynamic;
this does not reserve that much physical Windows disk space. Continue to monitor
both Windows physical free space and Linux free space.

## Validation boundaries

Unit/fixture tests cover fail-quiet behavior, job preservation, training lock,
socket cancellation and unchanged frame selection after sequential decoding.
Native checks cover the packaged image, GPU availability, real display-power
notifications, gateway admission and saved-data integrity. Live recording,
performance samples and limitations belong to the dated journal and receipt.
They do not measure cat-behavior accuracy or establish that every cause of mouse
freezes has been eliminated.

The migration checkpoint also records camera/MP4 timestamp irregularities.
The live `capture_gaps` counter tracks capture failures and analysis-queue loss;
it does not measure migration downtime or every gap between video timestamps.
The journal and evidence receipt separately record those intervals and successful
frame-decoding checks. Do not interpret a zero counter as uninterrupted coverage.

Primary references: [Windows display power notifications](https://learn.microsoft.com/en-us/windows/win32/power/power-setting-guids),
[notification registration](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerpowersettingnotification),
[Podman resource controls](https://docs.podman.io/en/latest/markdown/podman-run.1.html),
[WSL file placement](https://learn.microsoft.com/en-us/windows/wsl/filesystems),
[online VHD expansion](https://learn.microsoft.com/en-us/powershell/module/hyper-v/resize-vhd).
