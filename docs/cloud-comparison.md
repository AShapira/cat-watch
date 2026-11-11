# Bounded cloud comparison — 3 November 2026

The user reported $39 in activated API credits and authorized **up to $20 total**
for the proposed cloud models, cost monitoring and comparison with local Qwen.
The balance is user-reported; no billing-account balance has been verified.
The $20 is a ceiling, not a target or a recurring allowance.

## Current result

The user explicitly approved the exact ten-clip/160-crop batch with fingerprint
`564f58a07e60d9117254be7819b64526ffb5bf8438d37e8473f145bb94c861de`.
The cloud run finished at **04:16 UTC** with no retries or unknown outcomes.

| Model/configuration | Valid annotations | Mean request time | Estimated inference USD |
| --- | --- | --- | --- |
| Qwen3.5-9B Q4_K_M, thinking off | 9/10 | 3.179s | $0 API fees |
| GPT-6.1 Sol, medium | 10/10 | 7.841s | $0.159930 |
| GPT-6 Astra, high | 5/5 | 20.933s | $0.521400 |

The corrected total is **$0.681330**, including cache writes and reasoning
tokens. Conservative exposure is **$2.019750**, including the token-count
allowance, leaving **$17.980250** of the $20 authorization. These figures have
not been reconciled against an invoice or account balance. End-to-end request
times include preflight work and are not isolated generation benchmarks.

Qwen proposed eating in seven clips; Sol proposed it in none. Sol and Astra
returned the same subject assessments and label sequences on all five shared
clips, with some differing interval boundaries. There is only one assisted
human reference and no independent references, so these are disagreement and
response-validity results, not classification accuracy. The private `analysis.md`
includes the clip comparison and focused human-review questions.

The ordinary dashboard cloud indicator remains disabled. This comparison uses a
separate one-shot runner so the recorder need not restart to receive credentials.
It does not enable unattended production cloud labeling or modify training data.

## Exact experiment and limits

| Role | Model | Reasoning | Request limit | Output token cap |
| --- | --- | --- | --- | --- |
| Existing local baseline | Qwen3.5:9b Q4_K_M | Thinking disabled, current operating profile | 10 | 4,096 |
| Primary cloud comparison | GPT-6.1 Sol | Medium, standard mode | 10 | 4,096 |
| Hard-case comparison | GPT-6 Astra | High, standard mode | 5 | 8,192 |

The local digest is
`6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`.
Each clip has 16 timestamped native-resolution area crops, for 160 distinct
prepared frame positions. Actual clip durations are 6.012–7.990 seconds. Crop
sizes are 399×449 or 510×489 pixels. Full camera frames and audio are excluded.
The same prepared images and instruction text are used for all models; human
labels and previous model answers are withheld from cloud prompts.

Astra receives the five lowest-agreement or invalid-output cases after Sol.
Its subset is deliberately harder, so its aggregate must not be compared with
Sol's entire cohort. The report includes metrics on the matched three-model
subset. Unreviewed cases establish disagreement, not which model is correct.
Invalid outputs remain missing predictions in the attempted reference denominator.

The manifest and spending authorization are frozen in SQLite. They expire at
**2026-11-03 09:58:17 UTC**, six hours after preparation. There is no scheduler,
automatic renewal, or reset on rerun. An expired manifest or unresolved request
stops the runner. All fifteen approved generation slots are now consumed. No
further cloud work is scheduled. Do not delete the ledger to continue a campaign.

This first selection used a strict six-second minimum. Four reviewed exports
were 5.999 seconds and therefore fell below it; five other reviewed exports were
shorter. Only one review entered the cohort. This makes the pilot unsuitable for
an accuracy ranking. A later evaluation should use a frame-aware duration
tolerance and more independent human references, with a newly reviewed manifest.
The running recorder's clip creation and review queue were not changed here.

## Spending controls and evidence

Before each outbound request, an immediate SQLite transaction reserves the
worst allowed cost. Input is preflight-counted using the Responses token-count
endpoint. Generation stops above 65,536 input tokens, well below long-context
pricing thresholds. Output caps include hidden reasoning tokens. Standard
service and reasoning modes are explicit; no paid tools are enabled.

Rates checked against official documentation on 3 November 2026:

| Model | Input / million | Cached input / million | Output / million | Conservative maximum input rate |
| --- | --- | --- | --- | --- |
| Sol | $2 | $0.10 | $10 | $5 |
| Astra | $10 | $1 | $50 | $25 |

The reservation allows input twice, covering both counting and generation, at
the highest documented cache-write rate. This deliberately exceeds the ordinary
inference estimate. A Sol request reserves $0.696320; Astra reserves $3.686400.
Successful calls settle against returned usage plus the conservative counting
allowance. Timeouts, crashes, or ambiguous outcomes retain the full reservation
and are never automatically retried. The runner stops on the first unresolved
cloud result. No new reservation can put the campaign above $20.

The CSV records ordinary input, cached input, cache writes split by lifetime,
total output including reasoning, reasoning tokens, estimated inference cost,
conservative accounted exposure, and original
reservation for every request. These are usage-based estimates and budget
controls, **not an OpenAI invoice or verification of the remaining account
balance**. Billing reconciliation remains a separate step after real usage.

Real usage exposed an initial estimate that omitted the cache-write premium.
The estimator now charges the documented 30-minute default (1.25× ordinary input)
or a reported 12-hour write (2.5×), instead of double-counting those tokens at the
ordinary rate. Offline reconciliation changed $0.592158 to $0.681330, retaining
the previous estimate and reason on each request. Conservative exposure was
already sufficient and did not change. No requests were repeated to make this
correction.

Official sources:

- [Sol model and supported reasoning efforts](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
- [Astra model and supported reasoning efforts](https://developers.openai.com/api/docs/models/gpt-6-astra)
- [Current API pricing](https://developers.openai.com/api/docs/pricing)
- [Token counting](https://developers.openai.com/api/docs/guides/token-counting)
- [Cache-write rates and default lifetime](https://developers.openai.com/api/docs/guides/prompt-caching)
- [Input-token request schema](https://developers.openai.com/api/reference/resources/responses/subresources/input_tokens/methods/count)

## Inspect the completed run

Exact-batch approval was obtained and the one-shot run is complete. The saved
key does not need to be entered again. To regenerate the saved reports without
making API calls, run from native Windows PowerShell in the project directory:

```powershell
.\scripts\run-cloud-comparison.ps1 -Stage Report
```

For a future key change, use `scripts/configure-learning-secret.ps1 -Service OpenAI`
and enter the secret only at its secure local prompt. The key must belong to the
OpenAI organization/project with the activated credits. It is stored using
Windows DPAPI for the current user, then passed to
the isolated runner through stdin. It is never put in container environment
metadata, a command argument, the ledger, or source control. Read-only model
access checks run before any frame upload. This is a manual continuation, not
a promise that saving the key alone starts work in the background.

Other stages are `Build`, `Prepare`, `Local`, `Cloud`, and `Reconcile`.
`Reconcile` only recalculates saved usage offline and is idempotent; it does not
release conservative budget exposure. Repeating a stage
does not repeat an already attempted clip/model pair. `Build` uses the verified
0.5.3 image offline. It does not replace the recording image.

Private artifacts are under
`C:\Alex\data\tapo-cat-monitor\cat-watch\learning\comparisons\2026-11-03-pro-credit-comparison`:

- `manifest.json`: exact frozen selection, frame hashes and parameters.
- `comparison.md` / `comparison.json`: labels, explanations and human references.
- `analysis.md` / `analysis-summary.json`: readable findings and review questions.
- `cost-ledger.csv`: per-request usage and spending accounting.
- `cost-summary.json`: aggregate results without image contents.

The durable ledger is the sibling `learning\cloud-comparison.sqlite3`.
These files are local evidence, not publication artifacts. Human decisions and
production predictions are not overwritten. No cloud suggestion becomes a
training label automatically.

Validation: the earlier 42-test regression suite passed, including concurrent budget admission,
restart persistence, changed-image rejection, timeout reservation retention,
reasoning-token accounting, invalid-output cost settlement, and reference
denominators. After adding cache-write correction and audit tests, all 14 focused
comparison tests passed. The completed 15 real cloud generations establish API
execution on the approved frames; they do not establish behavioral accuracy.
All frame hashes and per-request cost bounds were verified after completion,
and a separate decimal calculation matched the corrected estimates. Recording
and resident Qwen were healthy in the final native check, with the recorder's
original image and start identity intact.
