# Care-labeling sprint toward approximately 15 November 2026

The immediate objective is a useful, reviewed dataset for drinking and litter
activity. Training is suspended while this evidence accumulates. Recording and
local Qwen proposals continue. Calendar dates are targets, not an accuracy promise.

## What is operating

**4 November outcome:** The exact approved 100-clip batch completed with 100
valid Sol/medium proposals, no retries and an estimated inference cost of
$2.743841. Conservative exposure across both authorized batches is $12.121210,
leaving $7.878790 under the original $20 ceiling. The review UI shows all results;
none has yet been human-confirmed. Recording and Qwen continue; training is off.

**4 November, fountain follow-up completed:** The separately approved 100-clip
fountain batch produced **97 usable Sol/medium proposals and three validation
failures**, with no retries or unresolved requests. It used the exact 3,400-crop
manifest `900e180e988c5a13d1fe59e00f86d9e7b32c62c893bbb25e0f60a20af91fd4e4`,
including 77 recent clips and 23 archive clips, without overlap against previously
uploaded fountain time windows. The queue is
`http://localhost:8767/?campaign=2026-11-04-fountain-100`.

Sol proposed no drinking; 96 of the 97 usable answers include unclear intervals.
On the same 84 clips with saved Qwen proposals, Qwen proposed eating in 78 and
Sol in none. This is disagreement under different sampling conditions, not an
accuracy ranking. Review the full video to establish whether the action is
visible before treating either proposal as a label. The private
`outputs/fountain-campaign/review-first.md` starts with ten questions across ten
recording days/source groups and separately lists the three manual-only cases.

This batch's estimated inference cost was **$1.617770**, with **$5.642830** in
conservative accounting. Across all three approved batches the figures are
**$5.042941 estimated inference** and **$17.764040 conservative exposure**, leaving
**$2.235960** under the original $20 ceiling. Every new request was reconciled
from saved usage. Input counts were 5,364–5,369, below the frozen 6,000 cap;
maximum output was 679, below 1,536. No further batch is authorized. These are
usage estimates, not invoices. The earlier exact-approval block was resolved
by the user's explicit approval; journal entry 19 preserves that sequence.

Recording and GPU-resident Qwen continued, training stayed off, and no human
labels were submitted by the agent. Native Windows Edge verified the completed
queue. The corrected recording audit verified all 217 segments overlapping the
run; no recorder restart occurred. The immediate checkpoint is evidence
visibility and human adjudication, not resuming training.

Sol proposed one litter-activity example and no drinking examples; 71 clips
include unclear intervals. The immediate checkpoint is to adjudicate the ten
suggested difficult examples and establish whether visible evidence supports
reliable care labels. Candidate count alone cannot satisfy the training gates.
The local rolling pool now excludes the approved source groups and has 36 fresh
candidates (31 fountain, five litter), without any additional cloud dispatch.

The companion at `http://localhost:8767/` has a batch selector for the completed
care batch and the completed fountain batch. Sol/medium proposes intervals and explains visible evidence;
the person reviewing can accept, edit, mark unclear, skip, or undo. Only an
explicit review action records a human label. The companion shares the main
application's revision history and clips, so accepted decisions also appear in
cat-watch. It does not restart the recorder or consume GPU memory.

The companion refreshes a **local-only** shortlist every 15 minutes while running.
This is a metadata search, not an additional paid model call. The first refresh returned 100 candidates; after excluding the fixed batch, a later verified refresh returned 36 fresh candidates. Its private
`shortlist.json` is the starting point for the next selection and excludes the
source groups already assigned to all frozen review batches. Each fixed cloud
batch never grows automatically. The service restarts with Podman when available;
it cannot record or refresh while the workstation/Podman is off. The Windows loopback tunnel is a user process; after a workstation restart, run `scripts/open-care-review.ps1` to reopen the review connection. This does not start recording or spend API credit.

Selection uses recorded fountain/litter visits, motion in the relevant area,
cat observations, and recency. Candidates are 5.95–8.01 seconds, have available
cropped evidence, are separated by at least 12 seconds, and are capped at two
per source group. The initial aim is 50 per area, but an area with insufficient
signals yields its quota to stronger candidates in the other area. No-signal
clips are excluded. Motion and area presence are selection signals, not labels.
Old clips may fill genuine evidence gaps; the manifest records their dates.

The outbound evidence is 32 native cropped JPEGs per clip, with timestamps,
checksums and a fixed prompt. Sol sees no audio or full camera frames. This gives
more temporal evidence than the earlier 16-frame comparison, but a hidden mouth
or covered litter activity must still remain uncertain. The local Qwen comparison
uses its saved proposal; its earlier sampling/prompt conditions can differ, so
this is diagnostic disagreement, not a controlled accuracy leaderboard.

## Review priorities

1. Begin with `outputs/care-campaign/review-first.md`: ten selected questions across both areas, with direct clip links. Confirm visible drinking, distinguishing repeated visible lapping from standing,
   sniffing or simply lowering the head. Reject suggestions unsupported by the video.
2. Confirm visible litter digging, posture, covering and entry/exit context. Do not
   infer elimination inside the cover. Use unclear for hidden activity.
3. Keep useful nearby negatives: a cat passing, inspecting the fountain or box,
   resting nearby, and motion without a visible cat. Negative examples prevent
   the model from learning that an area alone implies a care action.
4. Split genuine behavior transitions into non-overlapping intervals. Skip a
   clip when a reliable decision cannot be made; skipping is not a negative label.

If human review also finds the care actions hidden, the next acquisition experiment should use longer local entry/exit context and verify visibility before proposing more cloud expenditure. For a covered litter box, a separately defined visible-visit label may be more attainable than the existing digging/posture/covering classes; that taxonomy change is a proposal, not part of this completed batch.

The interface supports slow playback. The aim is short review sessions, with the
agent doing selection and proposals. There is no requirement to accept all 100,
and 100 clips are not 100 independent positive episodes.

## Dataset and evaluation integrity

No cloud proposal automatically becomes training data. Accepted labels record
`source=human`, `independent=false`, and the assisting campaign/model. Versioned
history supports correction and undo.

The newest source days initially happened to be assigned to validation/test.
Before exposing assisted labels, the campaign reassigns **complete connected
components** (days, visits and shared source hashes) to the training pool. It
requires training to be off, no existing dataset/model artifacts, and no
independently reviewed labels in an affected component. The prior clip buckets
and every partition assignment are saved in a private audit record. Other days
remain untouched. Assisted data cannot later be described as blind evaluation.

Fresh, unseen days must supply the independent validation and test sets. A blind
review hides model suggestions; seeing the model answer first makes a decision
assisted even when the person disagrees with it. The current general trainer also
requires 30 independent episodes for **each** care class, including eating. Thus
30 drinking/litter clips alone do not authorize a train-ready claim.

## Milestones and decision points

| Target | Work and evidence required |
| --- | --- |
| 4–6 November | Review the completed care and fountain proposals, starting with the short review lists. Count accepted positive episodes and useful negatives by behavior/day; diagnose why candidates are rejected. |
| 5–8 November | Continue recording and local shortlist refresh. Favor underrepresented behaviors, distinct visits and lighting conditions. Prepare further batches only within their explicit authorization. |
| 8 November | Dataset checkpoint: target at least 30 confirmed independent episodes per intended trained class, across several days, plus nearby negatives. If litter activity remains hidden or rare, explicitly narrow the prototype to observable visits until evidence improves. |
| 9–10 November | Reserve unseen recording days for blind validation/test. Resume training only after a separate readiness review. Choose a training configuration that fits alongside resident Qwen; do not unload the shared service automatically. |
| 11–12 November | Run the candidate model in shadow mode. Measure per-class precision/recall, false alerts, abstention and coverage on human-reviewed held-out episodes. Do not promote based on training scores. |
| 13–14 November | Exercise the daily summary and alert flows, replay missed/duplicate-event cases, and document limitations. Telegram delivery still needs configuration and an authorized real delivery test. |
| Around 15 November | Demonstrate recording → visible event evidence → reviewed local predictions → summaries and tested alerts for qualified behaviors. Label unqualified behaviors as provisional or unavailable. |

These checkpoints deliberately depend on evidence. A covered box may support
entry/exit monitoring before it supports reliable classification of actions
inside. The deadline does not justify inventing positive examples or reporting
model accuracy without independent human references.

## Spending and operations

All campaign requests use the same durable SQLite spending ledger as the earlier
comparison. The $20 total ceiling includes the previous conservative exposure of
$2.019750. Each request reserves its worst case before either token counting or
inference. Usage estimates distinguish cache reads/writes and reasoning output.
Unknown outcomes retain their full reservation and stop dispatch; there are no
automatic retries. Inference estimates and conservative exposure are not invoices.

The completed care manifest permitted at most 100 Sol/medium labeling requests and their
matching token-count requests, with 4,096 output tokens and 65,536 input tokens
per clip. The completed fountain manifest used the lower limits stated above.
Astra is not part of either 100-clip batch. No key is stored in the image, command
arguments, environment metadata or development log. The native Windows credential
is decrypted transiently and passed only through the runner's standard input.

Reproducible commands from native PowerShell:

```powershell
scripts/run-care-campaign.ps1 -Stage Build
scripts/run-care-campaign.ps1 -Stage Prepare  # local; freezes manifest
scripts/run-care-campaign.ps1 -Stage Cloud    # exact authorized batch only
scripts/run-care-campaign.ps1 -Stage Serve    # isolated local review + local refresh
scripts/open-care-review.ps1                # verified Windows loopback tunnel
scripts/run-care-campaign.ps1 -Stage Report   # no cloud inference
```

Private manifests/results live under the application's
`learning/campaigns/2026-11-04-care-candidates/`. They contain private evidence
paths and are not publication artifacts. Model/API policy references:
[Sol documentation](https://developers.openai.com/api/docs/models/gpt-6.1-sol),
[pricing](https://developers.openai.com/api/docs/pricing), and
[prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching).
