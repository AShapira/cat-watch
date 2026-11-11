# Delayed Sol classification campaign — 9 November 2026

> **Completed at 04:47 UTC on 9 November:** 18/18 Sol proposals returned, with
> estimated inference $0.204778 and conservative exposure $0.695650. Monitoring
> was verified on and training paused at 04:47:55 UTC. The one-off schedule was
> deleted after completion. [Report](../outputs/cropped-care-sol-20261109/report.md)
> and [receipt](development-evidence/2026-11-09-cropped-sol-results.json).
> The instructions below preserve the original handoff; they are not a new
> authorization to repeat the batch or renew its budget.

> **9 November migration update:** cat-watch has moved to RHEL rootless
> Podman (camera/detector ready after the 04:34 UTC start). Do not resume the retained Windows container or run old helpers against
> its rollback data. Check `docs/development-log.md` and `docs/rhel-runtime.md`
> for the completed cutover before dispatch. Active RHEL data are at
> `/home/alex/.local/share/cat-watch/data`; this location is authoritative only
> after the migration receipt confirms completion. Preserve display-driven quiet
> mode and the independent training pause. If cutover is still in progress, wait
> for it rather than creating another recorder or modifying either database.

## Authorized task and start time

The user requested a batch of cropped cat-activity clips classified by Sol,
with activity around the drinking fountain as the main focus and eating and
litter-box activity also included, followed by a report of classification
results. They explicitly authorized **up to US$20** for this new campaign and
asked to delay starting activity for one hour while restarting the workstation.

**Do not begin preparation, extraction or paid classification before
2026-11-09 04:36 UTC / 06:36 Asia/Jerusalem.** This is one campaign with one
non-renewing $20 ceiling, not a daily or per-retry allowance. Preparation and
dispatch within that scope are authorized; do not require a new confirmation
solely because an older campaign used a separate approval exchange.

The one-off local Codex heartbeat is `run-cropped-cat-activity-sol-batch`, attached
to this chat (`01a1b951-4451-7673-989f-9178e7eb7feb`). Its persisted configuration
was verified ACTIVE at 03:36:54 UTC. The workstation and desktop app must be
available for the local scheduled run. No data preparation or paid request was
started when this handoff was written. The three older cat-watch automations
were found PAUSED and were left that way.

## State to verify after restart

- Project: `/home/alex/dev/cat-watch`; active data:
  `C:\Alex\data\tapo-cat-monitor\cat-watch`.
- Read AGENTS.md and the current/recent development journal. Reuse or safely
  resume the existing authorized monitoring with its saved calibration. Keep
  `training=false` and `pause_training=true`. Check camera health and calibration
  after restart before claiming monitoring readiness.
- The fountain classification override is `[1180,400,1360,602]` in the
  2560 × 1440 frame: **180 × 202 native pixels**, white backing retained and
  neighboring food bowls excluded. Verify persisted metadata and actual samples.
  Food and litter use their separate crops. Do not send full-frame footage or
  restore the previous combined/wider food-fountain view.
- The last inspected live image was 0.5.3 with two persistent queue bridges.
  Offline 0.5.5 contains native support, but was not deployed. Do not recreate
  the recorder just to classify a batch. The run-cat-watch skill provides
  restart recovery; no archive reset or destructive migration is authorized.

## Batch and spending plan

Use campaign id **2026-11-09-cropped-care-sol**. Prefer activity-bearing clips
from the fresh collection after the tightened crop took effect on 8 November
at 18:26:42 UTC. Select diverse time windows and source episodes with a small
negative control sample. Aim for approximately 70% fountain, 15% eating and
15% litter when useful footage supports that distribution; report the actual
mix. Do not fill the budget with empty or overlapping clips. Preserve source
hashes and grouping, including any newly identified recrops of older footage.

The established Sol model is **gpt-6.1-sol**. Current official documentation was
checked on 9 November; recheck pricing and limits before paid dispatch. The
existing comparison policies use standard input $2/M, output $10/M and a
conservative input ceiling covering cache writes. Do not infer invoice charges
solely from request estimates.

Adapt the existing `catwatch/learning/comparison.py`, `campaign.py` and
`fountain.py` as needed, with focused tests. Their existing campaign ids, area
selection, old fountain focus logic and November 3–4 shared budget are historical
and must not be run unchanged. In particular, old `focus_crop` logic must not
broaden the current fountain view. Prepare and freeze an immutable manifest,
then use a durable idempotent ledger dedicated to this new $20 authorization.
Preserve all previous spending records. Reserve worst-case exposure before
every outbound call, include counting/inference and unknown outcomes, and never
reset the allowance on restart. Stop before exceeding $20; spending it all is
not required. Unknown billed requests must not be silently retried.

Use only Sol for the paid classification, with the existing Windows DPAPI key
passed transiently through stdin. Do not expose secrets in commands, environment
metadata, outputs or this journal. The task is authorized cloud classification
of these crops; no other upload, model substitution or publishing is requested.

## Results and completion

Complete the batch in the resumed task, with durable checkpoints and bounded
checks. Save JSON/CSV results, per-area and unique-episode counts, timestamps,
uncertainty/failures, representative cropped clips and the spending ledger under
`outputs/cropped-care-sol-20261109/` (private evidence also stays in the owned
application campaign directory). Produce a readable report with drinking-fountain
findings first, eating and litter next, and actual/estimated costs distinguished
from conservative exposure. Compare saved local Qwen suggestions where useful.

Distinguish visible drinking from sniffing, passing, waiting, grooming and unclear
mouth contact; area presence alone is not drinking. Sol answers are proposals,
not human-confirmed labels or measured accuracy. Preserve model-assisted exposure
provenance; do not submit human reviews or start training.

Update `docs/development-log.md`, verify monitoring and training state, and return
the report and sample links in this chat. Retire the one-off schedule through
`automation_update` after dispatch/completion. Do not create a recurring spend
or completion-monitoring automation. If a real dependency is unavailable after
restart, report it and preserve the same authorization and ledger.

Official references: [Sol model](https://developers.openai.com/api/docs/models/gpt-6.1-sol),
[API pricing](https://developers.openai.com/api/docs/pricing), and
[local scheduled tasks](https://learn.chatgpt.com/docs/automations?surface=app).
