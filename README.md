# cat-watch

Local Tapo camera investigations with motion capture, overlapping cat-presence areas, and human review. Source development runs in RHEL/WSL; camera access, model storage, and the live application run through Windows Podman Desktop.

## Start

From native Windows PowerShell, run `scripts/cat-watch.ps1 -Action Build` after source changes, then `scripts/cat-watch.ps1 -Action Start` when no application container exists. The project run helper reuses an existing deployment. The default image is `localhost/cat-watch:0.3.0`.

Open http://127.0.0.1:8765/#setup and draw the three areas on a fresh image. Setup provides preview without recording or heavy analysis. Confirm areas and masks before starting an investigation. Defaults are Broad capture, eight hours, and five-second pre/post-roll.

Use `scripts/review-cat-watch.ps1` to view a stopped deployment's existing data without starting background work. The review-only mode cannot prepare a live camera image.

See [the investigation workflow](docs/investigation.md) and [validation checkpoint](docs/acceptance.md). The application is local-only; camera credentials are transferred via the existing DPAPI-backed helper and never written into calibration snapshots.

## Version compatibility

Version `0.3.0` requires a fresh application database; it does not migrate databases from `0.1.0` or `0.2.0-investigation`. Preserve older databases and media separately with their matching application version before using a fresh data directory.

## License

Original project code and documentation use the [MIT license](LICENSE). Bundled third-party components retain their own terms, including the Ultralytics detector's AGPL-3.0 requirements; see [third-party notices](THIRD_PARTY_NOTICES.md).
