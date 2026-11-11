# Local vision-model review — 2 November 2026

## Recommendation

Keep **Qwen3.5-9B as the baseline** and compare **Gemma 4 12B** before replacing it.
Gemma is a newer, credible candidate for this workstation; available evidence does
not establish that it classifies this cat more accurately. Qwen3.8-27B is newer
still, but its standard four-bit distribution is too large for a fully GPU-resident
shared monitoring setup on the RTX 5080 16 GB. This is a hardware and task-fit
recommendation, not a measured head-to-head result.

This review used model-author documentation, model-author repositories and cards,
and Ollama's own distribution listings. Community rankings and rumors were not
used as evidence. No model was downloaded, replaced or invoked for this comparison,
and no camera footage was sent to an online model.

## What is actually installed and configured

Native Windows checks on 2 November confirmed an **AMD Ryzen 9 9950X3D**, **64 GiB
RAM**, and **NVIDIA GeForce RTX 5080**, with **16,303 MiB** of reported GPU memory
and driver **617.42**. One snapshot during detector startup reported **10,933 MiB
free**. Free memory is a changing observation, not the teacher's guaranteed budget.

Cat-watch's learning configuration selects `qwen3.5:9b` through local Ollama at
`http://host.containers.internal:11434`. The service is currently unavailable to
the worker. The standard per-user Windows installation and model-manifest paths
were absent, and no Windows Podman container with `ollama` in its name was found.
That does not prove the weights are absent from other accounts, WSL distributions,
or custom locations. The actual loaded quantization, model digest and runtime
version therefore could not be verified. Here, “current Qwen” means the configured
teacher, not a successfully running model.

The teacher is only one component: YOLO detects candidates; the teacher proposes
reviewable timed labels; the smaller local VideoMAE classifier is trained from
human-confirmed examples and must qualify before routine alerts. Replacing the
teacher does not replace the need for representative data and human evaluation.

## Shortlist

Sizes below are **Ollama's llama.cpp Q4_K_M package sizes**, not measured peak VRAM.
These pages also contain Apple MLX variants; those are not the Windows CUDA target.
Tags may change, so an eventual experiment must record the full resolved digest.

| Model | Published package | Evidence and role in this project |
| --- | --- | --- |
| Qwen3.5-9B | 6.6 GB; displayed digest prefix `56671c2ab938` | Existing baseline, relatively more room for detector, image processing and context. [Ollama package](https://ollama.com/library/qwen3.5:9b). |
| Gemma 4 12B | 8.0 GB; `6114515d63c1` | First challenger to test. Google released it on 3 June 2026 and explicitly describes local execution on 16 GB GPU laptops. That statement does not guarantee concurrent cat-watch capacity. [Google developer guide](https://developers.googleblog.com/gemma-4-12b-the-developer-guide/), [Ollama package](https://ollama.com/library/gemma4:12b). |
| Qwen3.8-27B | 18 GB; `aaee06c39dcf` | Released 14 August 2026. This package already exceeds the card's total VRAM before runtime overhead, so it is a poor default for uninterrupted shared monitoring. CPU offload could make execution possible with 64 GB RAM, but its latency here is unmeasured. [Qwen release repository](https://github.com/QwenLM/Qwen3.8), [Ollama package](https://ollama.com/library/qwen3.8:27b). |
| Ministral 3 14B | 9.1 GB; `4760c35aeb9d` | Optional independent-family comparison, with vision support. It is from the December 2025 generation, so it is not a newer replacement for Qwen3.5. Prioritize the two-model pilot first. [Mistral announcement](https://mistral.ai/news/mistral-3/), [Ollama package](https://ollama.com/library/ministral-3:14b). |

The author's release repository identifies Qwen3.5's small models as released on
2 March 2026 and newer Qwen3.6 releases at 27B and 35B. Its official catalog also
lists newer, much larger Qwen3.8 models. The reviewed official sources did not
establish a released small Qwen3.8 vision successor to the 9B model. This is a
bounded search finding, not a promise that no other model exists.
[Qwen release history](https://github.com/QwenLM/Qwen3.8),
[Qwen's model catalog](https://huggingface.co/Qwen/models?p=0).

## What published results do and do not establish

Qwen reports **70.1 MMMU-Pro**, **78.4 VideoMME without subtitles**, and **74.4
MVBench** for Qwen3.5-9B. These results support retaining it as a serious visual
baseline. They do not measure drinking, eating, covered litter-box visits, or the
accuracy of this application's quantized, 16-frame prompt.
[Qwen3.5-9B author model card](https://huggingface.co/Qwen/Qwen3.5-9B).

Google reports **69.1 MMMU Pro** for **Gemma 4 12B Unified**, and documents image
and video-frame input. This is not a blanket visual benchmark win over Qwen.
Author-reported scores may use different inference settings and are not our own
controlled comparison. The relevant Google card has a 12B column; some generic
family tables omit it, so 31B results must not be attributed to 12B.
[Gemma 4 12B author model card](https://huggingface.co/google/gemma-4-12B-it).

Gemma's newer architecture and stated 16 GB hardware target justify testing it;
they do not establish better cat-behavior precision. A larger or newer model can
still confidently confuse proximity to a bowl with the act of drinking.
With the litter-box cover restored, some activity will be occluded. A valid answer
may be “litter-area visit; action unclear,” even from the better model.

## Memory and integration constraints

The current teacher sends up to 16 cropped frames per eight-second window, requests
JSON, uses a 16,384-token context, disables thinking, and caps output at 1,024
tokens. Package size is only part of the allocation: context cache, image inputs,
projector/draft components and runtime buffers also need memory. Ollama documents
that increasing context and parallelism increases memory requirements.
[Ollama context documentation](https://docs.ollama.com/context-length),
[Ollama FAQ](https://docs.ollama.com/faq).

Start with one teacher request at a time. Measure the actual peak while YOLO is
running, retain the configured GPU reserve, and do not schedule training
concurrently with teacher evaluation. Merely fitting the weights is insufficient.
CPU offload is an option for an offline experiment, not evidence of acceptable
live-monitor latency. No throughput estimate was invented from parameter count.

The current learning settings deliberately pin Qwen3.5-9B. A Gemma experiment needs
a separate comparison adapter and provenance record, or an explicit configurable
allowlist with tests. Changing the tag alone would not validate frame order,
prompt formatting, JSON parsing, truncation behavior or correct handling of the
model's thinking output.

## Proposed local comparison, with explicit bounds

This is a proposed experiment, not one that ran during the review:

1. Restore or locate the existing local teacher and record its runtime version,
   digest, quantization and actual GPU placement. Separately approve any new model
   installation or service configuration that is needed.
2. Freeze a 60-episode pilot from independent episodes across recording days:
   approximately 12 each for eating, drinking, litter activity, other activity,
   and no-cat/unclear controls. Include daytime, infrared/night, partial occlusion,
   near-bowl non-drinking and the restored litter cover. If there are not enough
   independent examples, wait; overlapping crops are not extra independent trials.
3. Establish human labels without exposing either candidate's answer first. Keep
   pilot examples separate from the final qualification set. This pilot selects
   a teacher; it cannot qualify the production behavior classifier.
4. Run the baseline and challenger sequentially on identical local crops and
   timestamps. Use the existing 16-frame/eight-second evidence limit, one request
   at a time, maximum 1,024 output tokens, maximum 180 seconds per request, and no
   automatic retries. Cap the experiment at 120 requests, six elapsed hours, and
   zero online-model calls; unfinished requests remain missing results. Record
   actual supported context and decoding settings, including any model-specific
   template or image preprocessing differences.
5. Compare per-class precision/recall, false care claims, abstention/unclear rate,
   interval accuracy, JSON validity, timeouts, median and tail latency, peak VRAM,
   and changes in detector lag or dropped frames. Include uncertainty intervals;
   a 60-episode pilot is too small to establish rare-event alert reliability.
6. Present side-by-side evidence and proposals in a separate comparison view.
   Prioritize disagreements and hard cases for the owner's short review queue;
   preserve random blind audits rather than reviewing only disagreements.
7. Adopt the challenger only if the same-data results justify the switch without
   harming monitoring. Keep model suggestions separate from human truth and retain
   provenance so any later label revision can invalidate affected training runs.

Proposed additional storage ceiling: 12 GB for one challenger distribution and
comparison outputs. Check disk headroom before downloading; do not evict existing
models or evidence to make it fit. No cloud budget is needed for this local pilot.

## Follow-up: one resident model for general local agents — 19:21 UTC

The owner clarified that the model should remain GPU-resident for multiple local
agents and general tasks. The recommendation for that role is **Qwen3.5-9B
Q4_K_M**, with Gemma 4 12B as a challenger if coding or direct audio input becomes
the dominant workload. This is an engineering recommendation from published
results and package sizes, not a new speed/accuracy measurement on this workstation.

The following are author-reported scores, higher being better. They are not a
controlled comparison of the proposed quantizations. Sources:
[Qwen's model card](https://huggingface.co/Qwen/Qwen3.5-9B#benchmark-results) and
[Google's model card](https://huggingface.co/google/gemma-4-12B-it#benchmark-results).

| Benchmark | Qwen3.5-9B | Gemma 4 12B |
| --- | ---: | ---: |
| MMLU-Pro | 82.5 | 77.2 |
| GPQA Diamond | 81.7 | 78.8 |
| LiveCodeBench v6 | 65.6 | 72.0 |
| MMMLU | 81.2 | 83.4 |
| MMMU-Pro | 70.1 | 69.1 |
| MATH-Vision | 78.9 | 79.7 |
| Tau2 | 79.1 | 69.0 |
| BFCL-V4 | 66.1 | Not reported in the cited card |

Tau2 needs a specific caveat: Qwen documents changes to the airline scenario;
Google labels its result as an average over three domains. Treat those numbers
as separate reported results, not a measured ten-point advantage under identical
conditions. Different long-context and contest-math tests were not merged into
one ranking. Missing results are not zero. Coding competitions do not establish
repository-editing success, and multilingual averages do not establish Hebrew
accuracy for the owner's particular tasks.

Benchmark inference budgets, thinking settings and precision can differ from the
local fast-response profile. In particular, cat-watch presently sets `think:false`
and caps output at 1,024 tokens. Its results cannot be equated to published model
benchmarks. Actual tokens/second, first-token latency and peak GPU memory for the
two candidates remain unmeasured in this comparison.

### Proposed resident service contract

Use one centrally managed local inference service and one model copy, shared by
all agents through an API. Each agent keeps its own messages, tools and permissions.
Recommended initial server settings are:

```text
OLLAMA_KEEP_ALIVE=-1
OLLAMA_MAX_LOADED_MODELS=1
OLLAMA_NUM_PARALLEL=1
OLLAMA_CONTEXT_LENGTH=16384
OLLAMA_NO_CLOUD=1
```

Ollama documents indefinite idle retention, per-request overrides, preload calls,
and memory growth with parallel requests. These settings require a startup preload;
keeping a model loaded does not itself restart a stopped service or guarantee
GPU placement. Verify `ollama ps` reports **100% GPU** under representative load.
[Ollama FAQ](https://docs.ollama.com/faq).

A shared gateway should enforce the selected model, context ceiling and retention
policy so one client cannot accidentally unload it or trigger model/context
switching. Start with one in-flight generation and a bounded queue. Give interactive
agent requests priority over background labeling between requests; an already
running generation is not automatically preempted. GPU detection continues outside
that language-model queue, but contention still needs measurement.

The initial 16K context matches cat-watch's current requests. Long documents and
codebases should use retrieval and deliberate context management; this is not a
claim that all agent workloads fit in 16K. Increase context or concurrency only
after measuring shared-GPU headroom. Larger contexts consume more memory.
[Ollama context documentation](https://docs.ollama.com/context-length).

Use a fast profile for extraction, routing, summaries and routine tool calls, and
a bounded thinking profile for harder planning/code tasks, through the same model.
Check supported controls with the runtime's model metadata. Thinking changes are
request options, not a reason to load a second model copy.
[Ollama thinking controls](https://docs.ollama.com/capabilities/thinking).

There is an explicit resource tradeoff: cat-watch currently requires 8,192 MiB
free to start training. A permanently resident general model plus detector and
context may leave less than this. Training must then wait; the general model must
not be silently evicted. If training cannot fit, it needs a separately chosen
maintenance window or another device. Continuous recording can still proceed,
but simultaneous GPU residency and training capacity must not be promised without
measurement. The existing worker does not yet implement the proposed central
priority queue or client-policy enforcement.

No serving configuration, model installation or running service was changed for
this follow-up comparison. The 09:50 UTC operational snapshot earlier in this
report was not refreshed; it is not a current service-availability claim.
