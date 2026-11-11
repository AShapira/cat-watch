# cat-watch

Local cat care monitoring with agent-prepared behavior decisions, traceable learning, local VideoMAE training, and conservative summaries and alerts. Historical Tapo camera investigations remain available. Source and the application run in RHEL/WSL with rootless Podman and Linux data storage. Windows supplies protected credentials and display-power notifications for automatic quiet mode.

## Learning agent

See [the learning workflow](docs/learning.md) and [RHEL runtime and rollback guide](docs/rhel-runtime.md). The Today, Decisions, Timeline, Learning and Settings screens keep daily review short. Cloud requests require approval of a bounded batch. Training is currently paused in both performance modes.

## Development journal

The [development journal](docs/development-log.md) records the design decisions, experiments, failures, fixes, validation and deployment outcomes in human-readable form for the planned article. It distinguishes reconstructed history from live observations and is maintained as part of ongoing project work.

The [shared local Qwen service guide](docs/shared-local-llm.md) gives the agent API,
startup behavior, pinned model identity, GPU limits and automatic training admission rules.

## Start

From native Windows PowerShell, run `scripts/start-rhel.ps1`. The project run helper reuses the RHEL deployment. The 0.6.1 runtime uses automatic quiet mode while the screen is on and allows heavier background analysis when it is off. The Windows Podman container and original data are retained for rollback.

Open http://127.0.0.1:8765/#setup and draw the three areas on a fresh image. Setup provides preview without recording or heavy analysis. Confirm areas and masks before starting an investigation. Defaults are Focused capture with a 20% buffer per side, eight hours, and five-second pre/post-roll. Native-resolution area crops feed YOLO11m; shared Qwen3.5-9B descriptions run after capture.

Review is available in the running dashboard. The old Windows review helper targets the migration-time rollback copy; it is not the active collection.

See [the investigation workflow](docs/investigation.md) and [validation checkpoint](docs/acceptance.md). The application is local-only; camera credentials are transferred via the existing DPAPI-backed helper and never written into calibration snapshots.

For the current hardware-specific teacher recommendation and proposed comparison, see [the 2 November model review](docs/model-review-2026-11-02.md).

## Version compatibility

Version `0.5.2` bounds diagnostic cleanup so protected investigation history cannot trigger a full archive scan on every detection. Storage accounting runs outside the database lock and avoids redundant file scans. It uses the same data formats as 0.5.0.

Version `0.5.0` preserves the investigation archive and adds a separate learning database under the application data directory. Existing whole-group reviews do not become timed behavior labels. A running Ollama service with the configured local vision model is needed for automatic suggestions; no service is restarted or model pulled automatically.

Version `0.4.0` preserves completed `0.3.0` investigations and their original Cosmos jobs; new investigations use Qwen settings frozen at start. The earlier version `0.3.0` requires a fresh application database; it does not migrate databases from `0.1.0` or `0.2.0-investigation`. Preserve older databases and media separately with their matching application version before using a fresh data directory.

## License

Original project code and documentation use the [MIT license](LICENSE). Bundled third-party components retain their own terms, including the Ultralytics detector's AGPL-3.0 requirements; see [third-party notices](THIRD_PARTY_NOTICES.md).
