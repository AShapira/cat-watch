#!/usr/bin/bash
set -euo pipefail
catwatch_repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
catwatch_base="/home/alex/.local/share/cat-watch"
catwatch_image="eb332963e39b90244658368f9e83c7cf51482c43e34167fc785fc7cbe20a9ce6"
# A CPU-only helper; the live recorder and GPU services stay independent.
exec podman run --rm -i --name cat-watch-cropped-sol-campaign \
  --workdir /workspace \
  --network=host --read-only --cap-drop=all --security-opt=no-new-privileges \
  --cpus=1 --cpu-shares=128 --memory=2g --memory-swap=2g --pids-limit=128 \
  --userns=keep-id:uid=1000,gid=1000 --user=1000:1000 \
  --tmpfs /tmp:rw,size=256m,mode=1777 \
  --mount "type=bind,source=$catwatch_base/data,target=/data" \
  --mount "type=bind,source=$catwatch_repo,target=/workspace,readonly" \
  --mount type=bind,source=/mnt/c/Alex/data/tapo-cat-monitor/display-state,target=/host-display,readonly \
  --env PYTHONPATH=/workspace --env PYTHONDONTWRITEBYTECODE=1 \
  --env CATWATCH_DISPLAY_STATE=/host-display/state.json --env CATWATCH_TRAINING_PAUSED=1 \
  --env OPENBLAS_NUM_THREADS=1 --env OMP_NUM_THREADS=1 \
  "$catwatch_image" python -u -m catwatch.learning.cropped_campaign "$@"
