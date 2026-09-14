# Investigation workflow

Each investigation is independent. Its calibration, image dimensions, motion settings, and detector thresholds are frozen at start. Changing the room or camera means preparing a new investigation.

## Prepare without recording

Start the application using `scripts/cat-watch.ps1 -Action Start`. When no investigation is active, it provides CPU camera previews without writing video or loading a detector. No description model is started during setup. The Windows analysis controller runs alongside the app.

Open Camera & settings. A fresh image is frozen while you draw. Choose each of Eating pad, Water fountain and Litter box and outline the area with at least three clicks. Overlapping polygons are supported. Review exclusion masks on the same image. Save areas & confirm masks. Changing saved settings invalidates confirmation. Refresh camera image before each new investigation.

## Capture

Choose Broad (movement anywhere outside exclusion masks) or Focused (movement within any monitored area plus its buffer, default 20% of bounding-box width/height per side). Buffers are clipped to the frame and exclusion masks are subtracted afterward. Dashed setup outlines show the resulting motion boundary; solid polygons alone define cat presence. Buffer percentages (0–100%) are saved with the investigation. Both retain original full-frame video. Motion need not contain a recognized cat. Overlapping triggers produce one motion group.

Duration is 15 minutes to 24 hours in 15-minute steps; the default is 8 hours. Clips have five seconds of pre-roll and five seconds of post-roll. The deadline survives restarts. Capture stops after the deadline and five-second post-roll; the final completed segment is ingested before processing the queue.

Source MP4s remain segmented at camera keyframes. The review player limits playback to the selected group's padded interval. Padding can be partial at stream starts, interruptions, or missing source segments.

## Presence and human behavior

Cat boxes match every area meeting its overlap threshold (intersection divided by box area; default 20%). Per-area presence counts can overlap and must not be summed as unique visits. Motion groups are unique.

Automatic area presence does not establish eating or drinking. Group review records cat presence separately from observed eating, drinking, litter activity, other activity, or unclear. Multiple activities are allowed; unclear is exclusive. Group labels do not measure behavior duration. Changes are versioned and stale edits are rejected.

Historical group overlays and filters use that investigation's snapshot. Adjusting the next calibration never changes older sessions. Review detector confidence can be changed locally without changing saved calibration.

## Native-resolution area evidence

The live detector for new investigations is YOLO11m/640 at two samples per second. It receives crops cut from the original decoded camera frame before model resizing. Analysis crops have configurable context (default 50% per side, independent of the trigger buffer). Overlapping food/fountain crops merge; litter-box context stays separate. Crop detections are mapped to full-frame coordinates and duplicate boxes are suppressed before independent area assignment.

The group player offers detailed source views, native-pixel display, fit/2×/4× zoom, and PNG downloads of the current frame without overlays. Enlarging the display adds no source detail. The investigation filters include buffered-area motion, cat candidates, sustained sampled area presence (at least two seconds without a gap over 1.5 seconds), brief presence, and uncertain evidence. These do not establish eating, drinking, litter activity or behavior duration. Sampling skips and recording gaps are shown separately.

## Deferred heavy analysis

New investigations use the shared `qwen3.5:9b` model in Ollama. The app reaches it at `http://host.containers.internal:11434`; the Windows controller uses `http://127.0.0.1:11434`. It checks the loaded model after capture/post-roll drain and live-detector release, issuing one empty load request only if necessary. The service is never owned, restarted or unloaded by cat-watch. Its current two-request parallelism is shared with other applications; excess requests queue and may time out or receive an overload response. Cat-watch sends only one request at a time.

Each request uses an eight-second sequence of at most 16 timestamped native-resolution context images at two FPS, with thinking disabled, a 16K context and at most 512 output tokens. Each crop region is described separately. Results record provider, exact loaded model digest, crop dimensions, source timestamps and sampling settings; completed windows are checkpointed. Suggestions remain separate from human review.

The request timeout is configurable in setup (default 180 seconds). HTTP 429/503 responses retry at most three times after 30, 120 and 300 seconds. The retry schedule survives restarts, but application restart requires explicit Retry analysis. Timeouts and exhausted retries leave jobs queued with a visible explanation. No indefinite retry or shared-server restart occurs.

The Windows controller continues to admit detector comparisons separately with 4 GiB plus 1 GiB headroom; stages are sequential. Comparison-memory rejection does not block a loaded Qwen service. Historical Cosmos investigations retain their pinned model path and jobs. Job claims and controller permits are scoped to the selected investigation; new runs never automatically claim historical jobs.

New investigation settings add `motion_buffer`, `crop_context`, `detector_model`, `description_provider`, `description_model`, `description_url` and `description_timeout`. `POST /api/investigation/preview-regions` returns the same buffered mask contours used by capture without saving configuration. `GET /api/investigation/groups` accepts `presence=all|buffered_motion|cat|sustained|brief|uncertain` and returns saved detector identifiers. Group detail includes its saved crop context. No processing database migration is needed.

## Historical highlights

The original investigations from before the 11 September reset were retired. The new investigation 1 recorded on 12 September remains in the application and is preserved. Their ten selected clips and written camera-incident summary reside outside application storage in `C:\Alex\data\tapo-cat-monitor\cat-watch-highlights-20260911`. That archive has no processing database or analysis queue and is never imported automatically.
