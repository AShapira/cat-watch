# Cat-watch development journal

This journal records how the application was developed, what was learned along
the way, and what the evidence supports. It is source material for an article,
not a claim that every planned feature is already operating successfully.

The user requested this journal on **2 November 2026**, together with approval to
apply the Windows upgrade. The earlier sections below reconstruct the development
story from the conversation, repository history, implementation, and dated
validation records. They were not written contemporaneously with every event.
Entries from the upgrade onward are recorded as the work happens. Operational
timestamps use UTC; the application's daily routine uses **Asia/Jerusalem**.

## Current status

**Stopped at the user's request — 2026-11-11, 04:22:54 UTC / 06:22:54 Asia/Jerusalem.**
Cat-watch, its temporary review dashboard and display/startup helpers are stopped.
Port 8765 has no listener. The user will restore the local camera account before
resuming: the saved Windows credential was missing, and the camera rejected both
securely entered replacements. The unverified encrypted credential is retained
separately from the active startup filename, and its temporary Linux copy was
removed. Saved data remain retained; both databases passed quick checks before
the attempted launch. Training remained paused throughout. See section 30 and
the [launch/stop evidence](development-evidence/2026-11-11-launch.json).

**Sol crop campaign completed — 2026-11-09, 04:50 UTC / 06:50 Asia/Jerusalem.**
All **18** authorized Sol classifications returned usable structured proposals:
ten fountain, four food and four litter clips. Fountain activity was unclear in
eight clips, with two empty-fountain controls; no selected clip received a
drinking label. Food interaction was also unconfirmed, and litter views showed
stationary/moving/unclear activity. These are model proposals, not accuracy results.
Estimated inference cost was **$0.204778**; conservative exposure including the
token-count allowance was **$0.695650** against the new $20 ceiling. No retry,
unknown request, training job or human review was submitted. The one-off schedule
was deleted after completion. At the final 04:47:55 UTC health check, monitoring
was on, camera connected, detector ready and training paused/deployment-locked.
See the [private report](../outputs/cropped-care-sol-20261109/report.md),
[video gallery](../outputs/cropped-care-sol-20261109/report.html) and
[evidence receipt](development-evidence/2026-11-09-cropped-sol-results.json).

**RHEL migration completed — 2026-11-09, 04:49 UTC / 06:49 Asia/Jerusalem.**
The copied collection passed full database integrity checks and per-file SHA-256
verification: **17,533 files / 8,785,600,698 bytes**, including 16,678 recording
segments, 2,079 clips and 1,268 saved suggestions at migration. The Windows
originals remain retained. Migrated recording segments are protected from
retention; three unregistered leftovers are preserved separately.

The RHEL recorder first started at **04:34:00 UTC**; the final **0.6.1** image
started at **04:39:37 UTC** and is camera/detector ready with no service restarts.
Training remains disabled and deployment-locked. The display watcher has reported
both actual on and off states. Screen-off permits labels; on, dimmed, missing or
stale signals enable quiet mode. A native Windows dashboard check passed with
training controls disabled and no JavaScript errors. The migration's final source
suite passed **179 tests**. The container has a three-CPU quota and 6 GiB memory
limit; RHEL's filesystem now spans the approved **1,200 GiB** virtual disk.
The detector pacing correction is deployed. The migration and corrective restart
had recording downtime, and packet/segment timestamps remain irregular; section
28 separates these observations from the runtime's zero new capture-gap counter.
Normal-work mouse responsiveness has not been measured with the user present.
Use [the RHEL runtime guide](rhel-runtime.md); the old Windows container is a
rollback deployment and must not be resumed by campaign/startup helpers.

### Previous checkpoint — before RHEL migration (historical)

**Last updated:** 2026-11-09, 03:36 UTC / 05:36 Asia/Jerusalem.

- **A new Sol cropped-activity campaign is authorized for up to US$20 and
  scheduled once for 9 November, 04:36 UTC / 06:36 Asia/Jerusalem.** The user
  requested a one-hour delay to restart the workstation. Preparation and paid
  requests are deferred until that time. Fountain activity is the priority;
  eating and litter-box clips are also in scope. Training must remain paused.
  The [restart handoff](sol-cropped-campaign-2026-11-09.md) and
  [authorization receipt](development-evidence/2026-11-09-sol-campaign-authorization.json)
  preserve the task, crop boundaries, budget and required report. No batch has
  run yet; live monitoring state must be rechecked after the user's restart.

- **The fountain classification crop is now tightened to 180 × 202 pixels**, at
  `[1180,400,1360,602]` in the native 2560 × 1440 frame. It retains the fountain
  and white backing while excluding both neighboring food bowls. Food and litter
  crops keep their prior context; the user's monitoring polygons are unchanged.
- **Three post-change clips have completed local classifications: all `no_cat`.**
  These verify the new crop and local pipeline, not recognition of a positive
  drinking event. The model still flagged `poor_lighting`. Monitoring remained
  on and training paused; the 18:29:38 UTC check found the same recorder and
  13 capture gaps. All 87 temporarily deferred labeling jobs were restored.
- Forty focused source tests and an isolated native fixture passed. Offline
  patch image **0.5.5** includes the crop override and native handoff; the running
  recorder remains on **0.5.3** with the persistent online queue bridges.
  [Tight-crop evidence](development-evidence/2026-11-08-tight-fountain-crop.json)
  records exact bounds, source checks, new clips and recording continuity.

- At the earlier **18:20 UTC** checkpoint, three wider fountain previews had completed classifications:
  two eating suggestions and one no-cat suggestion. They are available as
  cropped videos for the user's inspection. None establishes a positive drinking
  example or improved accuracy from the white backing. No human labels were saved.
- The bounded preview operation restored all 138 temporarily deferred labeling
  jobs. At **18:20:08 UTC**, the camera was connected, detector ready, monitoring
  on and training paused, with the same recorder container and 13 capture gaps.
  [Preview evidence](development-evidence/2026-11-08-fountain-previews.json)
  records exact clip identities, model provenance, crop checks and review exposure.

- **Food and fountain classification are now separated for pending and new
  extraction jobs**, using the user's saved smaller polygons. Food retains its
  **294 × 293** native crop. The initial separated fountain crop was **338 × 277**;
  the tighter override above supersedes that width for new extraction. Each area
  has its own input and proposal.
- **Monitoring remains on without a recorder restart. Training remains paused.**
  A transactional queue bridge was applied at **18:01:27 UTC** in the existing
  container. It split 56 queued extraction jobs and preserves historical clips
  and human-review fields. The one extraction already running kept its input.
- The direct source implementation creates separate manifests from one encoded
  video. Its former offline 0.5.4 patch is superseded by 0.5.5, but the running
  0.5.3 recorder was deliberately retained. Only startup of the patched worker
  retires the online bridge; a normal store inspection does not remove it.
- The existing detector crop logic, monitoring areas, motion sensitivity,
  archived collection, training pause and cloud permissions are unchanged.
  The earlier day's 13 capture gaps were already present before this change;
  they must not be attributed to this deployment or described as zero.
- At **18:09:20 UTC**, live extraction had produced **56 separate food crops
  and 10 separate fountain crops** after application. Two frames from each
  selected real crop decoded at the expected native dimensions. New proposals
  remained queued at that checkpoint; this verifies crop preparation, not
  recognition accuracy. Training remained false and `pause_training=true`.
- [Separate-crop evidence](development-evidence/2026-11-08-separate-classification-crops.json)
  records the source tests, native fixture, live queue policy and recording
  continuity. See the entry below for bounded live crop checks and limitations.

### Earlier checkpoint — 8 November 2026, fresh collection (historical)

The checkpoint below preceded the user's request to separate food and fountain
classification. Its shared-crop description is superseded by the policy above.

**Last updated:** 2026-11-08, 04:28 UTC / 06:28 Asia/Jerusalem.

- **A fresh collection is monitoring continuously**, following the user's
  explicit request after saving smaller areas. New investigation 1 began at
  **04:23:34 UTC**. Native checks report camera connected, detector ready and
  recording reserve available. Local Qwen classification is enabled;
  **training remains disabled with `pause_training=true`**.
- **The prior app data is archived outside active storage:** 32,678 files,
  **35,235,051,478 bytes** across the application and prepared dataset. The
  same-volume moves preserved both inventories. Old counts include 14,442 clips,
  11,581 suggestions and 11 timed human reviews. The fresh app started with
  zero investigations, clips, suggestions and reviews; the legacy dataset is
  not mounted, so it cannot automatically repopulate the collection.
- The user's exact confirmed polygons and calibration image were carried over.
  The fountain polygon is approximately **47% smaller by area** than the previous
  saved version. The white paper behind the fountain was visually confirmed.
  Improved classification remains a hypothesis, pending new reviewed examples.
- Motion is measured independently in each area with a 20% buffer, a 0.05%
  changed-area threshold and 0.5-second confirmation at five samples per second.
  Collection does not require a positive cat detection. Native video records
  continuously; motion and visits supply classification windows with context.
- A **04:26:10 UTC** check found 30 new segments, all files present, with maximum
  internal timestamp gap **0.033334 seconds**. The latest video metadata probe
  passed at 2560 × 1440. Capture gaps were zero at the health checkpoints;
  detector sampling did discard queued frames, so complete detector coverage
  is not claimed. No new classification result had been produced at that check.
- Both archived original databases passed full read-only integrity checks.
  The last registered old segment's metadata probe passed, but the newest
  unregistered file from the earlier forced shutdown failed its probe and was
  preserved unchanged. This limitation belongs to the old archive.
- Native Windows Edge verified continuous monitoring, automatic labeling on,
  training off, zero decisions, mobile layout and no JavaScript errors.
  No review decisions, training jobs or new cloud batches were submitted.
  [Fresh-collection evidence](development-evidence/2026-11-08-fresh-collection.json)
  records the archive, calibration, recording and UI boundaries.

### Earlier checkpoint — 8 November 2026, area setup (historical)

The setup-only checkpoint below preceded the user's new calibration and explicit
request to archive the old collection and resume monitoring.

**Last updated:** 2026-11-08, 04:04 UTC / 06:04 Asia/Jerusalem.

- **The app is available for camera-area editing.** At the user's request, the
  existing Windows Podman machine and retained `cat-watch` container were
  resumed. A fresh 2560 × 1440 calibration image was prepared, and the Settings
  browser tab was requested. The browser tool returned `queued`; visibility and
  user interaction were not independently verified.
- **Recording, automatic labeling and training remain paused.** Live health
  reported camera `preview`, preparation enabled, detector stopped, no loaded
  live model, no capture in progress and zero analyzed frames. Saved learning
  settings remain `enabled=false`, `continuous=false`, `training=false`; Telegram
  remains disabled. The separate review companion was not resumed, and no
  legacy analysis controller was launched.
- The user reports adding white paper behind the fountain and suspects that
  the dark background and overly broad area contribute to missed drinking.
  These are hypotheses to evaluate with new evidence. The agent has not changed
  any polygons or confirmed calibration on the user's behalf.
- The stopped archive database and rollback journal were preserved before
  startup. SQLite recovery on a separate copy succeeded and its full
  `PRAGMA integrity_check` returned `ok`. The live application then opened the
  original database normally. The original has not had a separate full integrity
  check, and the final recording segment remains unvalidated before capture
  resumes. Saved learning counts remain 14,442 clips, 11,581 suggestions and
  11 reviewed clips.
- [Area-setup evidence](development-evidence/2026-11-08-area-setup.json) records
  the preview and recovery boundaries. Next: the user draws and saves the areas;
  recording needs a separate deliberate start after calibration confirmation.

### Earlier checkpoint — 8 November 2026, before area setup (historical)

The stop and CPU investigation below remain the record of the earlier pause.
The later setup-only reopening above supersedes their stopped-container status.

**Last updated:** 2026-11-08, 03:56 UTC / 05:56 Asia/Jerusalem.

- **Project activity is paused at the user's request for redesign.** Recording,
  detection, automatic labeling, training, review serving and shortlist refresh
  are stopped. Both active project containers are retained in the exited state.
- Saved learning settings are `enabled=false`, `continuous=false`,
  `training=false`, with `pause_training=true`. All three existing cat-watch
  automations were already paused. Native Windows checks found no remaining
  project containers, workers, listeners or scheduled tasks.
- Existing evidence and review results remain on disk: the learning database
  reports **14,442 clips, 11,581 saved suggestions and 11 reviewed clips**.
  These are inventory counts, not behavior-accuracy measurements.
- **The recorder did not finish graceful shutdown within 60 seconds and exited
  137.** The archive database retains a 12,824-byte rollback journal; read-only
  access reports that a write is required. The database and journal were preserved
  untouched. Archive recovery/integrity and the last recording segment need
  checking before the recorder resumes; this task does not establish data integrity.
- **RHEL10 was restarted at the user's request at 03:47 UTC.** Cockpit,
  Kubernetes and shared Qwen were verified active afterward; cat-watch remained
  stopped in the separate Podman machine. The persistent 45% Task Manager CPU
  display cleared when the user reopened Task Manager, agreeing with independent
  lower CPU measurements. See the restart/diagnostic entry below.
- The shared Qwen service remains available to other local projects. The pause
  changed no model artifacts, human labels, cloud permissions or external delivery.
- [Shutdown and verification evidence](development-evidence/2026-11-08-redesign-pause.json)
  records the live stop and its limitations. No restart is scheduled by this work.

### Previous live checkpoint — 4 November 2026 (historical)

The following checkpoint is retained as the earlier observation; its statements
about continuing recording and labeling were superseded by the pause above.

**Last updated:** 2026-11-04, 11:06 UTC / 13:06 Asia/Jerusalem.
These are bounded live observations, not a long-term reliability or accuracy claim.

- **The approved fountain batch is complete: 100 processed, 97 usable Sol/medium
  proposals and three validation failures.** All 3,400 approved crops were used
  within fingerprint `900e180e988c`; no retries, extra batches or unresolved
  requests. The fountain queue at
  `http://localhost:8767/?campaign=2026-11-04-fountain-100` shows all 100 clips.
  The earlier care batch's 100 valid proposals remain in the batch selector.
- **No drinking was proposed in the fountain batch.** Ninety-six of 97 usable
  answers include unclear intervals. On the same 84 clips with saved local
  proposals, Qwen proposed eating in 78 and Sol in none. These are unconfirmed
  model disagreements under different sampling conditions, not measured accuracy
  or proof that the fountain is unused. Human review must establish visibility.
- **Training remains suspended. Recording and local labeling continue.**
  At 11:03:34 UTC: camera connected, detector ready, 219,228 analyzed frames,
  6,946 clips, 5,536 saved local suggestions and ten human reviews. No clip in
  this new batch has been human-confirmed. No dataset/model artifact was created.
  All 217 recording segments overlapping dispatch existed; maximum measured
  internal timestamp gap was 0.329 seconds. This is bounded continuity evidence.
- **Qwen3.5-9B Q4_K_M remains fully GPU resident**, retaining its pinned digest,
  16K context and 5,763,005,151 bytes reported entirely in GPU memory. The recorder
  retains its 0.5.3 image and 2 November start identity.
- **Fountain-batch estimated inference: $1.617770.** Across all three approved
  batches, estimated inference totals **$5.042941**. Conservative accounted
  exposure, including counting allowances, is **$17.764040**, leaving
  **$2.235960** within the original $20 ceiling. All 100 new entries were checked
  independently. These are usage-based estimates, not invoices or credit balance.
- **A ten-question review starter now spans ten recording days and ten source
  groups**, with separate links to the three clips needing manual annotation.
  The private analysis and cost CSV are under `outputs/fountain-campaign/`.
  Source groups are not confirmed independent behavior episodes.
- Native Windows Edge verified **97 proposals ready**, both batches, playback,
  mobile layout and no JavaScript errors, without submitting a decision.
  The preceding development turn's 30 focused fixture tests remain the software
  regression record; the current turn adds real dispatch, accounting and UI checks.
- Local-only shortlist refresh continues without cloud authority. Its 11:03
  status reported 17 further candidates; this is an acquisition aid, not an
  authorization for a fourth batch. The original $20 ceiling has not been renewed.
- The target remains **around 15 November**. The immediate checkpoint is human
  adjudication and evidence visibility, followed by sufficient independent care
  episodes and blind evaluation on unseen days. The deadline does not override
  those requirements. See [the sprint plan](care-labeling-sprint.md).

For operating instructions, see [the learning guide](learning.md) and
[shared model service guide](shared-local-llm.md). For the pre-deployment test record, see [learning validation](learning-validation.md).
The live deployment and browser evidence are linked in the upgrade entry below.

## How to read the evidence

The distinctions in this table are important when writing about the project.

| Evidence level | What it can establish | What it cannot establish |
| --- | --- | --- |
| Design or code inspection | Intended contracts and implementation structure | That a live service is healthy |
| Unit/API tests | Behavior for the specific fixtures and mocked boundaries | Real camera accuracy or real message delivery |
| Browser tests with generated video | Layout, navigation, video/crop rendering, and decision interactions | Whether a label describes a real cat correctly |
| Native GPU pipeline test | That the packaged training and inference mechanics run on the actual GPU | Useful behavioral accuracy or production throughput |
| Live application/API checks | Current deployment, worker, camera, and dataset status | Long-term reliability or a qualified behavior model |
| Held-out real examples and shadow monitoring | Measured classification and alert performance under observed conditions | Events outside the camera view or a medical diagnosis |

A failure followed by a fix is part of the record. An older successful result is
not silently treated as current evidence. Private footage is kept out of this
journal; synthetic screenshots are safe examples of the interface, clearly
identified as fixtures.

## 1. The starting idea: an agent does the preparation

The inspiration was a screenshot describing a camera project that checked
whether a parked car was locked by observing folded mirrors. In that account,
an assistant found existing camera recordings, gathered examples, classified
them, noticed that its initial interpretation was wrong, revisited the images,
and trained a local detector. A recurring check then produced notifications.

The useful idea for cat-watch was the division of labor. The owner should not
have to manage a large annotation project, write a training pipeline, or inspect
hours of uneventful footage. The software should collect evidence, make proposals,
expose its reasoning, and ask for help where a human decision has value.

The cat problem is harder than the car's mirror state. Presence beside a fountain
is not proof of drinking. A lowered head is not enough to establish eating.
Standing in a litter area does not establish what happened there. Behaviors have
beginnings, endings, transitions and occlusions. This led to two central design
choices: classify short sequences rather than isolated snapshots, and preserve
an explicit “unclear” outcome instead of manufacturing certainty.

The requested destination is an agent that monitors behavior, analyzes routines,
and supplies summaries and alerts. The implementation approaches that destination
through evidence and acceptance gates rather than treating a model response as a
finished observation.

## 2. The existing foundation — reconstructed history

This work extended an existing FastAPI application rather than starting a second
web stack. The code runs in a Linux container managed by Windows Podman Desktop.
The source checkout is accessible through Linux/WSL, while the live data,
credential handling, camera access and actual deployment belong to Windows.
That distinction became important in both testing and deployment.

Repository history includes an initial release on 9 September 2026, motion
investigation work on 10 September, and investigation/focused-area changes on
13 September. These dates describe the commits; they are not invented timestamps
for every implementation step.

The [older acceptance record](acceptance.md) reports a 12 September investigation
checkpoint with 67 Python tests and a 13 September focused-capture/shared-Qwen
checkpoint with 80 tests. It also reports a bounded local Qwen request that
completed but still speculated about eating or drinking. That result established
an interface, not trustworthy behavior recognition. The new learning workflow
therefore retains the separation between machine suggestions and human labels.

The foundation already provided independent investigations, camera-area
polygons, exclusion masks, native-resolution crops, motion groups, recording
segments, review history, and an archived analysis queue. Existing history could
not be casually discarded just because the UI or training architecture changed.

The earlier audit recorded 212 prepared clips from 23 source groups, with about
943 seconds of prepared video. It also found 17 whole-group reviews but no
completed timed Label Studio annotations. These are historical inventory figures,
not a promise that the current import will produce exactly 212 decision cards:
new cards are generated per usable area crop, while shared sources remain grouped.
A whole-group opinion is also not a timed behavior label. Treating one as the
other would invent training truth.

## 3. The agreed product shape

The selected priority was care routines: eating, drinking, litter activity and
changes in activity. The target human workload was approximately five minutes
per day, represented initially by a daily queue of ten decisions. The interface
and summaries use English.

The agent performs collection, preparation and learning work locally. A local
vision-language model can propose a classification and explain the visible
supporting action. The owner can accept, correct, split a transition, mark an
unclear case, skip it, or undo a decision. The application retains the origin and
revision history rather than replacing one unexplained label with another.

Cloud review is optional and requires a new approval for every exact batch. The
approved design uses small, bounded exports: at most 20 clips, eight seconds per
clip, 16 area images per clip, a US$5 batch ceiling, and an expiry of at most
24 hours. These are software limits whose monetary guarantee depends on the
configured current provider prices and context limits. No cloud use is implied
by choosing a local label or starting the application.

The hardware is shared. Learning should use spare GPU capacity and yield to
monitoring. It should not stop, unload or restart another application's model to
make room. The practical result is queued work and resumable checkpoints when
capacity is unavailable, rather than assuming exclusive access to the GPU.

## 4. Implementation session — 2 November 2026, reconstructed

### Evidence collection and durable work

A separate learning database was added under the application's data directory.
This avoids reinterpreting or replacing the historical investigation database.
The learning store records clips, immutable manifests, prediction history, human
revisions, jobs, dataset snapshots, model records, observation coverage, events,
notices and cloud approvals.

Evidence comes from imported prepared clips, motion episodes, area visits and a
deterministic random audit window every fifteen minutes. New windows have context
and overlap, but overlapping exports and different area views of the same event
do not count as independent visits. Otherwise a long recording could produce
hundreds of nearly identical examples and falsely make the dataset look strong.

Extraction refuses missing source files and discontinuities. It does not bridge
an unseen recording gap and then present the combined clip as continuous action.
Source hashes and capture information follow the copied evidence into training.
Curated material has a separate storage budget, and reaching it pauses additions
instead of silently deleting reviewed evidence.

The background agent runs inside the application. It does not require this chat
to stay open. Collection, heavy teacher/training work and local inference have
separate execution paths. Work survives a restart through durable job records
and checkpoints, with explicit handling for operations whose outcome is unknown.

### Classification as a proposal

The local teacher uses timestamped native area crops and a visible-action prompt.
The prompt rejects inference from proximity alone and treats text visible in the
scene as evidence, not instructions. Suggestions include intervals, subject
assessment, quality flags, supporting observations and uncertainty.

The broad supervised classes are eating, drinking, litter activity, other
activity and no cat. Fine labels retain useful distinctions such as digging,
covering, elimination posture, sniffing, grooming, movement and stationary
behavior. Unclear and multiple-cat cases remain outside the initial supervised
single-cat dataset. “No label” does not become “no cat.”

Provider, model identity, model digest where available, prompt version and
sampling information accompany predictions. A model change during a local
annotation request invalidates that attempt rather than quietly mixing results
from different teachers. Model suggestions alone do not train this first version;
they reduce the work required to obtain reviewed labels.

### An interface centered on decisions and results

The new Today screen presents observations, coverage, confidence, summaries and
alerts. Decisions provides source context beside a synchronized native area crop,
visible explanations and a small set of direct actions. Timeline allows inspection
of earlier evidence. Learning exposes progress and evaluation. Settings retains
camera preparation alongside the new controls. Historical investigations remain
available through Archive.

The important interaction is deliberately small: watch a short clip, see the
proposal, and choose what the evidence supports. Keyboard shortcuts and a whole-
clip choice make obvious cases quick; the interval editor handles transitions.
Evaluation cases hide the proposed answer until the independent human decision
is saved. This reduces the risk that a human test label simply repeats the model.

Synthetic screenshots from browser acceptance are available at
[Today](../.artifacts/learning-ui/today.png),
[Decisions](../.artifacts/learning-ui/decision.png),
[Learning](../.artifacts/learning-ui/learning.png), and
[mobile layout](../.artifacts/learning-ui/mobile.png).
They depict generated fixture video, not real cat observations. The artifacts
are locally generated and ignored by Git, so an article author should explicitly
select and preserve approved figures rather than assume they are published assets.

### Reproducible local training

The local backbone is the VideoMAE checkpoint
`MCG-NJU/videomae-base-finetuned-kinetics`, pinned to revision
`488eb9a0565f257b32866000305c8178965eb9f6`. Its downloaded weights are checksum-
verified and build provenance is saved. Runtime model downloads are disabled.
The checkpoint's CC BY-NC 4.0 terms are recorded in
[third-party notices](../THIRD_PARTY_NOTICES.md); the application's original-code
license does not replace model-weight licensing.

The training pipeline compares a classifier-head experiment with a final-
transformer-block experiment. It selects the candidate and abstention thresholds
on validation data, then evaluates the selected model on test data. Day, source
and episode relationships are used to keep connected evidence in the same
partition. Frozen assignments survive later dataset versions; newly discovered
cross-partition connections are quarantined instead of silently leaking into
training.

Thirty confirmed independent examples per care behavior is an exploratory
readiness threshold. It is not an accuracy claim. Alert qualification additionally
requires sufficient independent positive and negative test examples, per-class
precision and recall targets, observation coverage, a routine baseline and
assessed shadow alerts. Metrics include uncertainty intervals so a small test
set cannot be mistaken for broad certainty.

Training records dataset identities, label versions, preprocessing, runtime and
checkpoint information. Corrected labels invalidate affected models. A final
version check also catches the less obvious race where a human corrects a label
while a training process is still running.

### Monitoring with an explicit notion of missing time

The application distinguishes recording from successful behavior analysis.
A healthy camera alone cannot establish that the model observed a particular
interval. Coverage therefore comes from analyzed source intervals, with a
separate record for each candidate model. Unclear classifications, stale
detection and multiple cats cannot establish a confident absence.

Routine summaries use the Jerusalem calendar, including daylight-saving
changes. Behavior alerts require sufficient analyzed coverage and a learned
baseline. Their wording is “not observed here,” which accurately describes the
camera's evidence. A shadow candidate must demonstrate its own coverage; it
cannot inherit another model's fourteen observed days.

Notifications use a durable outbox. A timeout may mean a request was delivered
but its response was lost. Blind retries could produce duplicate alerts, so an
ambiguous outcome is recorded rather than automatically repeated. A corrected,
invalidated model also causes its pending behavior alert to be cancelled before
outbound delivery.

## 5. Failures and corrections worth explaining in the article

These were development findings, not incidents involving actual cat care alerts.

| Finding | Why it mattered | Correction and evidence |
| --- | --- | --- |
| Duplicate motion/visit/area exports could inflate support | Many windows are not many independent observations | Merge overlapping episode identities and weight training windows by episode; regression tests exercise the counts |
| A candidate could inherit global analysis coverage | A new model could appear to have days of experience it never analyzed | Record and gate on coverage for the specific model |
| A human correction could coexist with a contradictory machine claim | Summaries could count both versions | Human intervals replace overlapping machine claims; models tied to old labels are invalidated |
| The most recent 100 alerts were insufficient for shadow assessment | Older false alerts might disappear from the promotion check | Evaluate all relevant shadow notices, independently of UI pagination |
| Two assessed false shadow alerts could leave a candidate blocking future learning | A permanently unpromotable candidate would prevent another training cycle | Reject the failed candidate explicitly; retain its record and permit future learning |
| Undo disappeared when the review queue became empty | The last decision was harder to correct than earlier decisions | Move Undo outside the disappearing decision card |
| A browser test initially relied on a CSP-disallowed evaluation form | The test failed before it could establish the UI behavior | Correct the test expression while retaining the application security policy |
| The initial crop was blank although source video had loaded | A visible detail view was a core promise of the decision screen | Wait for an actual presented video frame; strengthen the browser test to inspect rendered synthetic pixels |
| An area name could still refer to a very wide crop | A named region alone does not ensure a narrow outbound image | Reject cloud crops covering 80% or more of the frame; Telegram falls back to text |
| A newly added test nested SQLite write transactions | The test itself locked its database | Read its fixture outside the write transaction, then rerun the suite |

The blank-crop issue is particularly instructive. An earlier check asserted that
the canvas had a width, which was true even when it contained no pixels. Visual
inspection exposed the mismatch. The improved check tests the actual displayed
fixture pixels. This is a concrete example of strengthening evidence rather than
merely adding more tests that repeat implementation details.

## 6. What the pre-upgrade tests actually showed

The full Python suite passed **106 tests**. A later learning-specific run passed
**27 tests**, including one new shadow-rejection test beyond that full run. These
counts are reported separately to avoid implying that a 107-test full run was
performed at that point. The sole recorded warning was a dependency deprecation.

The Chromium acceptance run exercised desktop and mobile layouts, classification,
undo, navigation, disabled controls in review-only mode, and the actual initial
crop pixels. It reported no JavaScript errors or mobile horizontal overflow.

A native Windows/Podman test on the RTX 5080 exercised forward/backward training
and a Safetensors checkpoint round trip. A further generated-video pipeline test
exercised interrupted/resumed training, both candidate variants, independent test
evaluation, FFmpeg extraction and the live classifier. It ran with no network
and no live-data mount. Its resulting model did not qualify for behavior alerts,
as expected from a tiny synthetic dataset.

PowerShell syntax checks passed. The upgrade's Plan action successfully read the
new image and the stopped old deployment. The new image built before approval was
`localhost/cat-watch:0.5.0`, with immutable ID:

```text
1873e968a101c03dea10799858feba6caa0f5c05c13286b1ae11e155a6b17f0b
```

These results support the claim that the software pipeline and target GPU can
perform the intended operations. They do not support a numerical cat-behavior
accuracy claim, an inference throughput promise, or a claim of real Telegram
acceptance. Those require different evidence.

## 7. Windows upgrade — live journal, 2 November 2026

### 08:59 UTC — authorization and start

The user explicitly approved applying the prepared Windows upgrade and requested
this journal. No further confirmation was required for that same action.

The upgrade command was:

```powershell
.\scripts\upgrade-learning.ps1 -Action Apply
```

The helper inspected the existing container and found it stopped. It verified the
new image identity and planned a full application-data snapshot. The rollout
preserves the old container and its image; it does not delete the old deployment.
The new container reuses the application's data only after the snapshot's file
hashes have been checked.

The planned preservation identifiers for this run are:

```text
Backup directory: cat-watch-upgrade-20261102T085928Z
Old container:    cat-watch-before-learning-20261102T085928Z
```

These names are recorded for reproducibility. The backup lives under the existing
Windows application-data parent. They are not published image archives or proof
of successful startup; completion is recorded separately below.

### 09:05–09:09 UTC — verified deployment and real prerequisites

The Apply command completed successfully. The saved container is
`cat-watch-before-learning-20261102T085928Z`, still stopped on version 0.4.0.
The new `cat-watch` container reports **healthy**, and its immutable image ID
matches the approved 0.5.0 build. The snapshot contains **1,927 files totaling
9,817,682,118 bytes**. The helper compared SHA-256 hashes before preserving and
replacing the container name. The receipt records the old image and backup path.

The first successful startup response correctly said that the old investigation
had ended and that review was available. It did not claim camera or detector
activity. A separate local preview request was then used to verify camera access.
The camera returned a fresh **2560×1440** frame, with `camera=preview`,
`detector=stopped` and `capture_busy=false`. No calibration was confirmed, no
polygons were changed, and no recording was started. Only readiness metadata was
inspected; private camera pixels were not sent to a hosted model.

The local agent imported the prepared dataset and started extracting more clips
from archived evidence. At the 09:09 UTC snapshot, it reported:

| Live observation | Value at this snapshot |
| --- | --- |
| Preserved investigation inventory | 10 investigations, 217 motion groups, 17 whole-group reviews |
| Curated crop-level clips | 576 |
| Completed import jobs | 1 |
| Completed extraction jobs | 76 |
| Remaining extraction jobs | 1,294 queued; 1 running |
| Queued label jobs | 576 |
| Machine suggestions / human timed reviews | 0 / 0 |
| Daily decision queue | 10 items |
| Training ready / continuous recording | false / false |
| Curated evidence storage | 533,548,807 bytes against a 20,000,000,000-byte cap |
| Free GPU memory reported by the worker | 14,953 MiB |

These counts will change as extraction continues. In particular, one source clip
can produce more than one area crop. A larger decision-card count does not mean
more independent episodes or more human truth.

The main unmet prerequisite is now visible rather than speculative: the local
teacher reports **Qwen unavailable**, and a separate Windows-loopback check could
not reach the configured Ollama service. The worker is waiting and checking again;
it has not fabricated suggestions. There was ample free GPU memory, so the
observed dependency failure is distinct from memory admission. Starting another
service was not bundled into this deployment action.

Telegram is disabled and its credential is not configured. A cloud credential is
also not configured. There was no approved outbound batch and no real delivery.
The user can review existing evidence while these optional services remain off.

At **09:08 UTC**, a new read-only native Windows Edge check passed against the
actual deployed application. It verified Today, the ten-item review queue,
Learning, the disabled training gate, mobile width and the absence of JavaScript
errors. It did not modify decisions or calibration and did not inspect or capture
private images. This adds a native-host UI result beyond the earlier synthetic
Linux browser tests.

The request to open the dashboard in the Codex browser panel returned `queued`.
That is recorded as an opening request, not proof that the user saw the tab.
The local dashboard address is http://127.0.0.1:8765/.

Sanitized machine-readable evidence, with no tokens or image content:

- [Deployment snapshot](development-evidence/2026-11-02-upgrade.json)
- [Native Windows browser check](development-evidence/2026-11-02-windows-ui.json)
- [Reproducible read-only browser check](../tests/windows-learning-check.cjs)

The result of this milestone is a running application with preserved history and
an active evidence-preparation worker. It is not yet a qualified real-cat
behavior monitor. Fresh camera confirmation, the local teacher, reviewed timed
examples, independent evaluation days, and shadow performance remain the next
sources of evidence.

### Development-log maintenance

A project-level [AGENTS.md](../AGENTS.md) now instructs future work to maintain this
journal at substantive development, testing and deployment milestones. Entries
should explain the problem, choices, failures, correction, evidence and unresolved
work in readable prose. The latest-status section is updated, while earlier
observations are preserved and corrected through later dated entries.

The journal does not run an independent watcher. It is maintained as part of work
in this repository. Application runtime events remain in the app's own durable
stores. Neither mechanism authorizes publication or private-image sharing.

## 8. Article outline and claims to keep honest

A useful article could follow this sequence:

1. **The original camera idea.** Borrow the agent-led workflow, then explain why
   temporal cat behavior is harder than a visible mechanical state.
2. **Reducing the owner's workload.** Show a short decision rather than a large
   labeling tool; explain why the model's proposal and evidence remain visible.
3. **Building a trustworthy dataset.** Describe explicit unknowns, independent
   episodes, timed labels, native crops and leakage-resistant partitions.
4. **Making learning local and resumable.** Show why a successful GPU smoke test
   is a useful engineering milestone without calling it a trained cat expert.
5. **Treating uncertainty as part of the product.** Explain coverage, blind
   checks, shadow alerts, corrections and the difference between absence and
   not being observed.
6. **Giving the agent boundaries.** Explain cloud batch approval, cost limits,
   shared GPU ownership and preserving the previous deployment.
7. **What the real observations eventually show.** Add real dataset sizes,
   human review time, held-out metrics, false-alert rates and representative
   owner-approved examples only after they exist.

At this stage, “the agent can prepare data and train locally” is supported by
implementation and controlled tests. “The agent reliably detects this cat's care
routines” still needs representative real-data evaluation. “The agent diagnoses
health problems” is outside the current system's contract.

## Evidence index

| Topic | Primary repository evidence |
| --- | --- |
| Product workflow and operating limits | [Learning guide](learning.md) |
| Earlier investigation behavior | [Investigation guide](investigation.md) |
| Older, explicitly dated validation | [Acceptance history](acceptance.md) |
| Learning tests and deployment boundary | [Learning validation](learning-validation.md) |
| Annotation and provenance contracts | [contracts.py](../catwatch/learning/contracts.py) |
| Durable decisions and jobs | [store.py](../catwatch/learning/store.py) |
| Acquisition and sampling | [media.py](../catwatch/learning/media.py) |
| Training and evaluation | [training.py](../catwatch/learning/training.py) |
| Persistent local agent | [worker.py](../catwatch/learning/worker.py) |
| Live behavior inference | [inference.py](../catwatch/learning/inference.py) |
| Coverage, summaries and delivery | [monitoring.py](../catwatch/learning/monitoring.py) |
| Explicit cloud approval enforcement | [cloud.py](../catwatch/learning/cloud.py) |
| Human decision interface | [learning.js](../catwatch/static/learning.js) |
| Regression evidence | [Learning tests](../tests/test_learning.py) |
| Browser evidence | [Browser acceptance](../tests/browser_learning.py) |
| Native generated-video test | [Pipeline smoke](../scripts/learning-pipeline-smoke.py) |
| Windows upgrade and preservation | [Upgrade helper](../scripts/upgrade-learning.ps1) |
| Ongoing journal maintenance | [Project instructions](../AGENTS.md) |

## 9. 2026-11-02 — confirmed areas, first collection, and two live-only bottlenecks

### Authorization and the new reference image — 09:25 UTC

The owner reported that the litter-box cover was back in place, confirmed that
all areas were correct, and explicitly requested collection. That supplied the
camera confirmation required by the existing workflow. The assistant reused the
saved eating, water and litter polygons and the existing exclusion mask. It did
not redraw the areas or infer their positions from a hosted vision model.

A fresh preview was prepared and confirmed through the application's API. The
reference was 2560×1440, matching the previously saved dimensions. A comparison
verified that the polygons were unchanged. The monitoring endpoint created
**session 11 at 09:25:54 UTC** (11:25:54 in Asia/Jerusalem), with calibration
`7d010d102c4c43cd845090183a9b6fea`. The source session starts with a 24-hour
deadline; continuous mode extends it while the persistent controller is running.
It is not a one-shot 24-hour experiment.

The covered box matters to future interpretation. A camera can establish an
entry or visible litter-area activity without showing the hidden action inside.
The labeling policy must preserve that uncertainty; replacing an LLM cannot
recover actions the camera never saw.

[Sanitized collection-start receipt](development-evidence/2026-11-02-collection-start.json).

### A successful start response was not a successful collection run

The start request succeeded, but its follow-up health check timed out. Read-only
container and database checks showed that the process was running, the container
was unhealthy, the worker heartbeat had become stale, and segment registration
was progressing much too slowly. The recorder process alone was therefore not
accepted as evidence that the pipeline was healthy.

A temporary `py-spy` 0.4.2 installation inside the application container provided
thread stacks. It did not change host privileges, install a host service, or
inspect image contents. The first stack identified the detector inside diagnostic
cleanup while motion processing, the controller and API requests waited for the
same source-database lock.

The cleanup statement looked bounded because it used `LIMIT 1000`. However, that
limit applied to matching rows eligible for deletion. The historical sessions
were protected, so finding those matches could scan a large protected archive on
every detection. Live data exposed this cost; small synthetic fixtures had not.

The correction bounds **rows inspected**, advances through them by primary key,
and runs at most once per minute. Each pass considers no more than 1,000 rows,
keeps protected sessions and recent observations, and deletes only eligible old
diagnostics. Event, review and evidence records are not bulk-deleted. Cleanup is
incremental: it is not a promise that every expired diagnostic disappears at
exactly seven days, especially while traversing a large protected history.

A regression fixture puts thousands of protected rows before expired unprotected
ones. It verifies that bursts of detections do not repeat the scan, later batches
reach eligible rows, and protected and recent records survive. The first targeted
recording/retention run passed **27 tests**.

### First repair — 09:40 UTC

The first repair was built separately as `localhost/cat-watch:0.5.1`, image:

```
50031cad1825ffb4d212e2b06916f5d242c153dccd0fef81c4c720ab0dbb7dda
```

The 0.5.0 container was preserved as
`cat-watch-before-collection-fix-20261102T093949Z`. Three database-related files,
including the available rollback journal, were copied while the application was
stopped and checksum-verified under
`C:\Alex\data\tapo-cat-monitor\collection-repair-20261102T093949Z`.

The first receipt reports **zero recent media files copied**. The intended
recent-file filter mixed a parsed local DateTime with LastWriteTimeUtc; this was
corrected to an explicit DateTimeOffset-to-UTC comparison before the second
repair. The first snapshot must not be described as a verified backup of recent
footage. The earlier full upgrade backup still protected the historical archive.
Unregistered or unfinished files discarded by normal recovery are not claimed as
recovered evidence; the initial collection gap remains a real limitation.

After this repair the agent resumed session 11. At 09:42 UTC, 121 detection frames
had been processed and 898 review clips were available, mainly from existing
archive preparation. The camera was connected and the GPU detector ready.
However, further checks showed health responses taking about 5.4–5.5 seconds,
continued replacement of old detector samples, and an unhealthy container.
This partial recovery was recorded and investigated further.

[First repair receipt](development-evidence/2026-11-02-collection-repair.json),
[first recovered state](development-evidence/2026-11-02-collection-health.json),
[remaining latency evidence](development-evidence/2026-11-02-collection-progress.json).

### Second bottleneck: filesystem accounting inside the database lock

The second thread stack identified storage accounting. It recursively examined
files through the Windows-mounted data directory while holding the shared
database lock. A separate measurement took about six seconds to perform the
file checks. Multiple metadata calls per file and descending through the
separately budgeted learning directory added unnecessary work. During that scan,
detection persistence and health requests could not obtain the lock.

The fix uses directory-entry metadata, skips the learning tree before descending,
and does not follow symlinks. More importantly, the complete size scan occurs
**outside** the database lock. Quota decisions still protect active and leased
segments, keep the reserve, and preserve historical evidence. When deleting an
eligible generated segment, accounting subtracts its actual removed size rather
than resurveying the entire tree. A missing file cannot create fictitious free
space from an obsolete database size.

New tests exercise concurrent database reads during a deliberately slow scan,
learning-directory and symlink exclusions, and missing-file quota accounting.
The targeted suite then passed **30 tests**. The complete repository suite passed
**111 tests in 16.09 seconds**, with one existing Starlette/AnyIO deprecation
warning. Native PowerShell parsing also passed. These results cover software
contracts, not visual accuracy on this cat.

Reproduction of the software checks:

```bash
.venv/bin/python -m pytest -q
```

### Second repair and final live check — 09:48–09:50 UTC

The current image is `localhost/cat-watch:0.5.2`:

```
1a50a36141c6a0f13ccbd0855588968d2eaa4a5f0236dca83e4173ace3c3f1a7
```

Before applying it, the 0.5.1 container was preserved as
`cat-watch-before-collection-fix-20261102T094816Z`. The stopped application's two
databases and **104 recent media files** were copied and checksum-verified under
`C:\Alex\data\tapo-cat-monitor\collection-repair-20261102T094816Z`.
No new database format was introduced. The launch, learning-build and GPU-test
helpers now default to 0.5.2 so a future start selects the repaired version.
The build reused the installed dependencies and model layers.

The final three health probes, from 09:49:35 through 09:50:05 UTC, returned in
**77, 11 and 12 milliseconds**. Detection counts advanced **70 → 97 → 123**, the
camera stayed connected and the detector stayed ready. Frame ages were around
4–6 seconds, consistent with this segment-based pipeline. Capture-gap count was
zero after this restart. Dropped detector samples increased from 26 to 29 during
the interval, so this is not a zero-drop claim. Podman reported **running healthy**.

The 09:50 learning snapshot reported **928 review clips**, zero teacher proposals,
and zero human-reviewed learning clips. Most clips are from archive import and
extraction, not 928 independent newly observed behaviors. The source storage
reading was about **9.87 GB of the configured 50 GB cap**, with roughly 495 GB free
on the backing filesystem. Source recording and curated learning evidence have
separate budgets.

A read-only native Edge test loaded Today and Learning, found ten daily decisions,
confirmed that training remained disabled without sufficient gold labels, checked
390-pixel mobile layout, and found no JavaScript errors. It did not inspect private
images, make a classification decision, or change calibration. Its output was
saved separately to preserve the earlier upgrade UI result.

This verification establishes a working collector and responsive dashboard over
a short interval. It does not establish uninterrupted operation since 09:25,
long-term reliability, behavioral accuracy, or successful alerts.

Evidence:

- [Second repair receipt](development-evidence/2026-11-02-storage-repair.json)
- [Final health and learning snapshot](development-evidence/2026-11-02-collection-final-health.json)
- [Final progress and response times](development-evidence/2026-11-02-collection-final-progress.json)
- [Native Windows UI during collection](development-evidence/2026-11-02-collection-ui.json)
- [Bounded diagnostics regression](../tests/test_observation_retention.py)
- [Storage and concurrency regressions](../tests/test_retention.py)

## 10. 2026-11-02 — reviewing the local teacher for the actual workstation

The owner also requested credible-source research into newer or better local
models. Native checks confirmed the Ryzen 9 9950X3D, 64 GiB RAM and RTX 5080 with
16,303 MiB of reported memory. The configured teacher is Qwen3.5-9B, but its local
Ollama endpoint was unavailable. Consequently, its actual loaded digest,
quantization and throughput were not established. Collection readiness and
teacher readiness are separate facts.

The Hugging Face connector was unavailable, so the review used the model authors'
public pages, official repositories and model cards, plus Ollama's own package
listings. Search results from community sites and speculative release stories
were not used to support the recommendation. The review made no online inference
request and sent no private camera frames to a hosted model.

The recommendation is to retain Qwen3.5-9B as the baseline and compare Gemma 4 12B
locally before changing the teacher. Google explicitly describes the newer 12B
model as suitable for 16 GB GPU systems, but that is not proof of concurrent
cat-watch capacity or greater cat-behavior accuracy. The newer Qwen3.8-27B standard
four-bit package is about 18 GB before runtime overhead, making it a poor default
for fully GPU-resident operation alongside monitoring on this card. Published
visual scores do not establish a universal win for the proposed challenger.

The [full dated review](model-review-2026-11-02.md) supplies direct primary-source
links, distinguishes download size from VRAM, and specifies a proposed local
comparison: 60 independent episodes, two models, at most 120 requests, one request
at a time, six elapsed hours, 12 GB additional storage and no online-model calls.
The experiment needs representative human labels and actual runtime measurements;
it has not been executed or authorized as a model installation by this research
request. The model remains pinned to Qwen3.5-9B.

The next operational dependency is making the local teacher available, followed
by reviewing timed examples. Until then, the application can collect and prepare
evidence, but automatic proposals remain waiting and no real-cat model has
qualified for behavior alerts. This limitation is shown in the UI and retained
in the article record rather than being hidden behind the successful collection
health check.

## 11. 2026-11-02, 19:21 UTC — general agents need a resident shared model

The owner clarified that the local model should serve a wider purpose than cat
labeling: it should stay loaded on the GPU for various local agents. This changes
the selection criteria. General instruction following, tool use, coding,
multilingual tasks, request latency and predictable memory use matter alongside
visual behavior interpretation.

The comparison was refreshed directly from Qwen's and Google's model cards and
Ollama's runtime documentation. Qwen3.5-9B and Gemma 4 12B have mixed published
strengths; the evidence does not support calling either universally better.
The detailed [benchmark comparison](model-review-2026-11-02.md#follow-up-one-resident-model-for-general-local-agents--1921-utc)
records the main comparable scores and distinguishes unmatched tests. The Tau2
numbers receive an explicit scenario/protocol caveat. None of these published
scores was presented as a result from this workstation's quantized fast profile.

For a single resident general service on the 16 GB RTX 5080, the recommendation
remains Qwen3.5-9B Q4_K_M. The smaller package and published general capability
make it the initial choice; Gemma merits a local comparison if coding or direct
audio input dominates. No tokens-per-second or peak-memory result was invented
from model size, and this follow-up did not download or invoke either model.

The proposed deployment now has one shared service, one loaded model, independent
agent contexts, explicit idle retention, preload at service startup, a 16K initial
context and one in-flight generation. A proposed gateway would apply request
limits and prioritize interactive work between background labeling requests.
These are documented requirements, not implemented scheduling guarantees.

Keeping the general model resident also exposes a resource constraint: the
current training worker requires 8,192 MiB of free GPU memory before starting.
If the shared service leaves less headroom, training must remain queued. The
owner's new requirement must not be implemented by silently unloading the model
when training wants the GPU. This tradeoff belongs in the operational design and
should be measured before promising simultaneous training and general inference.

This was research and design documentation only. No source/runtime configuration
or host service was changed, no online inference ran, and no private footage was
inspected. The earlier 09:50 UTC live status was not refreshed during this
comparison and must not be treated as a new availability check. No code tests
were needed for this documentation-only update.

## 12. 2026-11-02, 19:35–19:50 UTC — a resident model becomes a working local service

The owner approved the previously proposed deployment: Qwen3.5-9B Q4_K_M should
stay on the GPU, serve local agents, and begin automatic cat-watch labeling while
recording continues. This authorization covered the local service and its
integration. It did not authorize a cloud inference batch, publication, or a
Telegram message.

### Restore collection, then attach the teacher

The first native Windows inspection found the cat-watch container stopped and
its API unavailable. The container's displayed exit age was not credible, so it
was not used to invent a shutdown time or cause. The maintained Windows launcher
resumed the existing application. Session 11, the confirmed polygons and masks,
and the continuous-collection setting were retained. Subsequent probes showed a
connected camera, ready detector and increasing frame counts.

This is an important correction to the earlier journal snapshot: a healthy
collector at 09:50 did not prove it was still running later. Collection was
resumed before the shared teacher was attached. From that point, the application
was kept running rather than redeployed for the service changes.

### Reuse verified local weights without reviving an unrelated application

The workstation already held a suitable Qwen package and Ollama image from the
inactive local WorldMonitor deployment. The source cache was inspected read-only.
A separate model volume was created for the shared service; all four referenced
blobs, totaling **6,594,474,711 bytes**, were independently verified by SHA-256.
No cloud model call or new model download was needed, and WorldMonitor's services
and source volume were not changed.

The exact model manifest is
`6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`.
The package identifies Qwen3.5 with Q4_K_M quantization; its metadata reports 9.7B
parameters for the published 9B model. The runtime is Ollama **0.34.0**, from
`docker.io/ollama/ollama@sha256:684d8674b4315fa18f4f0e973a118ec2652ed96f67563277839985175858e0ba`.
These identities are recorded in the [lock file](../scripts/shared-llm/model-lock.json).
They identify the verified cached artifacts, not a claim about the newest mutable
registry tags.

### One service for several agents

The runtime runs in a dedicated rootless Podman container under RHEL10 WSL. It
loads one model with a 16,384-token context, one concurrent generation, an
eight-bit KV cache and indefinite retention. A small local gateway exposes port
11434 and checks the loaded model's digest, context and GPU allocation every
15 seconds. The backend stays on loopback port 11435. Model administration and
per-client unload requests are blocked on the public gateway.

The queue admits at most 16 requests, waits at most 120 seconds for a slot, and
prioritizes interactive work over waiting background labeling work. It cannot
interrupt a generation already in progress. Each agent supplies its own messages;
model sharing does not create a shared conversation history. Native Ollama and
OpenAI-compatible chat interfaces were both tested, including a generated tool
call that was parsed but never executed.

User-level systemd units manage the gateway and runtime. The Windows
`SharedLocalQwen` sign-in task launches the existing WSL service with limited
privileges, no stored password, no machine wake and no missed-run catch-up.
Executing that task while the service was already up returned zero. A cold reboot
was not tested because recording was active. “Always loaded” therefore means
preloaded and retained while the workstation/runtime is operating, with startup
and recovery mechanisms; it does not mean the GPU can operate while powered off.

### From reachable API to actual saved proposals

Cat-watch's settings API was changed to `http://127.0.0.1:11434`. This route was
verified from native Windows and the camera container. The alternative
`host.containers.internal` name was rejected by the gateway's Host policy, so it
was not used. No LAN exposure was added.

At **19:39 UTC**, the first durable local proposal was verified. Detection frames
advanced from **1,016 to 1,121** while the suggestion count advanced from zero to
one, with a connected camera and no reported new capture gaps. The saved
prediction included the model digest, prompt version and temporal sampling
provenance. It remained a proposal, not a human label.

The next checks found two integration problems that a simple health check would
have missed:

1. The dashboard retained its earlier “Local Qwen is unavailable” message after
   successful proposals. A narrowly scoped metadata refresh was performed only
   after checking the GPU service and a recent saved prediction. The source now
   updates the worker status on recovery and on a failed proposal. That recurring
   correction awaits the next camera application deployment; the one-time live
   refresh did not restart the camera.
2. Many replies were rejected with **“Invalid evidence explanation.”** A bounded
   replay of one queued example confirmed the contract error without exposing
   private imagery or explanation text in this journal. Plain JSON formatting
   did not guarantee that the explanation and uncertainty fields were strings.
   The shared gateway now applies an explicit response schema to the existing
   cat-watch prompt. Other agents' JSON formats are unchanged, and the
   application's interval/subject validation remains authoritative.

The gateway alone was restarted at **19:47:45 UTC** to apply the schema. The GPU
runtime retained its original **19:35:18 UTC** start time and did not restart;
recording also continued. The first immediate API smoke check raced the gateway
listener and received connection refused. The verification helper was corrected
to wait for readiness, then native JSON, OpenAI tool-call generation and streaming
all passed again. This was a startup-check race, not evidence of an unloaded model.

A diagnostic initially counted lines containing the word “truncated.” Reading the
bounded runtime metadata showed these were normal completion records with
`truncated = 0`, not evidence of input truncation. No frame-resizing workaround or
larger context was introduced on that mistaken basis.

By **19:50:54 UTC**, **20 proposals** had been saved, with eight visible in the
current ten-item review queue. There were 3,562 prepared clips, 3,537 queued label
jobs, one running job and four failed label jobs after their bounded attempts.
Those failed jobs remain unresolved evidence for review; they were not converted
into accepted labels. The last successful prediction was about 18 seconds old.
The initial archive backlog is large, so this check establishes that autonomous
work is advancing, not that the archive has finished processing or that every
model answer will pass validation.

### GPU accounting changes the training decision

Ollama reported **5,763,005,151 bytes resident, all on the GPU**, with the expected
16K context and pinned digest. Native GPU accounting during the follow-up showed
**9,442 MiB used and 6,536 MiB free** on the 16,303 MiB RTX 5080. Total card usage
includes more than Ollama's resident-weight report.

The camera worker's CUDA reading simultaneously claimed approximately **14,599
MiB free**. Running `nvidia-smi` inside that same container agreed with the native
host instead. The virtualized CUDA reading therefore could not safely determine
whether another training process would fit alongside the resident shared model.
Automatic training was explicitly disabled through the settings API. Recording,
learning collection and local proposal generation stayed enabled.

The source capacity check now takes the lower of CUDA and host GPU readings and
queues heavy work if the host reading is unavailable. Regression tests cover the
observed disagreement and unreadable metrics. This code is **not yet in the live
0.5.2 camera process**: deploying it would require a separate camera application
restart. Training stays paused until that deployment and native validation.
There are also no human-reviewed learning clips yet, so the real-data training
eligibility gate remains unmet. The shared model will not be silently unloaded
to make room for training.

### Validation and remaining work

The final relevant fixture run passed **34 tests in 7.50 seconds**, with one
upstream TestClient deprecation warning. Two earlier restricted-environment runs
stalled at the API fixture; only those owned test processes were stopped. A
bounded run with local networking available completed. The passing result covers
the gateway policy/schema, worker-status recovery, conservative memory handling
and existing learning contracts. It is not the earlier 111-test collection result
and does not measure real-cat accuracy.

Native Windows Edge passed Today and Learning loading, the ten-decision display,
training-disabled state, mobile layout and absence of JavaScript errors. No human
decision was submitted by the browser check. Final camera evidence showed
**2,251 analyzed frames**, detector lag **4.7 seconds**, a connected camera and
zero reported capture gaps since this resumed run. The recorder stayed in session
11 throughout the shared-service changes.

Next work is to review the visible proposals, collect independent labeled days,
and deploy/validate the host-aware training guard during a suitable camera
maintenance interval. A qualified behavior model, trustworthy alert accuracy and
actual Telegram delivery remain unproven. No private footage was uploaded to a
hosted model during this work.

Evidence and reproducibility:

- [Service setup and operating guide](shared-local-llm.md)
- [First proposal and advancing capture](development-evidence/2026-11-02-shared-qwen-labeling.json)
- [Initial synthetic API checks](development-evidence/2026-11-02-shared-qwen-api.json)
- [API checks after schema deployment](development-evidence/2026-11-02-shared-qwen-api-schema.json)
- [Earlier native startup/GPU/camera snapshot](development-evidence/2026-11-02-shared-qwen-final.json)
- [Final proposal counts and continued recording](development-evidence/2026-11-02-shared-qwen-followup.json)
- [Native Windows UI check](development-evidence/2026-11-02-shared-qwen-ui.json)
- [Gateway checks](../tests/test_shared_llm.py) and [worker/capacity regressions](../tests/test_teacher_recovery.py)

The relevant test command was
`.venv/bin/python -m pytest -q tests/test_shared_llm.py tests/test_teacher_recovery.py tests/test_learning.py -o faulthandler_timeout=25`.
The local API verifier is `scripts/shared-llm/verify.py --evidence <new-output.json>`;
it uses three synthetic requests and does not execute generated tool calls.

## 13. 2026-11-02 — deploying the GPU memory guard and restoring automatic training

The owner authorized deployment of the memory fix, re-enabling automatic training,
keeping Qwen loaded and minimizing interruption to recording. This resolved the
pending-deployment limitation in entry 12. A brief controlled camera handoff was
within that authorization; no additional confirmation was requested for the
already approved work.

### Establish the live baseline before changing anything

At **20:10 UTC**, version 0.5.2 was running on Windows Podman, the camera was
connected, the detector was ready and session 11 was still collecting. There were
3,668 prepared clips, 76 saved proposals and no reviewed learning clips. Training
was disabled from the previous maintenance decision. Qwen's shared service was
healthy and fully GPU resident.

The memory discrepancy was still present: the app reported approximately
14,599 MiB free while native GPU accounting reported 6,478 MiB free. The main
application database was approximately 1.27 GB; the learning database about
10 MB. Measuring those sizes mattered because snapshotting all video during the
handoff would unnecessarily extend recording downtime. The update changes two
Python modules and no data schema, so a verified database snapshot and preserved
old container are suitable rollback support while media remain in place.

### Prepare a small candidate while recording continues

A new [patch Containerfile](../Containerfile.gpu-memory) builds directly on the
verified deployed 0.5.2 image and replaces only `learning/training.py` and
`learning/worker.py`. It does not install dependencies, download model weights or
replace the shared Qwen runtime. The new image is **localhost/cat-watch:0.5.3**:

```text
540a4e088dd95c017766509195324f951e88e0c611048e9fd4a6fce291d5610f
```

The existing memory fix takes the lower of CUDA and host `nvidia-smi` free-memory
readings. Invalid, unavailable or timed-out host readings leave heavy work
waiting. The other deployed change updates the worker's status when local
labeling becomes available or a proposal fails, replacing the one-time status
repair described in entry 12.

Before stopping the camera, **34 relevant tests passed in 3.92 seconds** with one
upstream TestClient deprecation warning. A separate candidate container then ran
on the real GPU with networking disabled and no live data mounted. It measured
**6,102 MiB free**, matching the host reading, although CUDA alone reported
14,953 MiB. Calling the training entry point with a disposable fixture returned
“Waiting for GPU capacity” before dataset partitioning or model allocation. No
training workload was started. The candidate's two module hashes matched the
source files exactly.

The [native check script](../scripts/check-gpu-memory.py) makes this distinction
reproducible: it tests real memory accounting and early refusal, not a synthetic
claim about model accuracy or a full GPU training benchmark.

### Keep the recording handoff short and reversible

A [scoped deployment helper](../scripts/deploy-gpu-memory.ps1) first validated a
concrete Plan against the live app and candidate identity. Unlike the original
first-learning-upgrade helper, this code-only handoff supports an existing
learning database. It refuses an unexpected image, unrelated writer or unhealthy
baseline. It preserves the previous container and can restore it if the new
camera, calibration or Qwen checks fail. It does not overwrite new media or
annotations during code rollback.

The actual UTC sequence was:

| Event | UTC time |
| --- | --- |
| Stop requested for the camera application | 20:15:04.939 |
| Application finished stopping | 20:15:12.392 |
| Database snapshots copied and SHA-256 verified | 20:15:16.538 |
| New application camera connected and detector ready | 20:15:49.721 |
| Deployed native memory check completed | 20:16:39.130 |
| Automatic training re-enabled through the settings API | 20:17:32.353 |
| Further labeling and recording progress verified | 20:18:48.559 |

The preserved container is
`cat-watch-before-gpu-memory-20261102T201504Z`. The snapshot directory is
`C:\Alex\data\tapo-cat-monitor\gpu-memory-backup-20261102T201504Z`.
It contains the main and learning databases, with checksums in the deployment
receipt. It is a **database-only snapshot**, not a new full-media backup. No
schema migration or camera calibration change was performed.

Stop request to camera readiness took **44.78 seconds**. A separate read-only
query of 44 registered media segments around the handoff measured one gap over a
second: **20.661 seconds**, between segments 43840 and 43841. Recorded media
resumed before detector readiness was announced. Reporting both values avoids
mistaking application initialization time for missing footage.

The application frame counter restarted with the new process. Its later zero
capture-gap counter therefore must not be read as proof of zero maintenance
interruption. The explicit segment-timestamp measurement preserves that history.

### Prove that Qwen remained resident

A separate monitor ran from **20:14:48.909 to 20:19:01.595 UTC**, spanning the
handoff, native acceptance and training re-enable. All **243 samples** observed
the exact pinned Qwen digest, a 16,384-token context and `size_vram` equal to the
reported resident size. The GPU runtime's process identity, start identity and
restart count were unchanged before and after. Neither the gateway nor the
runtime was restarted for this deployment.

Sampling does not prove an arbitrary sub-second invariant, but the unchanged
runtime identity and consistent loaded-model responses support the requested
resident-service behavior across this maintenance interval. No alternate model
was loaded to make room for training.

### Re-enable the scheduler after validating the deployed files

The same native check was run inside the newly deployed camera container. Its
module hashes matched the candidate. It measured **6,085 MiB free** from both the
corrected function and host tool, versus 14,953 MiB from CUDA alone, and again
refused the disposable training fixture before model allocation.

Only after that check was the supported settings API used to set `training` back
to `true`. The admission threshold remains **8,192 MiB**, with a **2,048 MiB**
running reserve. The training preference is enabled; it is not a command to
ignore capacity or fabricate human-reviewed examples. The current free memory
and zero reviewed clips leave the scheduler waiting, with no training jobs
started. Qwen will not be unloaded to satisfy the gate.

After the preference changed, recording frames advanced from **178 to 302** and
saved suggestions from **101 to 102**. The final progress record contained 3,720
prepared clips, no reviewed clips, 6,344 MiB available and a fresh “Local Qwen is
ready” worker status. Thus the recurring status repair is now live, not merely
staged source. Recording and local proposals continue while training waits for
its legitimate prerequisites.

Native Windows Edge loaded Today and Learning, found the ten-item daily queue,
passed the mobile layout check and reported no JavaScript errors. Its manual
Train button remained disabled because the independent-label gate is unmet;
this is separate from the now-enabled automatic-training preference. The browser
check made no classification decisions or calibration changes.

The maintained launcher, build helper and GPU-check helper now default to 0.5.3.
The learning and shared-model guides explain the deployed capacity policy and
remove the previous instruction to keep training disabled pending deployment.
Earlier journal entries and receipts remain unchanged historical observations.

### Evidence and limits

- [Candidate native GPU check](development-evidence/2026-11-02-gpu-memory-candidate.json)
- [Deployment, backup hashes and readiness timings](development-evidence/2026-11-02-gpu-memory-deployment.json)
- [Native check of the deployed modules](development-evidence/2026-11-02-gpu-memory-live.json)
- [Training re-enable and subsequent recording/labeling progress](development-evidence/2026-11-02-gpu-memory-training-enabled.json)
- [Recording gap from media timestamps](development-evidence/2026-11-02-gpu-memory-recording-gap.json)
- [Qwen residency samples and unchanged runtime identity](development-evidence/2026-11-02-gpu-memory-residency.json)
- [Native Windows UI acceptance](development-evidence/2026-11-02-gpu-memory-ui.json)

The regression command was
`.venv/bin/python -m pytest -q tests/test_shared_llm.py tests/test_teacher_recovery.py tests/test_learning.py -o faulthandler_timeout=25`.
PowerShell parsing and repository whitespace checks also passed. GPU acceptance
used `scripts/check-gpu-memory.py` in an isolated candidate and then the live
container, rather than running a full training benchmark beside recording.

This completes the authorized maintenance: the fix is deployed, automatic
training is enabled, Qwen remains loaded, and collection and labeling continue.
It does not qualify a behavior model, establish long-term uptime, create human
labels or demonstrate Telegram delivery. Those remain separate evidence gates.

## 14. 2026-11-03 — A bounded cloud comparison and a real local baseline

### User intent and what the authorization covers

The user activated the API-credits option, reported $39 available in the current
billing cycle, and explicitly authorized spending **up to $20** with the proposed
models while monitoring costs and comparing results against local Qwen. This is
authorization for the bounded comparison; it does not require asking again for
the same batch. The account balance remains user-reported, not independently
verified. The limit is a ceiling, not an instruction to spend the whole amount.

The selected cloud roles remain GPT-6.1 Sol with medium reasoning for the initial
pass, and GPT-6 Astra with high reasoning for up to five difficult cases. Current
official model documentation confirms both image input and those effort levels.
The [comparison guide](cloud-comparison.md) records the model, pricing and token
counting sources consulted on this date, together with reproducible commands.

### Keep the experiment separate from continuous recording

The live service already supports a different, batch-oriented cloud path, but
does not have a configured API key. Deploying a new web process just to supply
credentials would unnecessarily interrupt collection. Instead, the new runner
uses the verified 0.5.3 image as its offline base and adds only the comparison
modules. Its image identity is
`860560a68d52d3b5409679043b3e5b61946ada98e58142a5c65a00b9981f3d01`.

The runner has two CPU cores and a 2 GiB memory limit, no direct GPU device,
a read-only container filesystem, and no elevated capabilities. It reads the
learning database in read-only mode and writes its own experiment files and
ledger. Qwen inference goes through the existing shared service at background
priority. Neither the recorder nor the model service was restarted.

The frozen manifest contains ten non-overlapping clips from distinct source
groups, each sampled at sixteen timestamps. Actual durations are 6.012–7.990
seconds. The 160 cropped frame positions use 399×449 or 510×489 native pixels;
full-room images and audio are excluded. Frame hashes are checked again before
outbound use. All models receive the same images and instruction text. Human
answers and other models' predictions are withheld from cloud prompts.

There was an instructive selection limitation. The strict six-second lower
bound excluded four reviewed exports lasting about 5.999 seconds, as well as
five substantially shorter clips. The selected cohort therefore has only one
human reference, and that review was assisted rather than independent. The
experiment is useful for inspecting disagreement and response validity, but
not for ranking cat-behavior accuracy. A later evaluation should include a
frame-aware duration tolerance and more independent references. This entry
preserves the actual frozen selection rather than silently improving it after
seeing results. Global clip creation and the daily review queue were not changed.

### Make the spending limit survive crashes and repeated commands

The ledger uses integer microdollars and transactional reservations. A request
must fit its maximum allowed exposure before the first outbound call. The
reservation includes token counting and generation, at conservative input rates,
plus all permitted output tokens, including hidden reasoning. Sol reserves
$0.696320 per attempt; Astra reserves $3.686400. Returned token usage supplies
the inference estimate and conservative settlement. Unknown outcomes keep their
entire reservation. Rerunning a command never retries an already attempted
clip/model pair or resets the budget, and an unresolved cloud result stops the
campaign before another request.

This one-shot authorization expires at 09:58:17 UTC on 3 November, six hours
after preparation. There is no recurring allowance or background scheduler.
The CSV records individual requests and token categories; the Markdown report
shows model explanations beside human references. Cost estimates are clearly
separated from conservative exposure and from an actual provider invoice.
Neither the reported $39 credit balance nor eventual billing reconciliation is
inferred from a successful token-count calculation.

The report counts invalid responses as missing predictions in the attempted
human-reference denominator. Astra's cases are selected for low agreement or
invalid output, so the report also includes a matched three-model subset.
Comparing Astra's hard cases against Sol's whole, easier cohort would otherwise
give a misleading ranking. Unreviewed clips can show disagreement only.

### Validation, failures and the native local result

Eight new fixture tests exercise concurrent budget reservations, persistence
across restart, attempts to under-reserve or change authority, unknown-request
retention, changed-image rejection, token limits, hidden reasoning charges,
invalid-output costs and reference metrics. The combined relevant suite passed
**42 tests in 8.02 seconds**. Its first sandboxed attempt stalled in an existing
Starlette/AnyIO test-client startup; it was interrupted, then the same fixture
suite passed outside that restriction. This was not a live recorder failure.

The first native launcher attempt also exposed PowerShell's removal of quotes
inside a Go-template label lookup. It stopped before frame preparation. Reading
the image's labels as JSON fixed the quoting boundary; the next preparation run
completed. No cloud request or paid retry was involved in either issue.

The real Qwen baseline ran from approximately **03:58:51 to 03:59:26 UTC**.
Nine of ten outputs passed annotation validation, with a mean of **3.179
seconds** per attempt. One attempt was recorded as a `ValueError`; its minimal
failure receipt does not retain enough detail to distinguish every validation
cause. It was not silently repaired or retried. The single assisted human
reference agreed over 5.954 labeled seconds. That isolated agreement is not an
accuracy estimate and supplies no independent evaluation evidence.

At 04:00:40 UTC the live camera remained connected and the detector ready.
Analyzed frames advanced from 43,972 in the initial readiness check to 45,725;
saved suggestions advanced from 1,935 to 2,023. The ten human decisions were
unchanged. The live container still had the 0.5.3 image and its 2 November
20:15 UTC start identity. Qwen reported the exact pinned digest, 16K context and
5,763,005,151 bytes fully GPU resident. These observations support progress
without a deployment restart; they do not prove absence of every transient
camera or network gap.

### The remaining blocker is authentication, not spending approval

No API key was present in the supported Windows DPAPI credential file or the
checked environments. A native secure prompt was opened for the user to save a
project key for the organization holding the credits. The secret is entered
locally, not in chat, and the runner will receive it through stdin rather than
process arguments, environment metadata or logs. Saving it does not itself
start an unattended task.

At the final recorded readiness check the key was still absent. Consequently
**zero cloud inference requests and zero private-frame uploads occurred, with
$0 spent and the full $20 authorization uncommitted**. Live Sol/Astra responses,
model-to-model comparison results and API billing reconciliation remain pending.
The production Cloud indicator stays disabled; the separate runner is prepared
but has not established a live cloud connection. Human training labels were
not replaced and no model was trained or promoted during this work.

Evidence:

- [Sanitized native baseline and zero-spend summary](development-evidence/2026-11-03-cloud-comparison-baseline.json)
- [Final recording, credential and Qwen readiness receipt](development-evidence/2026-11-03-cloud-comparison-readiness.json)
- [Experiment contract, official sources and continuation commands](cloud-comparison.md)

Private per-clip Markdown/JSON reports, image manifests and the cost CSV remain
in application storage, outside this article journal. The validation command was
`.venv/bin/python -m pytest -q tests/test_comparison.py tests/test_learning.py tests/test_teacher_recovery.py tests/test_shared_llm.py -o faulthandler_timeout=25`.
The native command was `scripts/run-cloud-comparison.ps1 -Stage Local`; the
future `Cloud` stage requires the locally saved key and an unexpired manifest.

## 15. 2026-11-03 — Credentials verified; exact media approval requested

The user confirmed that the project API key had been saved. At **04:08:36 UTC**,
a native Windows readiness check confirmed that the DPAPI credential file now
exists. It also observed a connected camera, ready detector, 46,507 analyzed
frames and 2,054 suggestions, with the same ten human reviews. Continuous
recording and the training preference remained enabled. The recorder retained
its existing image/start identity, and the pinned Qwen model remained fully GPU
resident. No service restart was needed to make the key available to the
separate runner.

The attempt to invoke the prepared cloud stage was rejected by automatic
approval review **before process execution**. The review cited the earlier
requirement to approve each exact batch and stated that the budget authorization
did not provide trusted approval of these specific clips. This is a later
operational constraint on the interpretation in entry 14, which treated the
user's $20 instruction as sufficient for the bounded experiment. The rejection
was not bypassed by another execution route.

Useful checks could still be completed without transferring footage. At
**04:09:41 UTC**, two read-only `GET /v1/models/{model}` requests returned HTTP
200 and the expected identifiers, `gpt-6.1-sol` and `gpt-6-astra`. These checks
used the saved secret transiently and recorded only model IDs and HTTP status.
No key, provider error body, image, clip ID or prompt was included in the receipt.
This establishes access to model metadata; it does not independently verify
the reported credit balance or successful image inference.

The exact outbound selection was then made human-readable, with local source
video links, each crop's timestamp and local file link, and its SHA-256. All 160
frame hashes were rechecked successfully. One complete pass contains 7,465,399
bytes of prepared JPEG data before base64 expansion. The immutable manifest
fingerprint is
`564f58a07e60d9117254be7819b64526ffb5bf8438d37e8473f145bb94c861de`.
The private approval document is kept in ignored local output, not copied into
this article journal.

The approval request explicitly covers these 160 crops only: Sol/medium on all
ten clips and Astra/high on at most five selected from that same set. Token
counting resends the same images before generation, so the full experiment can
make at most fifteen counting and fifteen generation calls, with no additional
camera frames. The existing $20 total limit, expiry, durable ledger and no-retry
policy remain unchanged. A named-area crop can still contain private details;
the request identifies OpenAI as the recipient.

At **04:10:58 UTC**, a read-only ledger check still found **zero cloud requests**.
No reservations were created by the blocked invocation and spend remains **$0**.
The prepared local baseline is preserved. No models were trained, human labels
changed, or automatic production cloud dispatch enabled. Exact-batch approval
is now the remaining step before trying real inference.

- [Readiness after the key was saved](development-evidence/2026-11-03-cloud-comparison-before-dispatch.json)
- [Successful read-only model-access checks](development-evidence/2026-11-03-openai-model-access.json)
- [Frozen-batch hash verification and zero-request receipt](development-evidence/2026-11-03-cloud-batch-approval.json)

This continuation changed documentation and prepared a private review artifact;
it did not change runtime code. No new fixture-test pass is claimed. The 42-test
result remains the earlier evidence in entry 14.

## 16. 2026-11-03 — The approved cloud run completes below one dollar

### Authorization resolved and the exact experiment executed

The user answered **“Approve this exact batch”** to the question naming manifest
fingerprint `564f58a07e60`, its 160 cropped frames, Sol/medium on ten clips,
Astra/high on at most five of those same clips, token-counting uploads, the $20
total ceiling, and no automatic retries. This resolved the review rejection in
entry 15. The full manifest fingerprint was rechecked against the durable ledger
and the authorization was still unexpired before dispatch.

The native runner used the original comparison image
`860560a68d52d3b5409679043b3e5b61946ada98e58142a5c65a00b9981f3d01`.
The first cloud result completed at **04:13:12 UTC** and the last at **04:16:10
UTC**. All ten Sol generation requests and all five Astra generation requests
completed with valid annotations. Each generation was preceded by a token-count
request, for thirty outbound request bodies containing approved crops in total.
No additional camera frames were selected, no failed request was retried, and
no unknown outcome remained. Post-run hashing again matched all 160 prepared
frame positions to the approved manifest.

The returned model identifiers were exactly `gpt-6.1-sol` and `gpt-6-astra`, and
every generation reported the default service tier. The request configuration
used standard reasoning mode with medium/high effort, respectively. There were
no tools, extra model downloads, or separate cloud training jobs.

### Cost monitoring caught a real accounting omission

The budget reservations were deliberately conservative, but the first displayed
inference estimates charged every non-cache-read input token at its ordinary
rate. Real Responses usage included a separate `cache_write_tokens` category.
Ignoring it understated the estimated bill even though the larger reservations
already covered it. This is why usage details and budget exposure are retained
separately instead of treating a single number as both cost and safety margin.

The current [official prompt-caching guide](https://developers.openai.com/api/docs/guides/prompt-caching)
states that the default 30-minute write rate is 1.25 times ordinary input, while
a 12-hour write uses 2.5 times that rate. Those replace the ordinary rate for the
written tokens; they are not an extra full input charge. This experiment did
not request cache options or explicit breakpoints, so the documented 30-minute
default applies where the returned usage omits a lifetime breakdown.

The estimator was corrected to distinguish ordinary input, cache reads, 30-minute
writes, 12-hour writes, and output including reasoning. Invalid category totals
are rejected. Six added fixture cases cover default and mixed write lifetimes,
invalid breakdowns and idempotent offline reconciliation, bringing the focused
comparison suite to **14 passing tests in 0.82 seconds**.

The running inference process was left untouched. After it completed, an offline
reconciliation stage corrected all fifteen saved estimates, retained each prior
estimate with a dated reason/source in the request's audit history, and regenerated
the CSV and reports. It made no inference or token-counting calls. The separate
accounting image is
`ce95b633e5f7503791b9543b3c7081c3ce1917fd39b1d346210ed538641999bf`.
No reservation, conservative exposure, authorization, image selection or label
was changed by the correction. An independent decimal calculation from the saved
usage verified every revised amount, allowing only conservative microdollar
rounding.

| Model | Requests | Input tokens | Cache-write tokens | Output tokens, including reasoning | Estimated inference cost |
| --- | --- | --- | --- | --- | --- |
| Sol, medium | 10 | 52,654 | 52,624 | 2,831 | $0.159930 |
| Astra, high | 5 | 25,159 | 25,144 | 4,139 | $0.521400 |
| Total | 15 | 77,813 | 77,768 | 6,970 | **$0.681330** |

There were no cache-read tokens in these results. Reasoning accounts for 1,218
Sol output tokens and 3,267 Astra output tokens; it is already included above.
The original displayed total was $0.592158. The $0.089172 correction is retained
as history, rather than silently replacing the evidence of the omission.

Conservative accounted exposure stayed **$2.019750**, including the token-count
allowance and highest input rates. Remaining authorization is therefore
**$17.980250**. This is deliberately stricter than subtracting the inference
estimate alone. Neither value is a provider invoice or a verified remaining
credit balance. The approved batch is complete; unused authorization is not a
scheduled instruction to spend more.

### What the models disagree about

Qwen produced nine valid annotations out of ten attempts at a mean 3.179 seconds
per attempt. Sol produced ten out of ten at 7.841 seconds, and Astra five out of
five at 20.933 seconds. These are end-to-end request times in this setup,
including model-specific preflight work, rather than isolated GPU generation
benchmarks. Different model sizes, reasoning settings, backends and Astra's
deliberately difficult selection prevent a clean causal comparison of effort
or model architecture.

The important diagnostic difference is that Qwen proposed eating in seven
clips, while Sol proposed it in none. In the selected five-clip subset, Sol and
Astra agreed on every subject assessment and ordered behavior-label sequence,
although some time boundaries differed. The cloud outputs more often used
`unclear` when their explanations said visible action was insufficient. This
does not prove that the cloud classifications are correct: the cohort contains
only one assisted human reference, and the Astra subset contains no human
references at all. The independent-reference denominator is zero.

The private report therefore presents model claims and abstention coverage,
rather than a headline “accuracy” percentage. It includes clip links, the
per-model label sequence, full explanations and three focused human-review
questions. These target care-action evidence, transition timing, and visible
subject assessment. No suggested answer was submitted on the user's behalf.

The practical inference from this pilot is to retain the inexpensive local
first pass and evaluate Sol as a selective reviewer of questionable care labels.
Astra supplied similar label sequences at higher cost and latency on this small
subset; there is no demonstrated quality gain here from routine Astra use.
Human adjudication remains necessary before these outputs can support training,
promotion or alerts. This is an experiment result, not a deployed labeling-policy
change or a general model leaderboard.

### Recording, residency and reproducible evidence

At **04:20:20 UTC**, the camera was connected and the detector ready. Frames
advanced from 46,507 at the credential-era preflight to **47,616**; saved
suggestions advanced from 2,054 to **2,107**, with **4,314 prepared clips** and
the same **ten human reviews**. The recording container retained its original
0.5.3 image and 2 November start identity. Qwen still reported the pinned digest,
16K context and 5,763,005,151 bytes entirely resident in GPU memory. A during-run
receipt also recorded progress. These are bounded live observations, not a
claim of perfect frame continuity.

The production dashboard's cloud dispatch remains disabled because this work
used a separate approved runner. There are no automatic new cloud batches,
retries or recurring spending tasks. Recording and local proposals continue;
human decisions, training data and the training preference remain intact.

- [Completed results, token totals, comparisons and independent cost checks](development-evidence/2026-11-03-cloud-comparison-results.json)
- [Historical initial cost estimate before correction](development-evidence/2026-11-03-cloud-comparison-initial-costs.json)
- [Recording and Qwen during the experiment](development-evidence/2026-11-03-cloud-comparison-during-run.json)
- [Final live readiness and unchanged recorder identity](development-evidence/2026-11-03-cloud-comparison-after-run.json)
- [Maintained experiment guide and official sources](cloud-comparison.md)

The commands were `scripts/run-cloud-comparison.ps1 -Stage Cloud`, then the
offline `-Stage Reconcile`. Private analysis was generated from saved results by
`scripts/summarize-cloud-comparison.py <comparison-directory>` with no network
access. Regression verification used
`.venv/bin/python -m pytest -q tests/test_comparison.py`. No new full-suite result
is claimed beyond the earlier 42-test run; no real-data model was trained or
promoted and no Telegram delivery was attempted.


## 17. 4 November 2026 — Suspend training and concentrate on useful care labels

### The user's priority and the first live change

The user asked to suspend training until more confirmed examples accumulate,
concentrate on drinking and litter activity, send the best 100 candidates to Sol
with a preference for recent footage, and present the results for review. The
prototype deadline is approximately 15 November. This changes the immediate
priority from keeping training enabled to improving the evidence that training
will eventually consume.

At **04:11:29 UTC (06:11 Asia/Jerusalem)** the supported settings API confirmed
`training=false`, while continuous monitoring remained enabled. The camera was
connected, the detector ready, and the frame counter was 181,948. The learning
store held **6,038 clips, 4,757 suggestions and ten reviewed clips**. Human-confirmed
independent episode counts were eating 2, drinking 0, litter activity 0, other 2
and no-cat 2. These counts explain why a large clip inventory does not yet mean
a usable supervised dataset. No real model training or accuracy claim follows
from this setting change.

The evidence receipt is
[the training-suspension record](development-evidence/2026-11-04-training-suspended.json).
Recording was not restarted. The existing Qwen model was not unloaded.

### Why selection needed to change

The extractor creates both a food/fountain crop and a litter crop for each
source interval. This preserves useful alternative views but also creates many
irrelevant crops. A simple newest-first queue can therefore consume the person's
review time on repeated or empty views. A recent inventory contained 61 fountain
visits, 75 food-area visits and only one litter visit over the preceding four
days. Detection absence is not proof that the cat did not use the covered box.
Motion in the litter area provides a second discovery signal.

The new local selector combines overlap with area visits, area-specific motion,
cat observations and recency. Broad simultaneous changes in both areas receive
a penalty because lighting changes can imitate movement. Candidates need roughly
6–8 seconds of existing evidence and a named crop; no-signal clips are excluded.
Selection alternates between target areas, spaces clip starts by at least 12
seconds, and permits at most two per source group. If one area lacks useful
candidates, stronger candidates in the other area fill the shortfall. There is no
claim that these heuristics prove the behavior or produce 100 positive episodes.

The first selection experiment used a 20-second separation and only the top 300
metadata candidates per area. It produced **86** sufficiently diverse clips and
stopped locally, without any upload or charge. A wider shortlist, alternating
area selection, and 12-second separation produced a full candidate pool. An
intermediate 50/50 selection still contained litter views with no supporting
signal; those were excluded before freezing the outbound manifest. These are
selection experiments, not final cloud results.

### Keeping human decisions and evaluation honest

The newest recording days had been assigned to validation/test by the original
stable day partitioning. Showing Sol's answer and then calling the human's
acceptance an independent test label would be misleading. The companion therefore
uses an explicit audited transition: complete connected day/source/visit
components become training material before assisted labels are exposed. It
requires training to be off, no dataset/model artifacts, and no independently
reviewed labels in an affected component. It stores prior clip buckets and
partition assignments so the migration is inspectable. Other components remain
unchanged; fresh unseen days are still needed for blind evaluation.

The review API records `source=human`, `independent=false`, the assisting
model/campaign and the ordinary revision history. Accept, edit, skip and undo are
explicit user actions. Merely receiving a Sol response does not save a human
label. Existing production recording remains on its current image; the new
companion shares the learning database without starting camera or GPU workers.

### Spending, failures found in testing, and local preparation

The new batch reuses the original durable ledger and its $20 total authorization.
The ledger now checks the sum of conservative exposure across authorizations,
not a fresh $20 for each batch. Only Sol/medium is permitted by the new runner;
Astra is rejected. An unknown result keeps its full reservation and stops
further dispatch. The exact cropped-frame list, checksums, prompt, limits and
expiry are frozen before cloud calls.

Focused tests found an identifier accidentally left pointing to the previous
campaign in request inserts, and an ordering problem where one area's selection
could consume the other area's available groups. Both were corrected before any
new cloud request. **21 focused tests passed** after these fixes, covering old
accounting behavior, cross-campaign carry-over, duplicate-call prevention,
immutable manifests, grouping, audited partition changes, unsafe migration
rejection, local authorization, conflict handling, assisted provenance and undo.
A sandbox thread/event-loop restriction stalled HTTP TestClient startup; the
same fixture-only suite passed outside that restriction. No real footage or
provider calls are part of those tests.

Initial native frame preparation repeatedly sought through video compression
frames and was unnecessarily slow. Only the new preparation container was
stopped; a sequential decoder now reads each clip once and selects 32 distinct
native crop frames. Recording continues in its separate container. This change
improves evidence preparation speed, not model accuracy.

The detailed acquisition, review and deadline plan is maintained in
[care-labeling-sprint.md](care-labeling-sprint.md). Final selection, browser
validation, deployment, outbound approval outcome and costs will be appended
below once observed; they are not implied by the implementation work above.


### Final prepared batch, interface validation and approval boundary

The final frozen manifest contains **100 clips and 3,200 cropped frames**:
**68 fountain candidates and 32 litter candidates**, from **63 source groups**.
Dates are 15 clips on 4 November, 46 on 3 November, 34 on 2 November, two on
15 September and three on 14 September. Thus 95% are from the current recording
period. Durations range from approximately 5.96 to 8.00 seconds; there are no
0.3-second clips in this batch. A source group is not a confirmed positive episode.
The exact fingerprint is
`361d88afd5d08a2d332f679abc823c8b734858753a1978f62cf9e0c7113e39e0`.
The selected owned clips were pinned so review evidence is retained. No real
human review or original decision was changed.

The final focused suite passed **22 tests in 3.56 seconds**. The additional
sampler test compared every selected timestamp and cropped pixel array with the
existing decoder on synthetic video. Browser testing exposed a form-selector
error before deployment; fixing it enabled explicit edited acceptance, undo
and skip. A cropped poster now appears before video playback. Desktop/mobile
fixture acceptance passed, including no horizontal overflow and no JavaScript
errors. These synthetic checks establish interface behavior, not cat accuracy.

The separate review image is
`37c09115d0a1c7376c77ba2fa284eb9179abafc53ad0b99f98f077dce5e4710a`.
Its first Windows bridge-port mapping was reachable inside the container but not
from Windows. Automatic approval review rejected a proposed switch to host
networking because it would broaden the network boundary; that rejected command
was never executed. The implemented alternative preserves the bridge and its
loopback-only mapping, using an SSH forward bound only to Windows `127.0.0.1`.
The server's public host key is verified directly from the local WSL machine;
strict SSH host checking remains enabled. The connection has no OpenAI key and
cannot send a cloud batch. The helper is `scripts/open-care-review.ps1`; after a
workstation restart, the user can rerun it to reopen this local UI connection.
Only the newly created companion was replaced during UI fixes, never the recorder.

The review list was also changed from 100 separate database transactions to a
single bounded query, reducing contention with live extraction and labeling.
Its first local-only shortlist refresh completed successfully with 100 candidates.
This refresh creates no paid calls, no new cloud authorization and no human labels.

At **04:44:07 UTC**, native Windows Edge loaded all 100 cards, played the current
video, displayed the 510×489 crop, and passed the mobile-width and JavaScript
checks. No screenshots or private image contents were inspected by this native
check, and it submitted no decisions. At **04:44:10 UTC**, the recorder remained
connected/ready with continuous monitoring on and training off. Its image/start
identity was unchanged. Qwen still reported the pinned digest and all model bytes
in GPU memory. Human review count remained ten.

The requested cloud dispatch was **blocked before execution by automatic approval
review**. Its stated reason was that the 3,200 private crops and exact manifest
require explicit user approval, beyond the delegated request to choose 100 clips.
No workaround or indirect upload was attempted. The batch is concrete and
reviewable in the UI and private manifest, but **all 100 Sol results remain
pending, zero new API requests have been made, and zero new cost incurred**.
Consequently the audited assisted-pool reassignment is implemented/tested but
has not been applied to real source partitions. The next required action is
approval of this exact payload, Sol/medium, token-count requests, original $20
shared ceiling and no retries. The authorization is non-renewing and expires
24 hours after the manifest was frozen.

- [Prepared batch and validation summary](development-evidence/2026-11-04-care-campaign.json)
- [Native Windows review acceptance](development-evidence/2026-11-04-care-windows-ui.json)
- [Final recorder, training, cost and Qwen receipt](development-evidence/2026-11-04-care-live-status.json)
- [Acquisition and prototype milestones](care-labeling-sprint.md)

The remaining product work is human adjudication, sufficient independent
positive/negative episodes, blind evaluation on unseen days, memory-compatible
training while Qwen stays loaded, and tested summary/alert delivery. The roughly
15 November deadline does not turn proposal counts into validated accuracy.


## 18. 4 November 2026 — Execute the explicitly approved 100-clip Sol batch

### Approval and preflight

The user explicitly approved the exact 100-clip, 3,200-cropped-frame manifest,
fingerprint `361d88afd5d08a2d332f679abc823c8b734858753a1978f62cf9e0c7113e39e0`.
The approval covers Sol/medium labeling plus matching token-count requests,
the original shared $20 ceiling including prior exposure, no automatic retries
and no additional batches. This resolves the approval-review block recorded in
entry 17; it does not authorize another selection or an automatically renewed
budget.

At **08:18:16 UTC / 10:18 Asia/Jerusalem**, the camera was connected, detector
ready and continuous monitoring enabled. Training remained disabled. There were
**6,464 clips, 5,120 local suggestions and ten human reviews**, with 205,141
analyzed frames. At **08:18:55 UTC**, native-container preflight confirmed the
approved manifest, its unexpired limits, zero prior requests in this campaign,
and all **3,200 image checksums**. The original ledger still showed $2.019750
conservative exposure and $17.980250 remaining authorization.

The [explicit-approval receipt](development-evidence/2026-11-04-care-explicit-approval.json)
records this evidence without credentials or private image contents. The bounded
runner was started at approximately **08:19 UTC**. It uses the saved Windows
credential only through standard input. Each outbound attempt first acquires a
durable worst-case reservation; unresolved results retain their reservation and
stop further dispatch. Recording, the review service and Qwen are separate
processes and were not restarted for the run.

Sol's answers remain proposals. Human decisions are made only through the review
interface; no review is submitted by this execution. Final results, costs,
comparison to saved local proposals and live continuity checks follow below once
observed.


### Local-only accumulation and mid-run validation

While the fixed approved batch ran, the rolling selector was improved to exclude
its already-selected source groups. Without that exclusion, the next shortlist
could keep presenting examples already in the paid review queue. The change
preserves the immutable manifest and performs no API calls. A fixture explicitly
checks that selected IDs and related source groups do not return and that the
frozen manifest remains unchanged. The focused suite now has **23 passing tests
in 2.96 seconds**; the existing browser behavior was not changed.

The new review/refresh image is
`d5c14762724dc37bc8b645dc765e7d5395d9cc2772114f8981fdbbaeb66a5cb7`.
Only the companion was replaced. The running cloud job retains its original
`37c09115d0a1c7376c77ba2fa284eb9179abafc53ad0b99f98f077dce5e4710a`
image; recording and shared Qwen were not restarted. A native local refresh at
approximately **08:31 UTC** returned **36 additional candidates: 31 fountain,
five litter**, with zero source groups shared with the frozen batch. These are
unpaid, unconfirmed candidates for later review, not a new authorized cloud batch.

The [during-run receipt](development-evidence/2026-11-04-care-during-run.json)
recorded a connected camera, ready detector, continuous monitoring and suspended
training at **08:23:28 UTC**. Analyzed frames had advanced to 205,614, Qwen remained
fully resident, and the human-review count was still ten. Early Sol results were
mostly unclear/other/no-cat rather than positive care labels. That observation
is provisional until the complete batch and human review; it is not an accuracy
assessment.


### Completion, exact costs and useful disagreements

The first request was reserved at **08:19:40 UTC** and the final response arrived
at **08:39:35 UTC**. All **100 Sol/medium requests completed with valid annotations**.
Each clip also had its authorized token-count request. There were no invalid
outputs, unknown outcomes, retries or requests outside the fixed manifest.
The mean measured request duration was **11.289 seconds**, median **10.630**,
and maximum **22.236**. These include token-counting and generation work in this
setup and should not be presented as isolated model inference benchmarks.

The saved usage contains **980,996 input tokens**, including **980,696 cache-write
tokens**, zero cache-read tokens, and **29,150 output tokens**, of which **12,815
were reasoning tokens**. Reasoning is already included in the output total.
The estimator applies the documented 30-minute cache-write default where no
lifetime breakdown is returned. A separate decimal calculation verified every
request's inference estimate and conservative accounted amount from saved usage.

| Scope | Estimated inference USD | Conservative exposure USD |
| --- | ---: | ---: |
| This 100-clip Sol batch | 2.743841 | 10.101460 |
| Prior 3 November Sol/Astra experiment | 0.681330 | 2.019750 |
| Both authorized batches | **3.425171** | **12.121210** |

Remaining authorization is **$7.878790**, using the conservative measure. The
unused allowance is not an instruction to start another batch. These numbers
are usage-based estimates, not a provider invoice or an account-balance check.
A private per-request CSV preserves input/cache/output/reasoning counts, estimates,
conservative amounts and provider response identifiers. No credential is logged.

Across all 100 new Sol outputs, **71 clips contain unclear intervals**, 46 contain
other activity, 24 contain no-cat intervals, one contains an eating proposal and
one a litter-activity proposal. **None contains a drinking proposal.** A clip can
contain multiple intervals, so these counts intentionally overlap. They describe
model output, not verified cat behavior. They show that sending 100 candidate
clips did not create 100 positive care examples.

Saved Qwen proposals existed for 80 of these clips. The paired comparison uses
exactly those same 80 clips, avoiding a misleading comparison of unequal cohorts:

| Coarse proposed label | Sol on paired 80 | Qwen on paired 80 |
| --- | ---: | ---: |
| Drinking | 0 | 0 |
| Litter activity | 1 | 7 |
| Eating | 1 | 50 |
| Other activity | 39 | 8 |
| No cat | 23 | 22 |
| Unclear | 53 | 0 |

The models have the same set of coarse labels on **20/80** paired clips. The
saved Qwen proposals used earlier sampling conditions rather than the new
32-frame Sol protocol, and there is no independent human reference in this
cohort. Therefore neither the disagreement nor Sol's greater abstention proves
which model is correct. The practical next experiment is human adjudication:
check whether care actions are visibly established, whether Qwen over-labels
nearby cats, and whether Sol is over-abstaining or the view lacks sufficient
information.

A private **ten-decision starting list** selects five fountain and five litter
clips from distinct source groups, favoring care proposals and unclear cases
with cat evidence. Each links directly to the local review page. All 100 remain
available. The agent submitted no acceptance, correction or skip on the user's
behalf. The human must decide what can enter training.

### Dataset separation and final live checks

At **08:19:34 UTC**, the audited assisted-pool transition covered **4,564 related
clips and 4,725 partition keys** across the five selected recording days. Before
the transition, 1,004 clips were already in training, 1,686 were validation and
1,874 were test. Complete day/source components were reassigned to training-only
material so answers exposed to Sol cannot later masquerade as independent
validation. Prior assignments are preserved in the private audit. No independently
reviewed labels, existing datasets or trained models were present in affected
components. Other days remain available for genuinely blind evaluation.

At **08:39:59 UTC**, completion verification found all 100 requests settled and
independently reconciled, zero human reviews of the selected cohort, ten human
reviews overall, and zero dataset/model artifacts. During the run, **244 recording
segments** were registered; all corresponding files existed. The largest internal
timestamp gap was **0.329 seconds**, with the most recent completed segment about
4.86 seconds old at the check. This is bounded continuity evidence, not a claim
of perfect camera or network capture.

At **08:40:02 UTC**, native Windows Edge showed **100 Sol proposals ready**,
played the local clip, and passed the mobile-layout and JavaScript checks.
The camera remained connected, the detector ready and training disabled. The
frame counter had advanced to **207,061**. Qwen retained the same pinned digest,
16K context and all model bytes in GPU memory. The recorder kept its original
image/start identity. The earlier pre-approval browser receipt was preserved
separately from this later check; its reused filename was restored from the
exact earlier recorded output with an explicit restoration note.

- [Completion, cost reconciliation, partition and segment evidence](development-evidence/2026-11-04-care-completion.json)
- [Aggregate model comparison and token totals](development-evidence/2026-11-04-care-analysis.json)
- [After-run service/GPU status](development-evidence/2026-11-04-care-after-run.json)
- [After-run native Windows review check](development-evidence/2026-11-04-care-after-run-windows-ui.json)

Reproduction used `scripts/run-care-campaign.ps1 -Stage Cloud` once after explicit
approval. `scripts/summarize-care-campaign.py outputs/care-campaign` reads saved
outputs offline and creates the analysis, review-start list and cost CSV without
model calls. Private outputs are under `outputs/care-campaign/`; they are not
publication artifacts. The next milestone is the person's review of difficult
care/unclear examples, followed by visibility and acquisition improvements if
those examples cannot be reliably labeled. Training stays suspended.

## 19. 4 November 2026 — investigating the fountain more closely

### The question and the limits of the current evidence

The owner asked for the 100 most promising activities in and near the drinking
fountain after the earlier Sol batch returned no drinking proposals. The owner
also reported regular evidence of urination in the litter box. That report is
useful context; it is not a newly adjudicated label for any particular clip, and
neither observation identifies where the cat obtains water. This experiment is
intended to establish what the fountain footage actually shows. Zero drinking
proposals in the previous sample does not establish that the fountain is unused.

The earlier selector was designed to balance two care areas. This investigation
uses a dedicated fountain selector and closer views while retaining context. It
cannot reveal activity outside the camera's field of view. The resulting labels
must still distinguish visible drinking from proximity, sniffing, passing and
occluded activity. Unclear remains a useful answer.

### Selection: a broader search with less duplicate evidence

The new `catwatch/learning/fountain.py` searches the full eligible archive rather
than taking a pre-truncated top-600 shortlist. It combines fountain cat detections,
water-specific area evidence, recorded visit overlap, nearby cat centers, motion
and recency. Broad lighting changes are penalized. Clips need available owned
video and a saved source hash, and their duration is approximately six to eight
seconds. A cat detection or a motion score is a selection signal, not a care label.

Previously uploaded fountain time windows and clip identities are excluded using
all earlier cloud authorizations in the shared ledger. The selector can consider
an unused, non-overlapping part of a longer source group; excluding an entire
long recording would discard potentially useful evidence. It first favors one
sample per candidate visit/group, caps samples at two per visit/source group,
and requires starts to be at least 12 seconds apart.

The eligible pool contained **949 candidates**. The frozen selection has **100
clips, 100 candidate visit/group keys and 85 source groups**; these are not claims
of 100 independent true drinking episodes. **99 clips have recorded fountain cat
detections.** Recency was favored, but useful archive material filled gaps:

| Recording date | Selected clips |
| --- | ---: |
| 4 November | 17 |
| 3 November | 37 |
| 2 November | 23 |
| September archive, seven dates | 23 |

Thus **77/100 are from 2–4 November**. All previously uploaded fountain intervals
were checked again against the frozen selection: **zero overlaps**. This is the
best available ranked sample under these signals and diversity constraints,
not a promise that all 100 show informative or positive behavior.

### Evidence protocol and fixed spending limits

The manifest was frozen at **10:27:01 UTC / 12:27:01 Asia/Jerusalem** under
`2026-11-04-fountain-100`, fingerprint
`900e180e988c5a13d1fe59e00f86d9e7b32c62c893bbb25e0f60a20af91fd4e4`.
Each clip supplies 32 native **277 × 343** fountain closeups and two native
**510 × 489** context images, totaling **3,400 JPEG crops**. The context images
repeat the first and last sampled moments: there are 32 distinct timestamps,
not 34 independent moments. The fountain bounds come from each clip's saved
calibration, include a 20% surrounding margin, and stay inside its original
privacy crop. Images are not enlarged. No audio or full camera images are included.

The frozen prompt explains the views and asks Sol to distinguish visible lapping
from nearby food-area activity and uncertainty. Existing Qwen proposals used
other sampling conditions, so a later comparison will be diagnostic disagreement,
not a controlled accuracy benchmark. The exact clip/frame list and hashes are
private review artifacts under `outputs/fountain-campaign/`.

A native preflight at **10:33:08 UTC** verified every image hash, the 32 distinct
closeup timestamps per clip, zero earlier-upload overlap and zero requests for
this new authorization. The protocol keeps **Sol/medium** but lowers the frozen
caps to **6,000 input and 1,536 output tokens per clip**. The earlier completed
100-clip experiment's largest output was 694 tokens; that observation informed
the cap but does not guarantee that every new answer will fit. Input suitability
has not been established by a paid token-count call yet.

The maximum conservative reservation per clip is $0.075360: both the counting
and generation input allowances use the existing maximum input rate, and output
uses the pinned output rate. One hundred reservations therefore total **$7.536**.
Adding the existing **$12.121210** accounted exposure gives **$19.657210**, within
the original **$20** ceiling. If token counting exceeds 6,000, generation does
not proceed; the reservation is retained and dispatch stops. Unknown outcomes
also retain reservations. There are no automatic retries, replacement images or
additional batches. The shared ceiling has not been reset.

The common comparison code now accepts only lower caps in an immutable manifest;
prices, model identities and reasoning policy remain pinned. The ledger also
checks the frozen dispatch-model list, so even a caller with a broader default
allowlist cannot reserve Astra against this Sol-only authorization. These controls
were tested without uploading footage or using an API credential.

### Review interface, tests and service continuity

The companion now offers a batch selector. The completed care queue remains
available, while `http://localhost:8767/?campaign=2026-11-04-fountain-100` displays
the 100 pending fountain clips. The context video marks the closeup boundary and
explains what Sol would receive. API reads and writes check membership in the
selected batch. A stale clip load cannot overwrite a later selection, and switching
batches while saving is prevented. No human decision was submitted by the agent.
The local refresh excludes source groups from all frozen campaign manifests.

The focused suite passed **30 tests in 2.77 seconds**, covering shared spending,
frozen model/cap enforcement, stopping before over-limit generation, privacy
bounds, candidate diversity and scoped review decisions. The synthetic browser
exercise also passed playback, accept/edit/undo/skip, provenance, and desktop/mobile
checks. These fixtures demonstrate software behavior, not real cat accuracy.

Native Windows Edge checked the deployed interface at **10:32:26 UTC**: both
batches were available, the new queue contained 100 pending clips, video played,
the closeup explanation appeared, the completed queue retained 100 proposals,
and mobile layout and JavaScript checks passed. No screenshots or private-image
interpretation were used for that UI check, and no labels were changed.

The deployed review companion uses image
`f8c54caca938187e5094a218e447273c881c7340696a596b461ede62b2266316`.
The final fountain runner, including the additional ledger model-scope guard,
was built locally with networking disabled as
`d0e2dcef6d47f67b2de0bbc8273524a8d0d38090bd3e84333068a3553f9a11d8`.
The guard does not change the frozen payload or fingerprint. The runner is built,
not running a cloud batch; the review service has no cloud dispatch endpoint.

At **10:32:27 UTC**, the camera was connected, detector ready and continuous
recording enabled: **216,776 analyzed frames, 6,814 clips, 5,411 local suggestions
and ten human reviews**. Training was still disabled. Qwen retained digest
`6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`,
16K context and all 5,763,005,151 reported model bytes in GPU memory. The recorder
retained its 0.5.3 image and **2 November, 20:15 UTC** start. Only the review
companion was replaced during this work; the recorder and Qwen were not restarted.
No new assisted-pool migration has occurred for the fountain batch.

### Approval boundary and next step

After preparation, automatic approval review **rejected the proposed Cloud-stage
execution before it ran**. Its stated reason was that the new 3,400 private crops
and associated spending need approval of this exact manifest; the earlier explicit
approval covered the completed batch. The general request for 100 fountain
activities was not accepted by that review as exact-payload approval. This is an
operational approval block, not a model or API failure. No workaround or retry was
attempted. **No new images have been sent and no new cost has been incurred.**

The next step is approval of the concrete manifest above. Only then may the
one-shot native runner count tokens and request labels. The user can already
inspect all clips locally. After dispatch, the work remaining is reconciliation
of real usage, comparison with saved Qwen proposals, and presentation for human
acceptance. Training remains suspended throughout this stage.

- [Frozen-manifest preflight](development-evidence/2026-11-04-fountain-preflight.json)
- [Native Windows interface check](development-evidence/2026-11-04-fountain-windows-ui.json)
- [Recording, local-labeling and GPU status](development-evidence/2026-11-04-fountain-preparation-status.json)
- [Sprint plan and review requirements](care-labeling-sprint.md)

Reproducible local commands are `scripts/run-fountain-campaign.ps1 -Stage Scan`,
`-Stage Prepare`, and `-Stage Report`. Preparation freezes the manifest and must
not be used to silently replace an approved payload. `-Stage Cloud` is reserved
for the exact approved batch. The shared review companion and its Windows
loopback tunnel continue to use the existing care-review launch commands.

### Exact approval received and dispatch preparation

At 2026-11-04T10:44:28.644167+00:00 (UTC), the user's explicit approval of this exact batch for
processing was recorded. This resolves the earlier automatic approval block for manifest
`900e180e988c5a13d1fe59e00f86d9e7b32c62c893bbb25e0f60a20af91fd4e4`.
The authorization retains Sol/medium, 3,400 crops, the fixed token limits,
$7.536 maximum additional conservative exposure, the shared $20 ceiling and
no retries or additional batches. A fresh native preflight is checking the
unchanged frozen payload before dispatch. Approval does not accept any labels
or resume training. Actual dispatch and outcomes will be recorded below.

### Dispatch started; early visibility findings

The approved preflight completed at **10:44:47 UTC** with the same fingerprint,
all 3,400 image hashes and zero prior requests for this authorization. The native
runner then started once. The Windows credential was decrypted transiently and
passed on standard input; it was not exposed in arguments, image metadata or logs.
No retry, additional batch or model substitution was enabled.

At **10:45:22 UTC**, live recording remained connected and the detector ready;
217,791 frames had been analyzed, with 6,864 saved clips, 5,461 local suggestions
and ten human reviews. Training was disabled, Qwen remained entirely GPU resident,
and the recorder image/start identity was unchanged. The first two cloud requests
were visible in the shared ledger (one completed and one reserved/in progress).

At **10:46:40 UTC**, the first ten responses were valid. Their estimated inference
cost was **$0.153232**. All ten included an unclear interval, and one also included
moving. Early explanations repeatedly cited an obscured muzzle/contact point.
This is a preliminary model observation about the supplied views, not a human
verdict that drinking is absent. The full fixed batch continues; final outcomes,
account reconciliation and human-review priorities will follow.

- [Approved payload re-verification](development-evidence/2026-11-04-fountain-approved-preflight.json)
- [Dispatch-time recording, GPU and queue status](development-evidence/2026-11-04-fountain-dispatch-status.json)

### Fountain batch completed: outcomes, uncertainty and comparison

The first request was reserved at **10:45:07 UTC / 12:45:07 Asia/Jerusalem**;
the final response arrived at **11:03:09 UTC / 13:03:09 local time**. The single
native run processed all **100 Sol/medium requests and their matching token-count
requests** against the approved fingerprint. **97 responses became valid proposals;
three failed local annotation validation.** There were no retries, additional
batches, unknown outcomes or unprocessed clips. The runner exited normally.

The three failures were provider-completed responses with 459, 466 and 527 output
tokens, well below the 1,536-token cap. They were rejected during local annotation
parsing/normalization. The saved failure record preserves usage and a validation
status, but not the precise rejected text or validation exception, so the exact
annotation defect cannot be reconstructed from this ledger. It would be wrong to
attribute these failures to output truncation. The clips remain available for
manual review or skipping; a missing proposal is not a negative behavior label.
More detailed bounded validation diagnostics are a future improvement, not a change
made to this completed request protocol.

The input count for every request was between **5,364 and 5,369 tokens**, below
the 6,000 cap. The largest output was **679 tokens**. This verifies that the
frozen native-closeup protocol fit its budget on the real API; it does not verify
that the camera or sampled frames capture enough detail to classify drinking.
Mean measured request time was **10.050 seconds**, median **9.625**, maximum
**17.569**. These durations include counting and generation, not isolated inference.

Among the **97 valid proposals**, there were **zero drinking or eating labels**.
**96 clips included unclear**, 30 included stationary, 19 moving, four no-cat,
and one sniffing/inspection. A clip can contain several intervals, so these
counts overlap. Uncertainty explanations often refer to an obscured muzzle or
contact point. Human review of the full local video is still needed: model
abstention is not proof that drinking did not occur, and this camera cannot
identify water sources elsewhere in the home.

Saved Qwen proposals existed for **84 of these same 97 clips**:

| Coarse proposed label | Sol on paired 84 | Saved Qwen on paired 84 |
| --- | ---: | ---: |
| Drinking | 0 | 0 |
| Eating | 0 | 78 |
| Other visible activity | 35 | 18 |
| No cat | 3 | 1 |
| Unclear | 83 | 0 |

Only **1/84** paired clips had the same coarse label set. Qwen used earlier
sampling/prompt conditions and Sol received the approved closeups plus context;
there is no independent human reference in this cohort. This is a useful review
question—does the video establish eating, another action, or only an obscured
head near the objects?—rather than an accuracy ranking. Neither model proposed
drinking on the paired subset.

The offline report now selects an initial **ten questions across ten recording
days and ten source groups**, favoring recorded cat evidence and uncertain or
care-related decisions. This avoids making the first review session ten adjacent
moments from a similar recent scene. The three invalid-response clips are listed
separately for manual review. The report and all 13 direct links were checked to
use the fountain campaign; all 100 clips remain available in the companion.
No human acceptance, correction or skip was performed by the agent.

### Final cost reconciliation and dataset separation

An independent decimal calculation reconciled **all 100 usage records**, including
the three invalid annotations. Totals were **536,661 input tokens**, including
536,361 cache-write tokens, zero cache-read tokens, and **27,622 output tokens**,
including **11,872 reasoning tokens**. Reasoning is already included in output.
The unchanged estimator uses the documented 30-minute cache-write default when
the provider does not return a lifetime split. Matching token-count requests
reported 536,661 input tokens; conservative exposure retains their allowance.

| Scope | Estimated inference USD | Conservative accounted exposure USD |
| --- | ---: | ---: |
| This fountain batch | **1.617770** | **5.642830** |
| Both previously completed batches | 3.425171 | 12.121210 |
| All three approved batches | **5.042941** | **17.764040** |

Remaining authorization is **$2.235960** under the original $20 ceiling. The new
batch remained below its $7.536 maximum reservation total. There is no unresolved
reservation and no authorization for another batch. These figures are saved-usage
estimates and conservative accounting, not an invoice or a live account balance.
The private CSV records each request's counts, cost estimate and response identity.

At **10:45:04 UTC**, before inference, the audited assisted-data transition covered
**5,106 related clips and 5,405 partition keys across ten recording days**. Most
were already training-only: 4,978 were train, 100 validation and 28 test beforehand.
Complete related components were assigned to the assisted training pool; previous
assignments remain in the audit. The guard required training to be off, no existing
dataset/model artifacts, and no independent reviewed labels in affected components.
This prevents exposed answers and related footage from later being represented as
blind evaluation. It does not train a model or accept a label. Unseen future days
are still needed for independent evaluation.

### Native acceptance and an audit-path correction

The first completion audit found 217 registered recording segments but reported
zero existing files. Inspection showed an **audit-script path bug**, not demonstrated
recording loss: the segment database stores paths relative to the application's
`/data` root, while the new checker resolved them against its working directory.
The checker was corrected to use the same root as the application. Its initial
receipt was retained privately as `initial-audit-path-resolution-error.json`.
The corrected audit at **11:04:29 UTC** verified **217/217 segment files existed**
for the dispatch interval, with a maximum internal timestamp gap of **0.329 seconds**.
This is a bounded continuity check, not a guarantee that every camera frame arrived.

At **11:03:34 UTC**, native Windows Edge displayed **97 Sol proposals ready**,
played the fountain video and passed mobile layout and JavaScript checks. The
earlier completed batch was also available. The test used no screenshots and
submitted no review decisions. At the same time, the camera was connected and
detector ready, training was disabled, and counters had advanced to **219,228
frames, 6,946 clips and 5,536 local suggestions**. Human reviews remained ten
across the project and zero in the fountain batch. Dataset and model counts
were both zero.

Qwen retained its pinned digest, 16K context and all **5,763,005,151 bytes** in GPU
memory. The recorder retained its exact image and 2 November start identity;
neither it nor Qwen was restarted during dispatch. The review service remains
separate from the stopped one-shot cloud runner.

- [Final request reconciliation, partition audit and recording-file check](development-evidence/2026-11-04-fountain-completion.json)
- [Aggregate model comparison and token totals](development-evidence/2026-11-04-fountain-analysis.json)
- [After-run recording, local labeling and GPU status](development-evidence/2026-11-04-fountain-after-run-status.json)
- [After-run native Windows review check](development-evidence/2026-11-04-fountain-after-run-windows-ui.json)

Reproduction used `scripts/run-fountain-campaign.ps1 -Stage Cloud` once after the
exact approval. `scripts/audit-fountain-campaign.py` runs locally inside the native
review container to reconcile saved requests and segments; it makes no API calls.
`scripts/summarize-care-campaign.py outputs/fountain-campaign` creates the private
comparison, per-request CSV and review starter offline. The next useful step is
human adjudication of visibility and model disagreements, not automatic training
or another cloud batch. Training remains suspended.

## 20. Pausing the project for redesign — 8 November 2026

The user requested that running activities stop while the project's design is
reconsidered. This was an operational pause, with existing footage, databases,
model proposals, human reviews, campaign manifests and cost records retained.
The last journal entry described continuous recording and local labeling on
4 November, so live deployment state was checked rather than assuming that the
older checkpoint still described the workstation.

### Live scope and durable pause

The Windows Podman connection `podman-machine-default-root` had two running
project containers: `cat-watch` with the existing 0.5.3 image
`540a4e088dd95c017766509195324f951e88e0c611048e9fd4a6fce291d5610f`,
and `cat-watch-care-review` with image
`f8c54caca938187e5094a218e447273c881c7340696a596b461ede62b2266316`.
The recorder reported a connected camera, a ready detector and 656,953 analyzed
frames at the initial live check. The review companion also runs a local
shortlist refresh thread, so stopping only the recorder would have left project
work active. No cloud batch runner or legacy analysis controller was found.

The supported authenticated application APIs disabled learning and training and
stopped continuous monitoring: `PUT /api/learning/settings` with
`enabled=false, training=false`, followed by `POST /api/monitoring/stop`.
The session token stayed in process memory and was not recorded. After allowing
seven seconds for the configured post-roll, a status GET timed out. The pause
settings were subsequently verified directly in the learning database using
read-only access: `enabled=false`, `continuous=false`, `training=false` and
`pause_training=true`. Telegram was already disabled and remained so.

The existing launcher was not used for this pause because its `Stop` action
also removes the container. Instead, exact container identities were verified
and the existing instances were stopped without removing them or their storage.
The three cat-watch Codex automations were all already `PAUSED`; no automation
change was needed. No Windows task was found that starts project capture or
campaign work. The separately documented shared Qwen service serves other local
agents and was deliberately retained, including its existing startup task.

### Shutdown outcome and a remaining integrity check

The bounded stop was requested at **03:33:10 UTC**. The review companion exited
normally with code 0 at **03:33:11 UTC**. The recorder did not exit during the
60-second graceful interval; Podman terminated it, and it exited with code 137
at **03:34:11 UTC**. The stop operation returned at **03:34:12 UTC**. The recorder
retains restart policy `no`; the review companion retains `unless-stopped` and
was explicitly stopped. Container identities, images and persistent data remain
available for a later deliberate restart.

A shutdown-script attempt initially stopped before the Podman action because
PowerShell 5.1 nested the parsed inspection array, causing the identity guard to
reject an unchanged pair of IDs. The guard was corrected to use the parsed array
directly, and both IDs were rechecked before the successful stop. The preceding
API status timeout and this local orchestration error are recorded as failures,
not hidden by the final successful stop.

At **03:34:47–03:34:48 UTC**, independent checks found no running project
containers, host workers, listeners on ports 8765/8766/8767, or project-specific
Windows scheduled tasks. The learning database remained readable and reported
**14,442 clips, 11,581 suggestions and 11 reviewed clips**. These are saved
inventory counts; no labels were accepted or revised during the pause.

The archive database is 3,171,119,104 bytes and retains a 12,824-byte rollback
journal. Both during shutdown and after exit, opening it with SQLite `mode=ro`
and `PRAGMA query_only=ON` returned `attempt to write a readonly database`.
This is consistent with a required journal recovery, but it does not establish
corruption or establish integrity. The original database and its journal were
left intact; no journal was deleted and no repair was attempted. Before capture
is resumed, preserve a consistent copy of the stopped database and journal,
check recovery/integrity, and inspect the final recording segment. That is
remaining restart work, not a reason to keep recording during the redesign.

### Evidence and validation boundary

[The sanitized shutdown receipt](development-evidence/2026-11-08-redesign-pause.json)
contains exact container identities, exit states, UTC request/verification times,
saved pause settings and the empty runtime checks. Local operation scripts and
raw receipts are retained under `outputs/redesign-pause-20261108/`. Useful
read-only verification is Windows Podman
`--connection podman-machine-default-root ps --filter name=cat-watch`, followed
by inspecting the two retained containers' states. Shared Qwen's health endpoint
still reported the pinned GPU-resident model; stopping cat-watch did not stop
the workstation's shared model service.

No application code was changed and no synthetic, GPU-accuracy or behavior
accuracy test was run. This entry establishes that project activity stopped and
records the shutdown limitation; it does not establish archive integrity,
complete final-segment coverage or a new accuracy result. The next project step
is the user's redesign, with recording remaining off.

## 21. RHEL restart and a stale Task Manager CPU reading — 8 November 2026

After pausing cat-watch, the user saw 45% total CPU and roughly 51 GB of memory
in Windows Task Manager. The supplied screenshot attributed 40.4% CPU to
`VmmemWSL`. Read-only inspection of all four Podman stores found only the shared
Qwen runtime running in the RHEL user's store; both stores in the separate
Windows Podman machine and the RHEL root store had no running containers.
RHEL also ran Kubernetes/RKE2 system services outside Podman. These were
workstation dependencies, not evidence that cat-watch had resumed.

### The requested RHEL restart

The user explicitly requested restarting RHEL. RKE2 and both shared-Qwen user
units were stopped cleanly first. A detached native Windows PowerShell runner
then terminated only `RHEL10` at **03:47:29 UTC**, started it again and confirmed
startup by **03:47:41 UTC**. The systemd userspace start changed from
2 November to **8 November, 05:47:31 Asia/Jerusalem / 03:47:31 UTC**. The separate
Podman machine was left running and its cat-watch containers stayed stopped.

The runner recorded Cockpit HTTP 200 and both Qwen units active. Its final
03:49 checkpoint still had RKE2 in `activating`, so the runner's `completed`
label was not treated as proof that every service was ready. A subsequent live
check at **03:55:26 UTC** verified RKE2, the Cockpit socket and both Qwen units
were all active. No archive-database recovery or new recording was performed.

### Establishing whether 45% was real load

The user reported that Task Manager still showed the same 45% after the RHEL
restart and that its real-time update setting was not Paused. Earlier ordinary
Windows and Linux counter readings were useful clues but were not sufficient
by themselves to establish physical CPU usage under virtualization. Microsoft
recommends the Hyper-V Hypervisor Logical Processor counters for that purpose:
[Hyper-V CPU statistics](https://learn.microsoft.com/en-us/windows-server/administration/performance-tuning/role/hyper-v-server/configuration#cpu-statistics).

Ten two-second Windows samples at **03:52:38–03:52:56 UTC** measured physical
CPU activity of **11.53–18.77%, averaging 14.06%**. Guest virtual-processor
activity averaged **3.19%**. A separate 20-second Linux sample measured **3.236%**
CPU activity across its 28 logical processors. A later eight-sample Windows
check averaged **13.82% physical CPU** and **3.17% guest virtual-processor
activity**. These are different scopes and denominators; they should not be
added. All were inconsistent with a current, unchanging 45% total reading.

The Windows UI helper could not connect from this WSL workspace, returning
`sandboxCwd is not a local file URI`, so no automated Task Manager interaction
was claimed. The user closed and reopened Task Manager and reported that its
value now changed and was lower. Native process inspection independently
confirmed a new Task Manager process, PID 39100, started at **03:54:47 UTC**,
replacing the earlier PID 12364. This establishes that the persistent display
was stale and that reopening the monitor resolved the visible discrepancy.
It does not establish the internal cause or a particular Microsoft defect ID.
The installed build's official release notes did not identify this exact symptom.

The follow-up Windows memory reading was **38.08 GiB**. This is a point-in-time
post-restart observation, not proof that every reclaimed byte belonged to a
particular app. No updates, counter rebuilds, registry changes, model unloads
or additional service restarts were used to address the Task Manager display.

[Restart and CPU diagnostic evidence](development-evidence/2026-11-08-rhel-restart-cpu.json)
preserves the restart timestamps, readiness limitation, counter series and
explicitly attributed user observations. The cat-watch pause and the archive
integrity check required before its future restart remain unchanged.

## 22. Reopening camera-area setup after a background change — 8 November 2026

The user reported placing white paper behind the drinking fountain and proposed
two possible reasons for missed drinking: poor contrast against the former dark
background and a fountain area that included too much of the scene. They asked
to open the app so they could redraw the areas themselves. This authorized a
camera preview and calibration setup; it did not resume the paused monitoring
or learning campaign. Neither proposed cause has yet been established by a
behavior-accuracy comparison.

### Restoring the existing app safely

The initial Windows Podman connection was refused. Machine inspection showed
that the existing `podman-machine-default` was stopped. Starting that existing
machine restored the connection; the project containers remained exited.
No machine was provisioned, image rebuilt or container replaced.

The earlier forced shutdown had left the archive database with a rollback
journal. Before reopening it, both stopped files were copied to a separate
Windows backup directory, and another copy was made for recovery testing.
The archive was **3,171,119,104 bytes** and its journal **12,824 bytes**. SQLite
recovered the test copy automatically; its full `PRAGMA integrity_check`
returned **`ok` at 04:04:24 UTC**. The copy showed that investigation 11 had
already stopped and that no legacy analysis kind was admitted. A read-only
check of the learning database confirmed all pause settings, including
`pause_training=true`. The first local check command used an unavailable
`python` executable; rerunning it with the installed `python3` succeeded.

The maintained deployment launcher was invoked with `-Action Resume` and
without `-LegacyAnalysis`. This reused the retained container and avoided the
older skill helper's unconditional analysis-controller launch. The distinction
matters because opening the area editor should not restart deferred analysis.
Camera credentials passed through the launcher's existing protected mechanism;
no credentials were included in the receipts or journal.

### Preview and handoff

After startup, `POST /api/calibration/preview` enabled setup preview and
`POST /api/calibration/prepare` froze a fresh reference image. At
**04:04:45 UTC / 06:04:45 Asia/Jerusalem**, the receipt reported a
**2560 × 1440** source, camera `preview`, preparation enabled and a frame age
of **1.0 second** at the health sample. The detector was stopped, no live model
was loaded, capture was idle and zero frames had been analyzed. The new draft
was unconfirmed. Existing polygons were retained for the user to edit.

Live learning settings still had automatic labeling, continuous monitoring,
training and Telegram disabled. Inventory counts remained **14,442 clips,
11,581 suggestions and 11 reviewed clips**. These unchanged counts and the
preview health establish the bounded setup state, not long-term inactivity or
recognition accuracy. The storage report was empty because this preview did
not run the recording reserve check; recording capacity was not asserted.

The Codex browser was asked to open `http://127.0.0.1:8765/#setup`. Its result
was `queued`, so this entry does not claim a visually verified browser tab.
The user can select an area, clear its old outline, click at least three new
boundary points, and save with **Save areas & confirm masks**. The agent did
not draw, save or confirm an area, start recording, submit review decisions,
run cloud analysis or change the prior automation pause.

[Sanitized setup evidence](development-evidence/2026-11-08-area-setup.json)
contains the recovery result and live health. Reproduction receipts and the
bounded launcher are under `outputs/area-setup-20261108/`; the raw database
backup is outside the live application directory. No application source was
changed and no synthetic or model-accuracy tests were run. Full integrity of
the live original and the final recording segment were not separately tested;
those remain relevant before recording resumes. The next evidence-producing
step is the user's revised calibration, followed by explicitly started capture
and human-reviewed examples under the new scene conditions.

## 23. A clean collection with smaller areas and white fountain backing — 8 November 2026

The user saved new areas and explicitly requested continuous monitoring with
training still paused, all old data archived, and a blank collection. They also
asked that the white background behind the fountain be noted as a possible
classification improvement. This was a deliberate collection boundary: old
examples and model suggestions should remain recoverable without appearing in
the new activity and decision lists.

### Checking the user's fountain definition

The saved calibration was confirmed by the user, and an isolated native Windows
Edge session rendered the actual editor without changing any points. Both the
source image and the editor showed the white paper behind the fountain. The
new blue polygon concentrates on the upper fountain and drinking position;
it does not enclose the whole body of a cat approaching from the floor.
This distinction matters because area-triggered motion must remain independent
of a large detected-cat box overlapping the small polygon.

The fountain polygon changed from **0.7937% to 0.4226% of the camera frame**,
approximately a **47% reduction**. Its bounding rectangle is approximately
169 × 138 native pixels. Eating and litter polygons also became smaller.
The exact user-confirmed coordinates, masks and image were preserved. The
reference-image SHA-256 was verified across the transfer; confirmation was
carried over as the user's existing decision, not submitted anew by the agent.

The existing capture settings use separate buffered motion measurements for
each area, a 20% trigger buffer per side, a 0.05% changed-area threshold and
0.5-second confirmation at 5 Hz. These are motion thresholds, not a guarantee
that every subtle or very brief behavior will receive a classification clip.
Continuous native-source video provides the underlying record, within the
configured retention limits. Motion and visit evidence supply short windows
with five-second context, even when cat detection fails.

The classifier still uses 50% crop context per side. The overlapping eating and
fountain contexts merge into a **426 × 402** crop; the litter context is
**364 × 314**. Smaller polygons therefore narrow the source context, but they
do not create fully separate food and fountain classifier inputs. No crop or
model code was changed in this operation. The visual scene change was recorded
as collection metadata without asserting drinking or altering label semantics.

### Archiving without deleting history

An empty staging directory was initialized using the exact deployed image
`540a4e088dd95c017766509195324f951e88e0c611048e9fd4a6fce291d5610f`
(the existing 0.5.3 build). Only operating preferences, the user's confirmed
calibration and scene-change metadata were transferred. Training was disabled
before any app worker could start, and its durable pause metadata was true.
No old clips, model proposals, decisions, trained models or cloud approvals
were copied into the new databases.

The previous app stopped cleanly, exit code **0**, between **04:20:44 and
04:20:45 UTC**. Its full application directory and the separate prepared dataset
were moved on the same Windows volume into
`C:\Alex\data\tapo-cat-monitor\collection-archives\20261108T042043Z-before-white-background`.
The old dataset was removed from the new app's mount list by archiving it as
well; otherwise the startup import would have silently repopulated the fresh
learning database.

The archive contains **32,043 application files / 34,817,344,835 bytes** and
**635 prepared-dataset files / 417,706,643 bytes**. Relative paths, lengths and
UTC modification times were compared before and after both directory moves.
These were renames within one volume, not a lossy export or a media rewrite.
The prior container was retained stopped as
`cat-watch-archived-20261108t042043z`; the new container uses the same image.
The archive README explains that the retained container's original bind paths
must not be mistaken for an independently configured archive viewer.

The old databases retain **11 investigations, 651 motion groups, 17 group
reviews, 14,442 learning clips, 11,581 saved suggestions and 11 timed reviews**.
Existing older backups and project history remain preserved. The new app's
pre-capture check at **04:22:55 UTC** confirmed zero investigations, clips,
suggestions and reviews and no mounted prepared dataset.

### Failures caught during the handoff

The initial staging assertion expected three explicit zero counters, while an
empty learning store returns an empty counts object. Normalizing missing
counters to zero corrected that check before any live data was moved.
After the directory moves, a PowerShell summary failed because dictionary
entries were not exposed as properties to `Measure-Object`. The handoff paused
with the old app stopped and both archived directories intact.

The continuation then encountered PowerShell 5.1 array nesting while comparing
parsed inventories. Independent comparison confirmed **32,043 unchanged
application entries and zero differences**. The summary used ordinary objects,
and parsed arrays were assigned directly before the guarded continuation.
Both complete inventories were rechecked before startup. These orchestration
errors did not delete data or cause monitoring to run against the archive.

### Native recording, local classification and the training pause

The authorized monitoring start created new investigation **1 at 04:23:34 UTC /
06:23:34 Asia/Jerusalem**. Local labeling was enabled with training explicitly
false. The existing pinned **Qwen3.5-9B Q4_K_M** service was ready, digest
`6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`,
with 16K context and 5,763,005,151 bytes reported resident in GPU memory.
No model service was restarted, cloud request sent or training run launched.

At **04:23:58 UTC**, camera and detector were ready, recording storage was
allowed and the first five frames had been analyzed. A **04:25:20 UTC** follow-up
reported **153 analyzed frames**, no capture gaps and a 4.9-second frame age.
It also reported **36 dropped detector-queue frames**; those are detector
sampling losses, not proof of lost raw recording. The independent motion path
remained ready. The local teacher reported readiness, but the new collection
had no extracted clips or suggestions yet, so this does not establish a new
successful classification or accuracy gain.

At **04:26:10 UTC**, all **30 registered new segments** existed. Their greatest
internal timestamp gap was **0.033334 seconds**, and the newest segment's
metadata probe passed at **2560 × 1440**. This is a bounded continuity check;
it does not prove every future activity will be detected. Direct database
inspection confirmed `pause_training=true`, no datasets or models, and no
cloud batches or requests in the new collection.

Native Windows Edge verified **Monitoring continuously**, zero decisions,
automatic labeling checked and training unchecked, with no JavaScript errors
and a fitting 390-pixel mobile layout. The Codex browser was requested at
`http://127.0.0.1:8765/#today` to clear the previous session-11 URL filters;
that opening returned `queued`. Browser validation submitted no calibration
or human-review decisions. The separate review companion and prior scheduled
automations were not resumed by this operation.

### Resolving the old archive's remaining uncertainty

A read-only diagnostic container ran full SQLite integrity checks against both
archived original databases; both returned **`ok`**. The scan took several
minutes over the Windows-mounted files. A proposed bounded stop found that
the diagnostic container had already completed and been removed; the full
successful result was then collected. No diagnostic container was actually
stopped by that attempt.

The last registered old segment passed its metadata probe. The newest
unregistered MP4 left by the earlier forced shutdown did not; it remains
unchanged in the archive. Database integrity therefore has new supporting
evidence, while complete final-segment coverage is still not established.
The new collection is independent of that historical defect.

[Sanitized evidence](development-evidence/2026-11-08-fresh-collection.json)
links the area measurements, archive handoff, full database checks, recording
probe and native browser results. Private operational scripts and raw receipts
are under `outputs/fresh-collection-20261108/`, with inventory and restoration
notes beside the Windows archive. No application source or synthetic model
tests changed. Next comes new real activity and human review: the white backing
and tighter areas are plausible visibility improvements to evaluate, not a
measured improvement in drinking recognition. Training stays paused.

## 24. Separate classification crops without restarting monitoring — 8 November 2026

The user explicitly requested separate food and fountain crops using the new
areas, while monitoring continued and training remained paused. At the
**17:52:46 UTC** baseline, the existing recorder was connected and ready, with
86,264 analyzed frames, **806 clips, 620 proposals and no human reviews** in
the new collection. Its capture-gap counter was already **13**. These counts
describe the intervening day's activity; the morning's empty-collection check
was not treated as current state.

### Separate classification geometry, unchanged monitoring

The classification preparation path reused `crop_regions`, whose food/fountain
merge is useful for detector context. A dedicated
[`classification_regions`](../catwatch/learning/crop_policy.py) helper now
computes each named area's crop independently. The
[`media` preparation path](../catwatch/learning/media.py) creates one manifest
and proposal job per area, sharing the original video, timestamps, source hashes
and episode group. Version-2 identities include area names, so two equal crop
rectangles cannot accidentally collapse two named classification tasks.

Using the active investigation's exact polygons, the native rectangles are:

| Area | Pixel rectangle `(left, top, right, bottom)` | Size |
| --- | --- | --- |
| Eating pad | `(1257, 483, 1551, 776)` | 294 × 293 |
| Water fountain | `(1125, 374, 1463, 651)` | 338 × 277 |
| Litter box | `(1668, 309, 2032, 623)` | 364 × 314 |

The previous food/fountain union was 426 × 402. Each independent crop keeps
the existing 50% context per side; neighboring scene content can therefore
still appear in both views. Separate inputs do not force an eating or drinking
label. The model must still use visible behavior, and accuracy needs human
review. The calibration polygons, white background, motion thresholds,
detector behavior and previously recorded evidence were not changed.

### Applying the rule while capture continues

The running process does not reload Python modules. Replacing it merely to
change crop preparation would interrupt the recorder. Instead, the guarded
[`separate-classification-crops.py`](../scripts/separate-classification-crops.py)
utility applies a persistent SQLite queue bridge to the running older worker.
It verifies investigation 1 and the saved polygon fingerprint, requires
continuous monitoring and disabled training, and creates a consistent learning
database backup that must pass `PRAGMA quick_check` before the transaction.

At **18:01:27 UTC / 20:01:27 Asia/Jerusalem**, the transaction split **56 queued
extractions**. The original job retains food and litter; a companion fountain
job retains the same source interval and group with only its fountain polygon.
A trigger applies the same split to new jobs atomically as they are enqueued.
This lets the existing extraction code generate independent crops immediately,
without changing the running recorder. It can encode a source twice; the
native patch avoids that extra encoding and creates all manifests from one
video. Both approaches preserve episode grouping rather than counting each
crop as an independent behavior example.

The transaction verified that every existing immutable manifest and human
review field remained unchanged, and that learning settings were byte-for-byte
unchanged. There was **one extraction already running**; its input was preserved
and it produced one final historical combined clip after the policy timestamp.
This is a bounded transition, not evidence that newly enqueued work still merges.
Old combined clips and proposals remain traceable in history. No historical
batch was relabeled or human decision submitted.

The first read-only plan attempt could not import `catwatch` from a utility
copied under `/tmp`. Adding `PYTHONPATH=/opt/cat-watch` to that exec resolved
the module path. The failed plan did not install the policy or stop monitoring.
The actual receipt includes the exact reviewed policy-file hash and backup path.

### Source patch and validation

An offline image, `localhost/cat-watch:0.5.4`, was built from the exact live
0.5.3 image, without changing dependencies or contacting package repositories.
Its final identity is
`78d6d5052145bbcb56b5572c78a7f11d455cd31a896a5ac9f8995d6fe22ff53c`.
The current recorder remains on
`540a4e088dd95c017766509195324f951e88e0c611048e9fd4a6fce291d5610f`,
using the online bridge. No image replacement or restart is claimed.

The patched classification worker removes the bridge at its own startup,
after which direct media preparation supplies independent crops. Cleanup is
restricted to worker startup: opening a `LearningStore` for inspection or
review must not disable the policy underneath an older live recorder.

The initial focused suite passed **49 tests** across classification crops,
learning, focused detection and teacher recovery. After narrowing bridge
retirement to worker startup, **nine focused tests passed** for that change.
Coverage includes independent geometry, unchanged detector merging, identical
rectangle identities, native sampling, shared video storage, idempotent job
splitting, transaction rollback and preservation of already claimed jobs.

A separate native Windows Podman fixture run against the final image produced
three single-area manifests from one synthetic video and decoded their exact
pixel dimensions. That validates image packaging and crop mechanics; it is not
a real cat-behavior accuracy result. The test container used no network and
never mounted the live recording or learning database.

### Live handoff evidence

By **18:04:00 UTC**, the same recorder had advanced to **87,389 analyzed frames**,
with camera connected, detector ready, continuous monitoring true and training
false. Its container ID and original **04:22:51 UTC** start time were unchanged.
The capture-gap counter remained **13**, matching the pre-change baseline.
The learning database also retained `pause_training=true`.

A **18:06:50 UTC** recording check found all **13 segments** covering thirty
seconds before and after the policy application, with **zero internal timestamp
gaps**. This establishes bounded recording continuity across this change, not
the absence of historical camera gaps or a guarantee about future capture.

The live extraction queue first finished its older food/litter jobs before
reaching the companion fountain jobs. At **18:07:49 UTC**, it had produced
52 independent food crops and 53 litter crops since application, plus the one
already-running combined clip noted above. Native sampling verified the food
and litter dimensions while fountain extraction was still queued. This queue
delay was kept visible; merely installing the rule was not treated as proof of
completed fountain output. The final fountain checkpoint is recorded below.

The [evidence receipt](development-evidence/2026-11-08-separate-classification-crops.json)
and private `outputs/separate-crops-20261108/` records distinguish source tests,
the native fixture, the active online policy and real recorded clips. The
[learning guide](learning.md) documents the policy and later native-worker
handoff. Classification remains local, monitoring remains on, and training
remains paused. No cloud batch was approved or run by this change.

At the final crop checkpoint, **18:09:20 UTC**, **ten fountain jobs had completed**
and produced ten manifests naming only `water_fountain`. Native sampling of a
real fountain clip decoded two **338 × 277** frames. Corresponding food checks
decoded **294 × 293** frames; 56 separate food and 57 litter manifests had been
created since application. The one combined output remained the pre-existing
in-flight extraction. New fountain proposals were still awaiting their turn in
the local labeling queue, so no improved drinking-recognition result is claimed.
The final policy check also confirmed the bridge was present, training false
and `pause_training=true`. This completes the requested crop separation while
the original monitoring process continues.

## 25. Showing new fountain clips with their local classifications — 8 November 2026

The user requested a few new fountain clips with the model's answers, while
keeping monitoring on and training paused. The first **18:12 UTC** inventory
found 46 newly separated fountain clips but no completed prediction for them.
This was a labeling-queue delay, not a missing crop or a completed negative
classification. Today's clips were also assigned to the test partition, whose
ordinary review screen intentionally hides proposals for blind review.

Three existing fountain-only clips were selected for the requested assisted
inspection: recordings beginning at **17:57:47.566**, **17:58:17.037** and
**18:05:21 UTC** (19:57:47.566, 19:58:17.037 and 20:05:21 Asia/Jerusalem).
The first two are close in time and should not be counted as independent
behavior episodes. Selection was not based on a successful drinking prediction.

Between **18:18:47 and 18:19:18 UTC**, a bounded queue operation made those three
existing label jobs eligible ahead of 138 queued jobs. It left any running job
alone and retained each deferred job's original eligibility time. All three
completed on their first attempt through the existing local worker, after which
all 138 original eligibility times were restored. The helper used a finite
expiry and a restoration block, so a preview request cannot permanently strand
the ordinary queue. Learning settings were unchanged throughout.

The actual model was **qwen3.5:9b**, digest
`6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`,
using prompt `visible-actions-1` and 16 sampled native cropped frames per
eight seconds. Its results were **eating**, **eating** and **no_cat**. The first
proposal expressed uncertainty about the opening frames; all three carried the
model's `poor_lighting` quality flag. These are unconfirmed model outputs,
not human-approved annotations or a measured accuracy result. The white backing
is visible, but this selection cannot show whether it improves true drinking
recognition. Food bowls remain within the fountain crop's context margin.

Each preview was exported from its immutable source video with the exact
**338 × 277** classification crop. One black bottom row was added for compatible
H.264 playback, giving **338 × 278** exports. All three exported videos decoded
successfully at 15 fps with the original frame counts: 116, 120 and 119.
Comparing the first exported frame to the corresponding native crop gave mean
absolute pixel differences of 0.923, 1.089 and 1.040, consistent with the export's
lossy video compression. Originals and manifests were preserved.

At **18:20:03 UTC**, the three displayed examples were marked as audit review
and their model exposure was recorded in metadata. Their existing test split,
review version and empty human decisions were preserved. This makes later
reviews of these examples assisted rather than falsely blind under the app's
existing independence rule. Related overlapping clips still need exposure
screening before any future independent evaluation; this operation does not
claim to resolve that broader evaluation issue. No review was submitted for
the user, no training job was started and no cloud model was called.

The **18:20:08 UTC** final check reported a connected camera, ready detector,
**88,976 analyzed frames**, continuous monitoring true, training false and
`pause_training=true`. The recorder's container identity and original start
time were unchanged. The capture-gap counter remained **13**, equal to the
earlier baseline; that is not a claim of uninterrupted all-day capture.
Human-reviewed clips remained zero.

The [preview evidence receipt](development-evidence/2026-11-08-fountain-previews.json)
contains identities, checks and limitations. Private videos and detailed local
model outputs remain under `outputs/fountain-review-20261108/`; no private
footage is embedded in this journal. The three previews are supplied to the
user with their actual suggestions for inspection, without declaring drinking
recognition correct on the basis of negative examples.

## 26. Tightening the fountain crop to exclude food bowls — 8 November 2026

The previous previews showed why separating area names alone was insufficient:
the fountain's 50% context margin still included neighboring food bowls. The
user requested a tighter fountain crop, new classified clips and uninterrupted
monitoring with training paused. Visual inspection established a rectangle
`[1180,400,1360,602]` in the 2560 × 1440 source. This reduces classification input
from **338 × 277** to **180 × 202** pixels while retaining the fountain and white
backing and excluding both bowls. Less surrounding context is an intentional
tradeoff; approaches outside this rectangle are not visible to its classifier.

The change is a classification-only override bound to the exact saved fountain
polygon. It does not redraw the user's motion/presence area, change food or litter
classification crops, or change detector context. A later different calibration
will not silently inherit these particular bounds. Original source videos,
existing manifests, proposals and human-review history remain intact.

At **18:26:42 UTC / 20:26:42 Asia/Jerusalem**, the live worker received the new
policy transactionally after a consistent SQLite backup passed `quick_check`.
There were no queued fountain extractions or running extraction jobs to migrate
at that instant. The existing area-separation trigger remains, with an additional
trigger tightening new singleton fountain jobs, including companions generated
by the first trigger. The older worker expands a virtual extraction polygon to
produce the exact requested rectangle; this virtual polygon belongs only to the
job, never camera calibration. Job payloads also preserve the original polygon
for later native-worker handoff. Immutable clip/review fields and learning
settings were checked unchanged during the transaction.

The source implementation reads the same calibration-bound override directly.
It records the override in new manifests and restores original polygons from
bridged payloads when the native worker takes over. Worker startup retires both
legacy triggers. Crop coordinates participate in clip identity, so a narrower
input cannot accidentally reuse a wider crop's cached classification.

The focused command
`.venv/bin/python -m pytest -q tests/test_classification_crops.py tests/test_learning.py tests/test_teacher_recovery.py`
passed **40 tests**. Coverage includes default crops, matching and changed
calibrations, scaling, separate food/litter geometry, nested trigger behavior,
untouched running jobs, transactional rollback, native handoff and preserved
old manifests. One existing Starlette/AnyIO deprecation warning was reported.
An offline **0.5.5** image was built from the pinned live base with network access
disabled, identity
`2408cfc5d226f8e95e8a834b8e342a4412d2d9196f4a1a44641731116452da20`.
An isolated native fixture verified the exact 180 × 202 crop, exclusion of a
synthetic neighboring region, two decoded native samples and preserved source
identity. It mounted no live data and did not run a camera or model. This is
packaging/crop validation, not cat-behavior accuracy. The live container was
not replaced or restarted.

To provide genuinely post-change footage, three explicit local preview windows
were requested from the already running recorder: **18:26:48–18:26:56**,
**18:27:00–18:27:08** and **18:27:12–18:27:20 UTC**. Their provenance is
`manual_preview`, rather than claiming detected activity. Extraction and local
labeling each completed on the first attempt. A bounded priority operation
restored all **87** temporarily deferred label jobs; settings were unchanged.
All three new manifests contain only `water_fountain` and the exact tighter
rectangle. Ordinary audit and motion jobs also subsequently produced this crop,
so successful output is not limited to the manually requested previews.

The actual local Qwen model, digest
`6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`,
returned **no_cat** throughout each preview. It used `visible-actions-1` with
16 sampled frames per eight seconds and flagged `poor_lighting` in all three.
The displayed clips are the same crops used for those proposals. Native exports
retain all 120, 119 and 119 frames respectively at 15 fps, with no padding needed.
First-frame mean absolute differences from the corresponding source crop were
0.530, 0.487 and 0.509 after H.264 export. Visual checks confirmed the fountain
and white backing remain visible and the food bowls are absent.

These are unconfirmed model suggestions for empty-fountain examples. They do
not establish drinking sensitivity, prove that the backing improved accuracy,
or constitute independent behavior episodes. No human label was submitted.
As with the earlier requested previews, their model exposure was recorded and
they were placed in audit review while preserving test splits and review
versions, preventing later assisted reviews of those clips from being treated
as blind. No cloud inference or training was started.

A bounded continuity check found **13 existing recording segments** spanning
30 seconds before and after policy application, all files present and **zero
internal timestamp gaps**. At **18:29:38 UTC**, the camera was connected, detector
ready and **89,898 frames** had been analyzed. Continuous monitoring was true,
training false and `pause_training=true`; reviewed clips remained zero. The
recorder container and its original start time were unchanged. Its capture-gap
counter stayed at the pre-existing **13**. This verifies the change did not
interrupt the checked window, not perfect all-day coverage.

The [tight-crop evidence receipt](development-evidence/2026-11-08-tight-fountain-crop.json)
records policy, tests, model provenance, actual clip identities, queue restoration
and continuity checks. Private preview videos remain in
`outputs/tight-fountain-20261108/`. The operational crop is complete; judging
recognition of real drinking still requires a positive drinking example and
human review.

## 27. Deferring a newly authorized Sol campaign for a workstation restart — 9 November 2026

The user authorized up to **US$20** for a new batch of Sol classifications and
asked for a report, prioritizing activity around the drinking fountain while
also including eating and litter-box activity. They asked to suspend the start
for one hour because they were about to restart the workstation. This is a new,
non-renewing campaign authorization; it does not reset or erase the November
3–4 spending history. Their standing instruction to keep training paused remains
in force.

At the scheduling checkpoint, **03:36:54 UTC / 05:36:54 Asia/Jerusalem**, the
Codex app confirmed creation of the one-off heartbeat
`run-cropped-cat-activity-sol-batch`. Its persisted configuration was read back:
ACTIVE, attached to this chat, with one scheduled occurrence at **06:36 local /
04:36 UTC**. An explicit date/time guard also appears in its prompt. The three
older cat-watch automations were still PAUSED and were not reactivated. A local
scheduled task depends on the workstation and desktop app being available; this
setup does not establish that a future restart or scheduled execution succeeded.

Only scheduling, read-only documentation/source inspection and the durable
handoff were performed now. No batch selection, clip extraction, cloud request,
training, recording start/stop or workstation restart was initiated. After the
restart, the resumed task must verify actual health and saved crop metadata,
keep or safely resume the existing authorized monitoring and confirm training
is still disabled. The new fountain boundary remains the requested 180 × 202
crop excluding food bowls; the cloud payload must not silently expand it.

The [handoff](sol-cropped-campaign-2026-11-09.md) calls for a diverse activity-focused
selection, roughly 70% fountain and 15% each food/litter when evidence permits,
with a small negative sample rather than a large empty-scene batch. This is an
implementation target, not a claim about available clips or a fixed paid count.
The resumed work must freeze its manifest, use a dedicated idempotent $20 ledger,
reserve conservative cost before requests, preserve unknown-outcome reservations,
and adapt the old hardcoded campaign helpers before reuse. The user's present
request authorizes preparation and dispatch within those boundaries without a
redundant approval exchange.

Official Sol and pricing documentation were checked, preserving the established
`gpt-6.1-sol` model. The scheduled worker must verify pricing/limits again before
paid calls. The [official scheduling guidance](https://learn.chatgpt.com/docs/automations?surface=app)
confirms the local desktop availability requirement. The eventual report must
separate model proposals from confirmed labels, show representative crops and
uncertainty, and distinguish estimated inference costs from conservative exposure.
No report or classification result for this new campaign exists yet.

## 28. RHEL migration and screen-controlled quiet mode — 9 November 2026

The user reports mouse freezes and poor application responsiveness while cat-watch
runs. They authorized consolidation into the existing RHEL WSL distribution,
with the explicit rule: screen on enables quiet mode; screen off disables it.
RHEL still shares the Windows workstation, so migration alone cannot isolate
GPU or memory contention. The prior Windows container had no CPU/memory limit
and used a Windows bind mount for its active database and media.

The implementation uses Windows console-display power notifications, rather than
keyboard-idle time or the lock screen. Missing, unknown, dimmed and stale states
all stay quiet. Quiet mode gates model labeling and behavior inference; recording,
CPU motion analysis and bounded two-thread extraction continue so queued evidence
is not allowed to expire just because the screen stays on. Detector work receives
a lower rate ceiling. Training has an independent deployment lock in both modes.
A targeted gateway cancellation path is being added for cat-watch requests already
running when the screen turns on; other shared-model callers remain independent.

The migration copies rather than moves the stopped active data, verifies SHA-256
for every destination file, and retains the Windows deployment and prior archives.
Initial capacity is limited: RHEL has roughly 32 GiB free, the cached application
image is 8.56 GB and existing data are roughly 8.3 GiB. A host-disk expansion
question is pending; no filesystem resize or unrelated cleanup has been performed.
The intended deployment also reserves 5 GiB free disk space for the workstation.

At the first source checkpoint, 44 existing focused tests and 16 new performance
policy tests passed. These cover crop behavior, shared-model policy, teacher
recovery, safe display-state fallback, training lock, retry preservation and
upstream cancellation. They do not establish native display event delivery,
recording continuity, model accuracy or absence of mouse freezes; those checks
remain separate. Windows credentials will stay DPAPI protected at rest and be
forwarded through stdin to a private RHEL tmpfs file for service restarts.

At the 04:09:22 UTC checkpoint, the user had approved expanding RHEL's virtual disk to the proposed
1.2 TB (their reply wrote “1.2 gb”; the intended size was clarified in chat).
The complete source suite passed: 174 tests with one existing Starlette/AnyIO
warning. The native Windows watcher compiled, registered as a limited interactive
sign-in task, and reported a fresh `on` event. This validates actual screen-on
notification delivery; no physical display-off transition has been forced.
The Windows image export completed at 4,925,967,872 archive bytes. The data-copy
process was interrupted before cutover so RHEL can be stopped for the authorized
resize; its destination is resumable and the original remains unchanged.

**04:11:36 UTC resize checkpoint:** the imported image identity exactly matches the cached Windows 0.5.5 image. The data-copy process is stopped and resumable. Qwen and RKE2 are being stopped cleanly before the authorized WSL disk expansion. Windows Podman had no running containers.

**04:15:40 UTC resize result:** the first supported `wsl --manage RHEL10 --resize 1200GB` attempt failed with `WSL_E_DISTRO_NOT_STOPPED`; the VHD was in use again after shutdown. RHEL returned with its original filesystem size and Qwen/RKE2 active. No successful expansion is claimed. Investigating the restart race before another attempt.

**04:24:40 UTC infrastructure checkpoint:**
Windows administrator approval allowed the supported online `Resize-VHD` command
to grow the designated RHEL VHD from 1,099,511,627,776 to 1,288,490,188,800 bytes
(1,200 GiB). The native receipt records completion at 04:17:10 UTC. `resize2fs`
then grew the mounted ext4 filesystem to 314,572,800 4-KiB blocks; `df` reported
about 213 GiB available at that checkpoint. This avoids a second RHEL shutdown.
The first offline attempt remains recorded above as a failure.

The final source suite at this checkpoint passed **177 tests** with one existing
Starlette/AnyIO warning. Sampling now decodes forward from one seek instead of
repeatedly decoding the same keyframe group. A generated-video test compares all
pixels, timestamps, crops and duplicate sample indexes with the former algorithm.
The independent training lock is also enforced before the direct training
entrypoint loads any model or dataset. No training workload was started.

Windows delivered an actual off notification after its earlier on notification.
The installed shared gateway rejected a marked cat-watch request with HTTP 409
while on and accepted a short synthetic request with HTTP 200 while off. These
checks used text only, not camera frames. They establish display integration and
admission, not an accuracy result. The native RHEL GPU fixture loaded the detector
on RTX 5080 successfully; its cold synthetic warm-up reported an NMS time-limit
warning under the two-CPU fixture quota, so this is availability evidence rather
than a latency benchmark. Data copying remains in progress with per-file hashes.

**04:30:27 UTC service-control recovery:**
A later `systemctl --user` call returned connection refused despite the user
manager and Qwen processes still running. The runtime socket paths existed and
both manager/database sockets appeared in the listener inventory; the underlying
cause was not established. The only running application services in that user
manager were the shared Qwen units. A bounded restart of `user@1001.service`
restored the control connection and both Qwen units; RKE2 stayed active. The data
copy and chat execution were in `init.scope` and continued. No recorder had yet
started in RHEL. Runtime paths now use the actual user ID rather than assuming
UID 1000.

**04:37:30 UTC live cutover checkpoint:**
The DPAPI bootstrap initially failed when PowerShell inherited a Linux-style
`PATHEXT`; restoring Windows' machine value exposed and fixed the native launch
path. A second user-manager recovery followed the unit verifier replacing or
otherwise invalidating the reachable sockets again; the timing implicates the
verification run, but no upstream defect is claimed. No further live user-manager
verification runs are being used. Rootless startup then exposed the difference
between host UID 1001 and packaged UID 1000. Explicit `keep-id:uid=1000,gid=1000`
plus `--user=1000:1000` preserved private file ownership and allowed credentials
and data to be read without broadening permissions. Earlier failed starts ended
before capture. The private credential was checked mode 0600, with matching
container ownership, without printing its contents.

The first live interval contained 18 health samples over roughly a minute: camera
connected throughout, zero new runtime capture gaps and maximum health request
latency 7.2 ms. This was screen-off operation. Native Windows Edge verified Today,
Learning, disabled training controls, mobile fit and no JavaScript exceptions.
The running cgroups independently reported CPU quota `300000 100000`, memory
`6442450944`, swap `0` and PID limit `256`.

Live detector counts exposed a pacing issue in the first patch: discarding all
samples arriving before the next wall-time slot discarded most of each completed
video segment's burst. The correction waits between samples and bounds its queue
to one segment's ten expected samples. A regression test requires three queued
source timestamps to survive and be processed over at least 0.9 seconds at 2 fps.
The corrective image will be 0.6.1, including a matching OCI version label. This
is a measured engineering correction, not evidence of behavior accuracy.

**04:49 UTC completion checkpoint:**
The corrective image **0.6.1**, identity
`eef85ab0c5590d1e093694ad9d2645b2c0c07d3a8e1dd79fe1087c189be7b3d0`,
has been running since **04:39:37 UTC**. The recorder and detector are ready,
motion analysis is current, and systemd reports zero service restarts. Private
database backups taken before that correction passed quick checks. Startup now
preserves unregistered recording tails in `recovery-media`, so a restart cannot
silently discard the last unfinished file. The original Windows collection still
contains 16,678 segments and 2,079 clips; it remains a retained rollback snapshot.

The final source suite passed **179 tests**, with one existing Starlette/AnyIO
deprecation warning, and `git diff --check` passed. An earlier run correctly
failed the old four-slot queue expectation after the queue grew to ten; its
updated regression checks the bounded queue and newest retained timestamps.
Native Windows Edge checked the final deployed image at **04:41:15 UTC**:
Today and Learning loaded, training controls were disabled and unchecked, the
mobile layout fit, and no JavaScript exceptions occurred. No labels or camera
calibration were changed by these browser checks.

Across 24 health samples during startup and roughly a minute of screen-off
operation, 19 samples were ready. Maximum health latency including startup was
211.2 ms; maximum ready motion lag in that sample was 1.5 seconds. The detector
averaged 1.884 analyzed frames per second across ready samples and subsequently
processed 24 frames over 12 seconds. Its dropped-sample counter settled at 25
after cold startup and remained there during follow-up. These sampled detector
frames are separate from stream-copy recording and motion collection. Recorded
container resource samples used about one logical CPU or less for the app; the
shared Qwen service has its own allocation and can use more resources while the
screen is off. CPU percentages in these samples refer to one Linux CPU, not to
the entire Windows workstation.

The display watcher and startup tasks are installed for Windows sign-in. The
one-off resize task is disabled after success. Cat-watch is restricted to three
logical CPUs, 6 GiB RAM, no container swap, 256 tasks and lower scheduling/I/O
priority; no global WSL CPU or RAM setting changed. Training remains false with
`pause_training=true` and the independent deployment lock. Screen-off permits
background inference, never training. Real Windows on/off notifications and
gateway admission were observed; in-flight cancellation is covered by a socket
fixture, not a live GPU cancellation-latency measurement. The native display
receipts' host-only policy probe has `training_locked=false` because that probe
lacks the container environment; the deployed health API and browser correctly
report `training_locked=true`.

Recording continuity needs a precise qualification. The last retained Windows
segment ended at **03:38:54.969 UTC**, and the first RHEL segment started at
**04:34:06.125 UTC**, leaving a **3,311.156-second** migration interval. The final
corrective restart added **34.547 seconds** between registered segments. Later
RHEL segments sometimes have approximately **0.417-second** boundary timestamp
discontinuities; the last 1,000 retained Windows segments did not have such
boundary gaps. Packet inspection nevertheless found roughly 0.484-second steps
and nearly zero steps in both old and new footage. The last twelve old and twelve
new segments each contained complete 60- or 90-frame groups. An FFmpeg null-output
check exited successfully but warned about non-monotonic output timestamps;
independent OpenCV decoding then recovered all 60, 90 and 90 expected frames
from three latest segments without decoder diagnostics. This suggests irregular timestamps rather
than demonstrated missing frames, but the cause is unconfirmed and continuous
wall-time coverage is not proven. A zero runtime capture-gap counter only means
no new capture-session/analysis-queue failure was reported; it does not erase
these intervals. Retiming or changing camera configuration was not attempted.

The [sanitized migration evidence](development-evidence/2026-11-09-rhel-quiet-migration.json)
contains the image identity, database/file counts, disk resize receipt, final
health, limits, browser result, performance sample and timestamp comparison.
The [runtime guide](rhel-runtime.md) explains startup after a WSL-only restart,
the screen rule and rollback. The migration dispatched no cloud request,
performed no training and saved no human review; the separately authorized Sol
campaign is recorded in its own section below. Physical mouse responsiveness
during ordinary work still needs user observation. GPU availability and fixture
success do not establish improved animal-behavior accuracy.

## 29. Sol classification of the tightened crops — 9 November 2026

**04:44 UTC preparation checkpoint.** The scheduled task began after the requested
one-hour delay. The scheduled prompt still named Windows storage, but the current
migration handoff, `.migration-verified` marker, per-file verification receipt and
live RHEL health established the new root as authoritative. The retained Windows
container and rollback data were not resumed or modified. Monitoring was connected
and ready, the deployment training lock was active, and training remained false
with `pause_training=true`. Display-managed quiet mode was preserved.

The selected batch contains **18 clips: ten fountain, four food and four litter**.
Eight fountain windows sample distinct moments near the fountain during the
feeding-adjacent episode; two are empty-scene controls. One selected local Qwen
proposal includes drinking. This is a model candidate for comparison, not a
confirmed drinking event. The available activity spans few episodes, so the batch
is deliberately smaller than the budget could purchase; the approximate 70%
fountain allocation was not filled with more near-identical windows.

The new `cropped_campaign.py` uses only the exact saved separate crop boundaries,
32 timestamped native JPEGs per clip, Sol/medium and a dedicated immutable ledger.
The manifest fingerprint is
`b98904a7bd7615a610e98c70e7866e8d707236dffa0648adfdc22297402b6cf4`.
With 16,384 input and 2,048 output tokens allowed per request, the whole batch's
worst-case reservation is **$3.317760**, including both counting and inference
input at the conservative maximum input rate. The authorization remains $20;
unused allowance is not automatically renewed or dispatched. Standard Sol pricing
was checked against the official model and pricing pages on this date.

The focused campaign/comparison tests passed **28 tests**, with one existing
Starlette/AnyIO warning. A first helper launch could not import the new module
because the image's working directory took precedence over the mounted source;
setting `/workspace` as its working directory resolved it before any data work.
Preparation then rejected two selected durations outside its 6–8 second bounds
(one short partial window and one slightly over eight seconds). Nearby complete
windows replaced them before the manifest was frozen. No paid request had been
made at either failure. The helper is CPU-only, limited to one CPU and 2 GiB RAM;
it neither restarts the recorder nor loads a local model.

The outgoing batch has **576 timestamped cropped images**, each checksum and
native size verified. Local preview videos use the same crops; food's odd height
receives one black padding row for H.264 compatibility. Full camera frames,
wide combined food/fountain views and audio are excluded from the API payload.
Classification results and final cost/status checks follow below after dispatch.

### Sol campaign completion — 04:50 UTC

Paid dispatch ran from **04:45:17 to 04:47:03 UTC**. All **18 classifications**
and their matching **18 token-count requests** completed successfully; all returned
`gpt-6.1-sol`. The largest observed request used 5,479 input tokens and 587 output
tokens, below the frozen 16,384/2,048 limits. No request was retried, left unknown
or rejected as invalid. The separate campaign ledger remains in the owned RHEL
learning directory; the older campaign ledgers were not reset or reused.

The actual inference estimate is **$0.204778**. Conservative accounted exposure,
which retains the token-count allowance and the highest frozen cache-write input
rate, is **$0.695650**. The unused authorization is **$19.304350** and no further
batch was dispatched. These are usage-derived estimates, not a billing invoice.
The CSV ledger reconciles exactly to the durable request totals.

Sol marked **eight fountain activity clips unclear**, chiefly because the head
or mouth was outside the crop or obscured; two empty-fountain controls were
classified no_cat. One activity clip also contains moving and no_cat intervals,
so label counts overlap. No selected fountain clip received drinking. In the
one saved Qwen drinking candidate, Sol returned moving/no_cat/unclear and did not
confirm visible fountain contact. This is disagreement between model proposals,
not an independently demonstrated false positive.

The **four food crops** all contain unclear intervals, with moving, stationary
or other_activity intervals in some clips. No eating label was proposed by Sol.
The **four litter crops** contain stationary, moving and unclear intervals; the
covered box obscures some relevant action. No successful elimination or other
hidden behavior is inferred. Across all 18 clips, Sol flagged occlusion in 16,
while poor_lighting appeared in one. This sample points to visibility of the
relevant action as a major limitation, but does not measure the effect of the
white backing or establish a model's precision/recall.

The batch contains 139.654 summed clip seconds and **135.442 seconds of distinct
camera time**. It draws on 14 source-group names, collapsed by the repository's
overlap rule to six connected groups, including controls. Short gaps can split
one longer visit; these are not six independent human-confirmed behavior episodes.
Nine clips had saved local Qwen proposals at preparation; seven differ from Sol
in their fine-grained label sets. No independent human references exist for this
batch, so model agreement must not be presented as accuracy.

All 576 outgoing cropped JPEG references passed checksum and dimension checks
(572 distinct hashes; a few selected images are pixel-identical). All **18 cropped
preview videos** decoded with matching source frame counts and bounded duration;
the report gallery's 18 video links resolve. The report provides full timed Sol
intervals, saved Qwen labels, quality flags, uncertainty, source dates, cost CSV
and structured JSON. Exposure metadata and audit-review buckets identify these
shown proposals as assisted while preserving existing split assignments and
human review versions. Related source/episode groups need screening before any
later blind evaluation.

The final **04:47:55 UTC** check found camera connected, detector ready, continuous
monitoring true, training false, `pause_training=true` and the deployment training
lock active. Human review revisions, trained models and datasets remained zero.
The display signal was off, with the new quiet-mode policy preserved. The current
RHEL 0.6.1 recorder had started at **04:39:37 UTC** as part of the separately
managed migration/pacing correction, before paid dispatch; the campaign did not
restart it. Its runtime gap counter was zero and frame age 1.3 seconds. That
counter resets at startup and is not evidence of gap-free overnight coverage.

At **04:50:53 UTC**, the app confirmed deletion of the one-off
`run-cropped-cat-activity-sol-batch` schedule. The [completed report](../outputs/cropped-care-sol-20261109/report.md),
[local video gallery](../outputs/cropped-care-sol-20261109/report.html) and
[evidence receipt](development-evidence/2026-11-09-cropped-sol-results.json)
are the handoff. The $20 authorization has not been renewed, and training remains
paused pending the user's later decisions.

## 30. Launch and camera credential recovery — 11 November 2026

**04:18 UTC checkpoint / 06:18 Asia/Jerusalem.** The user requested starting
cat-watch and opening its dashboard. The current RHEL launch skill and journal
were consulted so the retained Windows deployment would remain a rollback copy.
The RHEL service was inactive, with no temporary credential file under the user's
runtime directory. Read-only SQLite quick checks passed for the approximately
890 MiB recording database and 15 MiB learning database; neither had a rollback
journal. The filesystem had roughly 172 GiB available.

The Windows display task was stopped and its heartbeat stale. Starting the
existing task restored a fresh screen-on signal, selecting quiet mode. The normal
DPAPI startup helper failed because the Windows `TapoCatMonitor` credential
directory was absent. A targeted filename search found no replacement camera
credential in the expected application/data locations. No cause for the missing
directory was established, and no password was requested in chat or printed.

The user chose to re-enter the camera account in a Windows credential prompt.
The supplied account was stored using DPAPI encryption and handed to the existing
RHEL bootstrap through stdin. The dashboard reached HTTP 200, training remained
false/deployment-locked, and screen-on quiet mode was active. Camera capture,
however, repeatedly failed. A bounded diagnostic established that RTSP was
reachable but authentication was rejected; authenticated URLs and raw decoder
errors were not logged. The service was stopped to end repeated failed attempts.
The launch helper's readiness deadline then expired, which is an accurate failure
of camera readiness rather than a database or GPU validation result.

A second secure prompt was opened with instructions to use the local Tapo camera
account instead of a TP-Link cloud login. The internal-browser open request was
accepted as `queued`; visibility was not independently observed. No calibration,
human labels, model weights or training settings were changed, and no new cloud
request was submitted. Final recovery and readiness evidence follow below.

**04:22:54 UTC final outcome / 06:22:54 Asia/Jerusalem.** The camera also rejected
the second entry. No successful live-camera session was established. A temporary
RHEL `cat-watch-review` container exposed the saved-data dashboard without camera
access, GPU work, retention or recording; Windows verified HTTP 200 and
`review_only=true`. Training remained locked off and the display policy quiet.
The user then explicitly requested stopping the app while restoring the camera
credential, superseding the launch request and the pending recovery question.

The recorder service and review container were stopped, both Windows helper tasks
were stopped, and the remaining launch process finished. The unverified DPAPI
file was retained under a distinct filename so ordinary sign-in startup will not
keep attempting that account. The temporary runtime credential was removed.
Final checks found the service inactive, no running cat-watch containers, no
listener on port 8765 and the existing data ownership/verification marker intact.
The Windows tasks remain registered; this was a stop, not an uninstall. Shared
Qwen and unrelated containers were left running. The [sanitized receipt](development-evidence/2026-11-11-launch.json)
records the successful database/dashboard checks separately from the rejected
camera authentication and final stopped state. No recording readiness or model
accuracy success is claimed.

## 31. Source publication preparation — 11 November 2026

**04:25 UTC / 06:25 Asia/Jerusalem.** After requesting that the application remain
stopped, the user requested committing and pushing the project. The pending
source update spans the learning workflow, separate care-area crops, bounded
cloud comparison tooling, shared Qwen gateway, rootless RHEL migration,
screen-controlled quiet mode and operational journal. These components are
included together because the deployed runtime imports the new learning package
and uses its training lock and job admission policy. The remote main branch was
fetched before publication; the checkout also contained the earlier unpushed
`4be0015` focused-investigation/shared-Qwen commit.

Fresh validation passed **186 tests in 25.99 seconds**, with one existing
Starlette/AnyIO deprecation warning. Syntax checks passed for **49 Python source
and helper files, 25 native Windows PowerShell scripts, 14 JavaScript files and
three shell scripts**. All pending JSON documents parsed successfully, and the
reviewed files contained no detected credential values, authenticated URLs or
embedded private images. Database, credential, recording, model and private
output files remain ignored; the tracked video fixture is synthetic. Whitespace
checks passed. These source checks did not start the application, perform a GPU
accuracy run or submit a cloud batch. Cat-watch remains stopped pending camera
account restoration. Commit creation and remote ref verification follow this
prepared source checkpoint; their final result is reported in the chat.

Staging the previously untracked evidence brought 27 Windows-generated JSON
receipts into the whitespace check and exposed their CRLF line endings. Those
files were normalized to LF, with parsed JSON equality verified for every file.
The complete staged whitespace check then passed; no receipt values changed.
