#!/usr/bin/bash
set -euo pipefail
shared_base="${HOME}/.local/share/catwatch-shared-llm"
shared_image=$(/usr/bin/python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["image"])' "$shared_base/model-lock.json")
/usr/bin/nvidia-ctk cdi generate --mode=wsl --output "$shared_base/cdi/nvidia.yaml"
exec /usr/bin/podman --cdi-spec-dir "$shared_base/cdi" run --rm --name shared-qwen-runtime \
  --label app=catwatch-shared-llm --network=host --device nvidia.com/gpu=all \
  --cap-drop=all --security-opt=no-new-privileges --read-only --tmpfs /tmp:rw,size=2g \
  --mount type=volume,source=shared-qwen-models,target=/models,readonly \
  --mount type=volume,source=shared-qwen-state,target=/root/.ollama \
  --env OLLAMA_MODELS=/models --env OLLAMA_HOST=127.0.0.1:11435 \
  --env OLLAMA_KEEP_ALIVE=-1 --env OLLAMA_CONTEXT_LENGTH=16384 \
  --env OLLAMA_NUM_PARALLEL=1 --env OLLAMA_MAX_LOADED_MODELS=1 --env OLLAMA_MAX_QUEUE=16 \
  --env OLLAMA_FLASH_ATTENTION=1 --env OLLAMA_KV_CACHE_TYPE=q8_0 \
  --env OLLAMA_NO_CLOUD=1 --env OLLAMA_GPU_OVERHEAD=1073741824 \
  "$shared_image" serve
