#!/usr/bin/bash
set -euo pipefail
catwatch_base="${HOME}/.local/share/cat-watch"
catwatch_image=$(/usr/bin/python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["image"])' "$catwatch_base/runtime/deployment.json")
exec /usr/bin/podman --cdi-spec-dir "$HOME/.local/share/catwatch-shared-llm/cdi" run --rm \
  --name cat-watch --label app=cat-watch --network=host \
  --userns=keep-id:uid=1000,gid=1000 --user=1000:1000 \
  --device nvidia.com/gpu=all --cap-drop=all --security-opt=no-new-privileges \
  --cpus=3 --cpu-shares=256 --memory=6g --memory-swap=6g --pids-limit=256 \
  --read-only --tmpfs /tmp:rw,size=512m,mode=1777 --stop-timeout=90 \
  --log-driver=k8s-file --log-opt=max-size=2mb \
  --mount "type=bind,source=$catwatch_base/data,target=/data" \
  --mount "type=bind,source=/run/user/$(id -u)/cat-watch-credentials,target=/run/catwatch-credentials,readonly" \
  --mount type=bind,source=/mnt/c/Alex/data/tapo-cat-monitor/display-state,target=/host-display,readonly \
  --env CATWATCH_DISPLAY_STATE=/host-display/state.json --env CATWATCH_TRAINING_PAUSED=1 \
  --env CATWATCH_DISK_FLOOR_BYTES=5368709120 \
  "$catwatch_image" python -m catwatch --credential-file /run/catwatch-credentials/credentials.json
