# Shared local Qwen service

Installed on 2 November 2026 for cat-watch and other local agents. It uses the
RTX 5080 through the RHEL10 WSL distribution. Cat-watch remains in its existing
Windows Podman container. Both use the same physical GPU.

## Connecting an agent

| Setting | Value |
| --- | --- |
| Ollama-compatible URL | `http://127.0.0.1:11434` |
| OpenAI-compatible base URL | `http://127.0.0.1:11434/v1` |
| Model | `qwen3.5:9b` |
| Quantization | `Q4_K_M` |
| API key | No authentication key required on this local endpoint; use `local` if a client requires a nonempty value |
| Context | 16,384 tokens |
| Output limit | 2,048 by default; at most 8,192 tokens per request |
| Concurrent generations | One, shared between agents |

Native `/api/chat` and `/api/generate`, plus OpenAI-compatible
`/v1/chat/completions` and `/v1/completions`, are available. Chat tool-call
generation and streaming were checked with synthetic requests. Tool execution
remains the caller's responsibility. This gateway does not expose `/v1/responses`.
Each agent supplies its own conversation; sharing weights does not merge chats.

The listener accepts loopback requests with `localhost` or `127.0.0.1` as Host.
Requests with browser Origin headers are rejected. Native Windows, WSL and the
current cat-watch container were verified against `127.0.0.1`; another container
network may need its own verified route. No LAN listener or firewall opening was
created. `host.containers.internal` is not the configured URL for this gateway.

Use the public 11434 port. Port 11435 is the loopback backend and bypasses gateway
limits; it is not an endpoint for application configuration. The gateway is a
coordination layer for trusted local agents, not isolation from hostile local
processes that can reach the backend directly.

## Keeping the model resident

The runtime sets indefinite retention, one loaded model, one generation slot,
16K context, flash attention and an eight-bit KV cache. A supervisor preloads
Qwen and checks every 15 seconds that the pinned model is fully GPU resident.
The public health endpoint returns unavailable while this cannot be verified.
Clients cannot change models, change context allocation, request CPU placement,
unload the model with `keep_alive: 0`, or administer model downloads/deletions
through the public API. Cloud use is disabled in Ollama.

The queue holds at most 16 admitted requests including the running request;
waiting requests time out after 120 seconds. Interactive requests take priority
over waiting cat-watch requests. An in-progress generation is not preempted.
Other background agents can send `X-Local-Agent-Priority: background`.

Thinking is disabled by default for predictable latency. A native client may
explicitly request it; the output cap still applies. Keep input and desired
output within the fixed context budget. The gateway does not offer arbitrary
per-client memory allocation settings.

Cat-watch's existing classification prompt is recognized as background work.
For its `format: "json"` requests, the gateway supplies a
[response schema](../scripts/shared-llm/catwatch-response.schema.json). This
requires string explanations and valid label/quality names. The application
still validates subject consistency, interval bounds and overlap; schema-valid
output is neither automatically accepted by the human nor proof of accuracy.
Other agents' JSON requests are unchanged.

## Runtime and startup

The installed files are under `~/.local/share/catwatch-shared-llm`. Rootless Podman
uses independent `shared-qwen-models` and `shared-qwen-state` volumes. The weights
are mounted read-only. They were copied from a previously cached local model and
every referenced blob was verified by SHA-256. No model download or private
camera upload was needed. The previous WorldMonitor deployment was not started
or modified.

The [lock file](../scripts/shared-llm/model-lock.json) pins:

- Model manifest: `6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`.
- Ollama version: `0.34.0`.
- Container image: `docker.io/ollama/ollama@sha256:684d8674b4315fa18f4f0e973a118ec2652ed96f67563277839985175858e0ba`.

This is a verified cached Q4_K_M revision, not a claim that the mutable model tag
or runtime is the newest available release. The model metadata reports 9.7B
parameters for the published 9B package.

`shared-qwen.service` is enabled in the WSL user's systemd manager and starts
`shared-qwen-runtime.service`. The existing user linger setting is enabled.
The Windows `SharedLocalQwen` task starts the service at the current user's
sign-in, with limited privileges, no stored password, no wake and no missed-run
catch-up. Its action was executed successfully with exit code zero while the
service was already running. A full reboot was deliberately not performed
during recording. The service operates while the workstation and WSL are awake;
it cannot remain resident while the GPU is powered off.

Read-only checks, from RHEL10 as the service owner:

```bash
systemctl --user is-enabled shared-qwen.service
systemctl --user is-active shared-qwen.service shared-qwen-runtime.service
curl --fail http://127.0.0.1:11434/health
curl --fail http://127.0.0.1:11434/api/ps
```

An intentional start or recovery:

```bash
systemctl --user start shared-qwen-runtime.service shared-qwen.service
```

An intentional stop requires both units; stopping only the API leaves the model
runtime loaded:

```bash
systemctl --user stop shared-qwen.service shared-qwen-runtime.service
```

The units restart on failure with bounded restart attempts. Persistent GPU or
runtime faults need investigation; after resolving a start-limit failure, use
`systemctl --user reset-failed shared-qwen.service shared-qwen-runtime.service`
before starting them. These instructions do not authorize unrelated service
changes or a workstation restart.

For a repeat installation using already approved cached artifacts, run
`scripts/shared-llm/install.py --source-models <existing-Ollama-models-directory>`
with Python, then enable/start `shared-qwen.service`. The installer requires the
locked image and exact model blobs to exist; it does not silently pull them.
`register-windows-startup.ps1` registers the owned sign-in task. Installation
changes host-owned service files and should be performed only within an
authorized setup or maintenance task.

## Cat-watch and GPU sharing

The supported settings API now points the running labeler at
`http://127.0.0.1:11434`. Session 11 and its confirmed camera areas are preserved.
The existing recorder was resumed because it was stopped at the initial check;
it was not restarted to attach the teacher or apply the response schema.

Automatic proposals remain suggestions. The Decisions screen shows their timed
intervals, explanations and provenance; reserved evaluation examples remain
blind. No human labels were manufactured, no trained behavior model was promoted,
and Telegram delivery is not configured.

**Automatic training was re-enabled at 20:17 UTC on 2 November 2026.** Version
0.5.3 now runs the conservative memory check and recurring teacher-status fix.
The deployed native check measured 6,085 MiB available, agreeing with host
`nvidia-smi`, while CUDA alone reported 14,953 MiB. Training uses the lower of
these readings and waits if host capacity cannot be verified.

Re-enabling training does not force an immediate run. The existing 8,192 MiB
admission threshold, 2,048 MiB running reserve and independent human-label gates
remain unchanged. At deployment there were no human-reviewed learning clips and
available memory was below admission, so no training workload started. Qwen stays
resident; recording and labeling continue. Future training remains conditional
on sufficient data and shared GPU capacity.

The upgrade's registered-media gap was **20.661 seconds**; the broader stop-request
to camera-readiness interval was 44.78 seconds. The GPU runtime was not restarted.
The previous 0.5.2 container and checksum-verified database snapshots are retained
for rollback. Media remain in their existing locations; the database-only patch
snapshot is not a full media backup. See [the deployment record](development-log.md#13-2026-11-02--deploying-the-gpu-memory-guard-and-restoring-automatic-training).

Ollama reports 5,763,005,151 bytes of resident model memory, all on GPU. Total GPU
usage during the live check was 9,439 MiB, including the runtime and other GPU
work. These are different measurements. Do not subtract the weight-file size
from 16 GB and call the remainder a measured training budget.

## Validation and primary documentation

- [First saved proposal with advancing capture](development-evidence/2026-11-02-shared-qwen-labeling.json)
- [Native JSON, tool-call and streaming checks](development-evidence/2026-11-02-shared-qwen-api-schema.json)
- [Live GPU, startup, camera and review-queue snapshot](development-evidence/2026-11-02-shared-qwen-final.json)
- [After the schema fix: 20 proposals with continuing recording](development-evidence/2026-11-02-shared-qwen-followup.json)
- [Native Windows dashboard check](development-evidence/2026-11-02-shared-qwen-ui.json)
- [0.5.3 deployment and database snapshot receipt](development-evidence/2026-11-02-gpu-memory-deployment.json)
- [Deployed native memory/admission check](development-evidence/2026-11-02-gpu-memory-live.json)
- [Automatic training re-enabled](development-evidence/2026-11-02-gpu-memory-training-enabled.json)
- [Recording interruption measured from media](development-evidence/2026-11-02-gpu-memory-recording-gap.json)
- [Gateway policy tests](../tests/test_shared_llm.py) and [worker/capacity regressions](../tests/test_teacher_recovery.py)

The live API checks establish integration on this workstation, not a language or
vision benchmark. Human review and independent held-out days remain necessary.

Official runtime references: [Ollama retention and concurrency FAQ](https://docs.ollama.com/faq),
[loaded-model API](https://docs.ollama.com/api/ps),
[OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility), and
[GPU container setup](https://docs.ollama.com/docker).
