# Investigation workflow

Each investigation is independent. Its calibration, image dimensions, motion settings, and detector thresholds are frozen at start. Changing the room or camera means preparing a new investigation.

## Prepare without recording

Start the application using `scripts/cat-watch.ps1 -Action Start`. When no investigation is active, it provides CPU camera previews without writing video or loading a detector. Cosmos is not started during setup. The Windows analysis controller runs alongside the app.

Open Camera & settings. A fresh image is frozen while you draw. Choose each of Eating pad, Water fountain and Litter box and outline the area with at least three clicks. Overlapping polygons are supported. Review exclusion masks on the same image. Save areas & confirm masks. Changing saved settings invalidates confirmation. Refresh camera image before each new investigation.

## Capture

Choose Broad (movement anywhere outside exclusion masks) or Focused (movement within any monitored area). Both retain original full-frame video. Motion need not contain a recognized cat. Overlapping triggers produce one motion group.

Duration is 15 minutes to 24 hours in 15-minute steps; the default is 8 hours. Clips have five seconds of pre-roll and five seconds of post-roll. The deadline survives restarts. Capture stops after the deadline and five-second post-roll; the final completed segment is ingested before processing the queue.

Source MP4s remain segmented at camera keyframes. The review player limits playback to the selected group's padded interval. Padding can be partial at stream starts, interruptions, or missing source segments.

## Presence and human behavior

Cat boxes match every area meeting its overlap threshold (intersection divided by box area; default 20%). Per-area presence counts can overlap and must not be summed as unique visits. Motion groups are unique.

Automatic area presence does not establish eating or drinking. Group review records cat presence separately from observed eating, drinking, litter activity, other activity, or unclear. Multiple activities are allowed; unclear is exclusive. Group labels do not measure behavior duration. Changes are versioned and stale edits are rejected.

Historical group overlays and filters use that investigation's snapshot. Adjusting the next calibration never changes older sessions. Review detector confidence can be changed locally without changing saved calibration.

## Deferred heavy analysis

The Windows `analysis-controller.ps1` checks GPU availability once after capture queues drain and live detection releases VRAM. It reuses the exact responding project Cosmos service, or starts the pinned model only if free memory covers its configured reservation plus 1 GiB. Comparison admission requires the configured comparison allowance (initially 4 GiB) plus 1 GiB. Stages run sequentially.

Failed admission or inference preserves queued jobs and displays the reason. Retry analysis explicitly to authorize another check. A blocked comparison does not prevent descriptions from an already-ready Cosmos service. Only a Cosmos service started by this controller is stopped after its work, with persistent identity checks. Existing services remain untouched.

The controller requires native Windows Podman and the existing NVIDIA-enabled Podman machine. No engine socket is mounted into the application. Model weights remain pinned in `cosmos.lock.json`.

## Historical highlights

Investigations 1 and 2 have been retired. Their ten selected clips and written camera-incident summary reside outside application storage in `C:\Alex\data\tapo-cat-monitor\cat-watch-highlights-20260911`. That archive has no processing database or analysis queue and is never imported automatically.
