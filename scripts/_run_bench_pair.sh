#!/usr/bin/env bash
# One-shot before/after benchmark runner (exclusive).
set -euo pipefail
cd "$(dirname "$0")/.."
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

# Kill other project benchmark/ask/profile jobs only (not this script).
while read -r pid; do
  [[ -z "${pid:-}" ]] && continue
  [[ "$pid" == "$$" ]] && continue
  kill -9 "$pid" 2>/dev/null || true
done < <(pgrep -f '/O-Level/O-Level/\.venv/bin/python scripts/(benchmark|ask|profile_memory)\.py' || true)
sleep 1

echo "======== BEFORE (FLASH_ATTN=false SWA_FULL=true) ========"
FLASH_ATTN=false SWA_FULL=true \
  .venv/bin/python scripts/benchmark.py --single-pass \
  | tee /tmp/benchmark_before_clean.log

echo "======== AFTER (FLASH_ATTN=true SWA_FULL=false) ========"
FLASH_ATTN=true SWA_FULL=false \
  .venv/bin/python scripts/benchmark.py --single-pass \
  | tee /tmp/benchmark_after_clean.log

echo ALL_BENCHMARKS_DONE
