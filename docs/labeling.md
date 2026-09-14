# Local activity labeling

Version 0.5 replaces the human annotation forms with Label Studio Community
Edition 1.23.0. Cat-watch continues to record, detect cats, inspect source footage,
show area overlaps and run shared local Qwen descriptions. Label Studio owns human
activity intervals. No cloud inference, model download or training is added.

## Deploy on Windows Podman

Deployment changes the running application and must be scheduled after capture
and analysis finish. These commands are implementation instructions, not evidence
that the production service has already been replaced.

From a native PowerShell session in this checkout:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./scripts/label-studio.ps1 -Action Configure
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./scripts/label-studio.ps1 -Action Pull
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./scripts/label-studio.ps1 -Action Start
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./scripts/label-studio.ps1 -Action Credentials
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./scripts/cat-watch.ps1 -Action Build
```

The execution-policy flag applies only to that child PowerShell process and permits
running this checkout from a WSL UNC path; it does not change Windows policy.

Configure creates local-only credentials restricted to the Windows account and
SYSTEM. Start creates a local personal access token using the bootstrap account;
the bridge refreshes that token to obtain short-lived bearer tokens. Credentials
opens the local username/password file in Notepad; it does not print secrets into
shell output. The bootstrap legacy token remains enabled for recovery on this
loopback-only instance. `UsePAT` securely accepts a replacement personal token.
No external account registration is involved.

The Label Studio image is pinned by digest in `scripts/label-studio.lock.json`.
It runs with two CPU cores, a 4 GB memory limit, no GPU device, no capabilities,
telemetry/version checks disabled, and binds only `127.0.0.1:8767` on the existing
Windows Podman machine. It has read-only access to the dataset. Cat-watch owns
writes to the dataset. The existing dashboard remains on port 8765.

After the approved shutdown/backup of the old cat-watch service, start the new
image using `cat-watch.ps1 -Action Start`, or use `review-cat-watch.ps1` for saved
data without camera/model workers. Both helpers add labeling mounts when
configuration exists. Review-only mode permits annotation synchronization and
queued dataset exports, and leaves recorder retention disabled.

Do not run an older image against the upgraded database. Version 0.5 upgrades
SQLite user_version 4 to 5 transactionally. Existing legacy label tables remain
inert history; they are not imported into Label Studio or the activity dataset.
The old HTTP annotation writes return Gone (or Forbidden in review-only mode).

## Storage and setup verification

Default sibling directories under `C:\Alex\data\tapo-cat-monitor`:

| Directory | Owner and purpose |
| --- | --- |
| `cat-watch` | Existing recorder DB/media; existing 50 GB retention cap |
| `cat-watch-label-studio\state` | Label Studio database and application state |
| `cat-watch-label-studio\private` | Restricted local credentials/configuration |
| `cat-watch-dataset` | Immutable sources, review clips and export snapshots |

The corpus has an independent 100,000,000,000-byte cap and a 5,000,000,000-byte
free-space reserve. Source copies, derivatives, temporary files and snapshots all
count. It never automatically deletes existing dataset files. Quota exhaustion
pauses exports, records the reason and leaves recording operational. Label Studio
state and recorder storage remain separate from that cap.

Open **Activity labeling** in cat-watch. Confirm that the local project link is
available, sync succeeds, and quota usage is sensible. The bridge registers the
project's clip directory for authenticated media serving. Do not use Label
Studio's storage Sync button: task creation belongs to the bridge. The storage
filter intentionally matches no files, preventing accidental duplicate imports.

All motion groups from newly started investigations are queued once capture,
post-roll and processing queues have drained, including groups with no detected
cat. Use the investigation selector and export button for historical footage.
Missing source files become visible `source_missing` jobs. Automatic recorder
retention may still expire historical footage before export; the permanent corpus
protects footage only after a verified copy succeeds. Choose **Retry sync and
exports** after fixing a stopped service, missing credentials or quota issue.

`CATWATCH_LABELING_CONFIG` points to a JSON file. Native Python development can
use the same integration with absolute local paths. Keys:

```json
{
  "dataset_root": "/dataset",
  "url": "http://127.0.0.1:8767",
  "token_file": "/labeling-private/pat",
  "token_type": "pat",
  "webhook_secret_file": "/labeling-private/webhook",
  "cap_bytes": 100000000000,
  "disk_floor_bytes": 5000000000,
  "ffmpeg": "ffmpeg"
}
```

Optional `project_id` selects an existing compatible project. For isolated test
ports or different mount paths, `callback_url` controls the webhook destination,
and `label_studio_dataset_root` names the dataset mount as seen by Label Studio.
Both applications normally mount the corpus at `/dataset`. Credentials must stay
outside Git. Missing configuration disables the bridge.

## Annotation policy

The packaged [labeling guide](../catwatch/labeling/guide.md) appears in the project.
The schema and taxonomy are versioned together; do not edit project labels ad hoc.
A mismatched configuration stops synchronization until resolved.

- Mark eating, drinking, litter digging, elimination posture, covering, inspecting,
  grooming, moving, stationary, other activity, unclear or explicit no-cat time.
- Mark subject assessment, full/partial coverage, quality and truncated boundaries.
- Fully labeled means every frame is covered. Partial labels contribute only
  their explicit spans; skipped, empty and unmarked time are never negatives.
- Multiple cats remain reviewable but are excluded from initial supervised data.
- Litter posture is visual evidence, not proof of elimination or a medical claim.
- Qwen text appears as model notes. It cannot create frame-accurate predictions.
  `catwatch.labeling.predictions.prediction` is the adapter for future structured
  zero-based frame predictions; publish its output to Label Studio's predictions
  API, never to its annotations API. Suggestions become truth only after review.

Clip exports preserve original files by SHA-256 and produce browser H.264/yuv420p
video at native dimensions. They use constant cadence at the source's measured
average FPS, matching the existing segment-start/frame-index timing convention.
They split at gaps, cadence/resolution changes and 120 seconds; no missing time
is fabricated. Capture timestamps remain estimates. The manifest explicitly maps
each derivative frame run to source hash/index and its estimated capture anchor.

Label Studio 1.23 uses one-based inclusive frame ranges: `[1,1]` is the first
frame. The corpus normalizes that to zero-based half-open `[0,1)`. Frame timing and
boundary uncertainty are preserved rather than silently rounded to seconds.

## Sync, reports and snapshots

Annotation webhooks require a dedicated secret. They enqueue work; they do not
apply their possibly stale payload directly. The worker fetches current task
state and reconciles the complete project on startup, after webhooks/exports,
and every five minutes. Failures retry after 30, 120 and then 300 seconds. Queues,
remote IDs, annotation revisions and deletions survive restarts. Lost create
responses are recovered by stable task keys before another POST.

One completed annotation per clip is expected in this single-reviewer workflow.
Multiple completions, incompatible overlapping activities, out-of-range labels
and incomplete declared coverage require correction. Raw revisions remain in the
local audit history. Deleting annotations removes them from current reports;
deleting a task suppresses automatic recreation while preserving its media.
To re-review a deliberately deleted task, create a replacement from its immutable
manifest through an explicit maintenance operation; retry does not undo deletion.

Activity totals union overlapping evidence and exclude time where clips disagree.
Reports distinguish reviewed, unclear and conflicting time. They are not estimates
of all-day intake or litter use. The existing visit report now presents automatic
area presence without legacy human behavior counts.

Create a dataset snapshot in the labeling tab. It synchronizes first and verifies
all selected clips and original-source hashes, then atomically publishes:

| File | Contents |
| --- | --- |
| `manifest.json` | Snapshot ID, taxonomy version, file hashes, source references |
| `clips.jsonl` | Immutable clip metadata, calibration, FPS and source frame maps |
| `intervals.jsonl` | Normalized intervals, annotator provenance, eligibility, grouping |
| `annotations.jsonl` | Raw annotation revision history |
| `taxonomy.json`, `guide.md` | Exact interpretation used by the snapshot |

These are **manifests referencing the permanent corpus**, not standalone video
archives. Keep the sibling `sources/` and `clips/` directories with snapshots when
backing up or moving a dataset. No-cat spans are explicit negatives. Unclear spans
are retained for uncertainty evaluation and excluded from initial supervised
classification. Conflicts and multiple-cat clips are also excluded. Existing
snapshots are immutable even if labels are later changed or deleted.

`group_key` keeps whole investigations together for future train/validation/test
splits. Never randomly split neighboring frames or overlapping clips. Before
training, freeze a held-out set of whole investigations and check balance across
days, lighting and behavior. This release builds the dataset; it does not train
or automatically deploy a model.

## Backup and recovery

After an approved stop of both applications, copy recorder DB/media, Label Studio
state/private credentials and the entire corpus together. Preserve the digest
lock and application revision. Verify hashes before considering the backup
complete. Restore all directories as a set into separate storage for a rehearsal;
never test a restore over production. Each corpus marker must match the recorder
DB's dataset ID. Restart the same versions and reconcile before exporting.

For rollback, use the pre-upgrade recorder backup with its previous application
image. Preserve the new Label Studio state/corpus separately. Never downgrade the
live schema or delete new media to make an older binary start.

## Validation

Run `python -m pytest -q`. Real encoding tests require `ffmpeg` on PATH or
`CATWATCH_TEST_FFMPEG`. They cover interval conventions, explicit coverage,
conflicts, deleted/lost tasks, codec output, gaps, deduplication, interrupted
exports, quotas, webhook authentication, snapshot recovery and tampering.
See [the labeling acceptance record](labeling-acceptance.md) for integration
checks and remaining deployment validation.

Upstream references: [video controls](https://labelstud.io/tags/video),
[timeline labels](https://labelstud.io/tags/timelinelabels),
[webhooks](https://labelstud.io/guide/webhooks.html),
[personal tokens](https://labelstud.io/guide/access_tokens), and
[HyperText links](https://labelstud.io/tags/hypertext).
