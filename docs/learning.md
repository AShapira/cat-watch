# Learning and continuous care monitoring

Version 0.5.3 extends the existing application. The persistent local agent imports
saved evidence, collects useful new clips, requests local model suggestions,
prepares a short human review queue, trains candidates and evaluates routines.
The agent runs inside cat-watch; an open assistant conversation is not required.

## Daily use

- **Today:** observed care episodes, analysis coverage, summaries and alerts.
  Provisional machine observations are visibly separate from confirmed results.
- **Decisions:** about ten decisions / five minutes daily. Play source context and
  its synchronized native-resolution area crop. Inspect the proposed behavior,
  visible evidence, uncertainty and model provenance. Confirm, correct, mark
  unclear, skip, edit interval boundaries, or undo. Keys 1–6 choose the main
  labels; Enter confirms. Validation/test decisions hide suggestions until saved.
- **Timeline:** inspect prior decisions and their history, browse crops, or select
  evidence for a specific cloud proposal.
- **Learning:** independent episode counts, jobs, training progress, per-class
  evaluation, model rollback and exact cloud approvals.
- **Settings:** learning/training preferences, daily review limit, Telegram settings
  and the existing camera calibration editor. Historical investigations remain
  under Archive.

First import the prepared dataset, or let the mounted dataset import automatically.
Existing group-level reviews are preserved but do not become timed training labels.
Confirm the camera areas and exclusion masks on a fresh frame, then select **Start
continuous monitoring** on Today. A saved old calibration alone cannot start it.
The agent maintains its ongoing capture session until paused or the app stops.
Camera dimensions and confidently detected background movement trigger a pause
and require calibration again. Textureless/occluded scenes may prevent geometric
movement checks; this is not a guarantee of detecting every camera displacement.

## Acquisition and classification

New evidence comes from motion and area visits with five-second context, plus
one deterministic random audit window every fifteen minutes. The agent extracts
up-to-eight-second windows with overlap, preserving native area pixels. It rejects
missing sources and recording gaps rather than stitching across unseen time.
Classification uses a separate crop for each named area, including separate food
and fountain crops even when their context margins overlap. Each crop normally
retains 50% context per side and its own manifest and proposal; area names
are part of the new crop identity. The underlying video, timestamps, source
hashes and episode grouping are shared, so overlapping crops do not become
independent behavior examples. Historical combined clips and their proposals
remain unchanged. Detector context crops can still merge; this classification
policy does not alter monitoring polygons, motion triggers or cat detection.
An explicit classification crop override can narrow one area's input without
changing its motion/presence polygon. Overrides are bound to the exact saved
polygon, so drawing a different area stops that override from applying. The
current fountain override excludes neighboring food bowls: `[1180,400,1360,602]`
in the 2560 × 1440 source, giving a 180 × 202 crop. Food and litter keep their
normal context. Existing wider clips retain their original manifests and labels.
The live legacy worker uses a transactional extraction-queue bridge to apply
this crop without restarting recording. Source code supports the same metadata
directly and restores original polygons from bridged jobs during native handoff.
Prepared clips retain original manifests, source checksums and capture provenance.
Overlapping motion, visit and area exports count as one independent episode.

The local teacher uses an existing Ollama service and `qwen3.5:9b`. It samples
16 native area frames per eight-second window and asks for visible actions,
boundaries, evidence and uncertainty. Each window is checkpointed with model
digest and prompt version. It never equates proximity to a bowl with drinking or
eating. Local service failures leave evidence review available and jobs queued.
The app can request loading the existing model when GPU capacity permits; it
never starts/restarts the Ollama service, pulls its model, or unloads another
application's model. The default endpoint is
`http://host.containers.internal:11434`; only explicitly allowed local endpoints
are accepted. A running local teacher service is therefore a setup prerequisite
for automated suggestions, not for manual review or collection.

For an older recorder that must remain running, the guarded
[`separate-classification-crops.py`](../scripts/separate-classification-crops.py)
utility can install an online extraction-queue bridge. It verifies the active
session and polygon fingerprint, requires training to be disabled, snapshots
the learning database, and atomically splits pending and newly inserted combined
extraction jobs. A job already running retains its input. Food/litter stay in
the original job; the fountain gets a second job with the same time window and
episode identity. This bridge can encode the source twice; the native patch
creates all area manifests from one encoded video. Only startup of the patched
classification worker removes the bridge; opening a store or review view does
not disable it. No recorder restart is required for the bridge.
If a later native deployment is rolled back to the older worker, reapply the
bridge before resuming its classification work; the older media code still
merges food/fountain context by itself.

The offline patch image is built with `Containerfile.separate-crops` over the
verified live image, without changing dependencies. Before applying the online
bridge, run its `--action plan` with the inspected `--session-id`,
`--polygons-sha256` and reviewed `--policy-file`; `--action apply` makes the
transactional change. When the utility is copied into `/tmp` in the existing
container, use `PYTHONPATH=/opt/cat-watch` so its reviewed policy module can
import the installed pixel-crop implementation. Do not replace live databases
with the backup while monitoring is active.

Suggestions, prediction history, human revisions and immutable media manifests
are stored separately in `cat-watch/learning/agent.sqlite3`. Unclear, skipped,
unlabeled and multiple-cat evidence cannot become negative examples. Care labels
are eating, drinking and litter activity; other activity and no-cat provide
explicit alternatives. Fine labels include digging, elimination posture,
covering, sniffing, grooming, moving and stationary. Posture does not prove
successful elimination. This first version does not identify individual cats or
infer illness, intake quantity or events outside the camera view.

## Local training and acceptance gates

Training is fully local with pinned VideoMAE weights. The checkpoint is
`MCG-NJU/videomae-base-finetuned-kinetics`, revision
`488eb9a0565f257b32866000305c8178965eb9f6`; its weight SHA-256 is
`065cfde56f97671da4d196e1a3a6d3cf9304dcad92eb671e3632a6c6cdd04f73`.
Build-time provenance is saved at `/opt/models/videomae/PROVENANCE.json`.
Runtime Hugging Face downloads are disabled. The checkpoint is CC BY-NC 4.0;
see [third-party notices](../THIRD_PARTY_NOTICES.md).

Thirty human-confirmed independent episodes per care behavior opens exploratory
training. This is a data-readiness threshold, not an accuracy claim. Group/day/
source-connected cohorts receive frozen approximately 60/20/20 train/validation/
test partitions. Cross-split discoveries are quarantined. Only independently
reviewed human labels enter validation/test; suggestions alone never train this
first implementation. Dataset IDs, source checksums, label versions and preprocessing
are recorded. Duplicate windows are weighted by episode so long exports do not
dominate optimization.

The worker compares a classifier-head run with a last-transformer-block run,
chooses on validation, selects abstention thresholds on validation, then evaluates
the winner on test. It reports per-class precision, recall, confusion and Wilson
intervals using independent episodes. Each alerting class requires at least 30
positive and 30 negative test episodes, precision ≥95% and recall ≥85%.
Corrections invalidate affected models; label changes during a training run block
its publication. A candidate with insufficient test support stays exploratory;
new confirmed data can trigger another cycle.

A candidate also needs its own fourteen sufficiently observed days to establish
routines, followed by seven days of shadow alert observation, ≥95% analysis
coverage, every shadow alert assessed, and no more than one false alert. A model
cannot inherit another model's observation coverage. Qualified classes alone can
produce behavior alerts after promotion. The prior qualified model remains
available for rollback unless its source labels were invalidated.

Training checks available GPU memory, saves resumable optimizer/model checkpoints,
and yields on detector lag, disabled learning/training, low capacity or a bounded
run duration. Monitoring retains its own inference loop and lock. GPU admission
is cooperative, not an operating-system GPU reservation; actual missed analysis
intervals are reflected in coverage and suppress absence alerts. Default training
admission is 8 GiB free with a 2 GiB reserve. Inference requires at least 3 GiB
free. No other model service is stopped to make room.

Since 0.5.3, training uses the lower of CUDA and host `nvidia-smi` free-memory
readings. If host capacity cannot be verified, heavy work waits. This matters on
Windows/WSL, where CUDA alone can overstate capacity shared with the resident
Qwen service. Automatic training may be enabled while waiting for both human
labels and the 8 GiB admission threshold; enabling it does not force a run.

## Summaries, alerts and evidence retention

Daily summaries are due at 09:00 Asia/Jerusalem and use calendar boundaries,
including daylight-saving changes. A durable notice key prevents repeated daily
creation. Delivery is not attempted while the application is stopped; a current
summary can be created after restart. Old queued deliveries expire after 24 hours.

Routine alerts require ≥95% usable analysis of the relevant interval and no gap
over five minutes. Unclear classifications, multiple cats, stale detection or
missing camera footage cannot establish absence. Absence wording is “not observed
here.” Frequency thresholds and absence windows derive conservatively from the
accepted baseline; insufficient per-behavior observations leave its rule disabled.
Shadow alerts stay on the dashboard for assessment. Acknowledge/snooze actions are
persisted. Delivery timeouts have an unknown outcome and are not blindly retried.

The existing capture quota stays separate (normally 50 GB). Continuous unretained
capture keeps a rolling day subject to that quota; archived protected evidence
keeps the original retention rules. Source files are leased during extraction.
Curated evidence is copied into owned storage, capped at 20 GB by default. The
agent stops additions when full instead of deleting reviewed/training evidence.
Model training pauses beyond 10 GB of saved model artifacts or below 3 GB free.
Curated evidence, snapshots, checkpoints and history are not automatically erased.

## Cloud: disabled unless you approve an exact batch

No online model is needed to run the pipeline. To enable the optional OpenAI
adapter, first configure a current, operator-reviewed `cloud-model-policy.json`
in the Windows data root. A policy maps allowed model IDs to provider `openai`,
`context_tokens`, `input_usd_per_million`, `output_usd_per_million`, `valid_until`
(Unix seconds) and an official pricing `source` URL. No model or price is assumed;
missing or expired policy disables proposals/dispatch. Use a dated policy with a
short validity period and verify model compatibility with Chat Completions image
inputs. The application supports this provider only in the initial adapter.

Each proposal freezes the exact provider/model, purpose, prompt, clip windows,
JPEG images/checksums, rate policy, expiry and cost reservation. Defaults/ceilings:
20 clips, eight seconds each, 16 cropped frames each (320 images total), US$5 for
the entire batch including any possible retry, and 24-hour maximum expiry. No
audio, source video or uncropped room view is eligible. An outbound area crop must cover less than 80% of the camera frame; otherwise cloud export is rejected and Telegram uses text only. Inspect the outgoing
images in Learning, then explicitly approve that fingerprint. Later changes,
expiry, revocation or a missing credential prevent new requests. Revocation
cannot recall a request already in flight. Unknown outcomes keep their full
reservation and are never automatically retried. A new batch needs new approval.

The cost guard conservatively reserves the configured model's full context at
its input rate plus a bounded output allocation before every request. Correct,
current operator-supplied rates/context limits are prerequisites for this monetary
ceiling. API billing cannot be independently capped by this app. No private camera
images have been sent during implementation or testing.

## Windows installation and credentials

Build the new image without modifying the old deployment:

```powershell
.\scripts\build-learning.ps1
.\scripts\test-learning-gpu.ps1
.\scripts\test-learning-gpu.ps1 -FullPipeline
.\scripts\upgrade-learning.ps1 -Action Plan
```

`Plan` only inspects the existing stopped deployment and prints the concrete
upgrade. With explicit workstation-change authorization, run `-Action Apply`.
It requires all relevant writers stopped, copies and checksum-verifies all
application data, preserves the old container under a timestamped name, and
starts the new image. Prepared dataset and optional cloud policy mounts are
read-only. A receipt records the old container/image and backup. No image or
historical container is deleted. The new UI is at http://127.0.0.1:8765/.
Continuous monitoring still requires fresh calibration and the Start action.
The old host analysis controller is not started automatically; use
`cat-watch.ps1 -Action Resume -LegacyAnalysis` only when intentionally continuing
archived deferred investigations.

Optional credentials are entered interactively, never in chat or command arguments:

```powershell
.\scripts\configure-learning-secret.ps1 -Service Telegram
# Only if you want to use the separately approved cloud adapter:
.\scripts\configure-learning-secret.ps1 -Service OpenAI
```

Windows DPAPI protects these credentials for the current user. On application
start they travel through stdin and a UID-restricted Unix socket, then remain in
process memory. They are not put in container configuration, SQLite, URLs in logs,
or frontend responses. No service credential enables sending by itself.
For Telegram, configure the positive numeric ID of your private bot conversation
in Settings, choose cropped evidence, then enable delivery. The initial version
uses an explicitly entered chat ID rather than bot auto-pairing. Send a message
to your bot first so it can address that private conversation. Only text and an
available area JPEG are sent; source room video remains local. Telegram delivery
has been mock-tested, not verified against your real account.

To roll back a failed initial upgrade, stop the new container, rename it to a
unique preserved name, rename the receipt's previous container to `cat-watch`,
and use `cat-watch.ps1 -Action Resume`. Do this only after reviewing the actual
receipt/container names and obtaining workstation-change authorization. Version
0.5 adds a separate learning database and preserves the existing investigation
schema/version, so the old app can read its original history. Keep the verified
snapshot; never overwrite newer evidence as a casual rollback step.

## Validation and remaining live acceptance

See the [dated implementation validation record](learning-validation.md) for observed results and the live-deployment boundary.

Run `.venv/bin/python -m pytest -q` and
`.venv/bin/python tests/browser_learning.py`. Browser checks exercise generated
fixture videos, classification, undo, navigation and mobile layout. Screenshots
are in `.artifacts/learning-ui/`; they contain no private camera footage.
The native GPU scripts use isolated, network-disabled containers, generated
pixels and temporary storage. The full pipeline checks a paused/resumed training
run, both variants, held-out evaluation and FFmpeg extraction. These establish
software and GPU mechanics, not real-cat accuracy.

Real acceptance still needs deployment authorization, fresh camera confirmation,
a running local teacher service, human timed labels, sufficient independent days
and examples, measured shadow performance, and optional Telegram credentials and
an explicitly authorized delivery check. Until those gates pass, the dashboard
must not claim a trained/qualified cat behavior model or live alert delivery.
