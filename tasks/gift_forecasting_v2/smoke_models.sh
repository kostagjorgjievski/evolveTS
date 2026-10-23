#!/usr/bin/env bash
# Run model_smoke.py for each v2 checkpoint inside the v2 worker image, with the
# evaluator's container limits (no network, read-only root, 8 GiB, one CPU,
# checkpoints mounted read-only). Each model takes a free candidate GPU slot
# (the evaluator's lock files), so running searches are never disturbed.
#
#   bash tasks/gift_forecasting_v2/smoke_models.sh [MODEL ...]
set -euo pipefail
TASK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$TASK/../.." && pwd)"
PROFILE="$ROOT/configs/hosts/$(hostname -s).json"
read -r IMAGE GPUS < <(python3 -c 'import json,sys; p=json.load(open(sys.argv[1]))
print(p["gift_v2_worker_image"], ",".join(map(str, p.get("gift_v2_physical_gpus") or p.get("physical_gpus") or [p["physical_gpu"]])))' "$PROFILE")
GPUS="${SMOKE_GPUS:-$GPUS}"   # e.g. SMOKE_GPUS=4 when other users fill a GPU
MODELS_DIR="$(python3 -c 'import json,sys; from pathlib import Path; p=Path(sys.argv[1]).resolve(); print((p.parents[2]/json.load(open(p))["models_host_dir"]).resolve())' "$TASK/protocol.json")"
LOCKS="$(dirname "$(readlink -f "$ROOT/.venv")")"
names=("$@")
[ ${#names[@]} -gt 0 ] || names=(chronos-2 timesfm-2.5 timesfm-3 tirex-2 toto-2.0-313m flowstate-r1.1 timestral-209m)
failures=0

for name in "${names[@]}"; do
  while :; do
    for gpu in ${GPUS//,/ }; do
      exec 9>>"$LOCKS/gift-eval-gpu-$gpu.lock"
      if flock -n 9; then break 2; fi
      exec 9>&-
    done
    sleep 5
  done
  out="$(mktemp -d)"
  docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
    --user "$(id -u):$(id -g)" --gpus "device=$gpu" --memory 8g --memory-swap 8g --cpus 1 \
    --pids-limit 128 --tmpfs /tmp:rw,size=256m \
    --mount "type=bind,src=$TASK/model_smoke.py,dst=/job/model_smoke.py,readonly" \
    --mount "type=bind,src=$out,dst=/output" \
    --mount "type=bind,src=$MODELS_DIR,dst=/models,readonly" \
    --env HOME=/output --env TMPDIR=/tmp --env CUDA_VISIBLE_DEVICES=0 --env OMP_NUM_THREADS=1 \
    "$IMAGE" /usr/local/bin/python /job/model_smoke.py "$name" --restricted 2>"$out.err" \
    || { failures=$((failures + 1)); echo "{\"model\": \"$name\", \"gpu\": $gpu, \"error\": $(tail -c 1500 "$out.err" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}"; }
  exec 9>&-
  rm -rf "$out" "$out.err"
done
[ "$failures" -eq 0 ]
