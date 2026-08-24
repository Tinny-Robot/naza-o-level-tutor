#!/usr/bin/env bash
# Download the submission GGUF into model/ (ADTC 2026 Laptop LLM track).
#
# Rules:
#   - Idempotent (safe to run multiple times).
#   - No credentials - public URL only.
#   - Output path must match `_runtime.model_path` in metadata.json.
#
# Production Naza demo still defaults to models/*.gguf via MODEL_PATH.
# This script only populates the ADTC-required model/ directory.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_DIR="$HERE/model"
MODEL_FILE="$MODEL_DIR/gemma-4-E4B-it-Q4_K_M.gguf"
LEGACY_FILE="$HERE/models/gemma-4-E4B-it-Q4_K_M.gguf"

# Public GGUF (same quant the Naza demo uses). Replace if you host your own release.
MODEL_URL="https://huggingface.co/lmstudio-community/gemma-4-E4B-it-GGUF/resolve/main/gemma-4-E4B-it-Q4_K_M.gguf"

mkdir -p "$MODEL_DIR"

if [[ -f "$MODEL_FILE" ]]; then
  echo "model already present at $MODEL_FILE - skipping download"
  exit 0
fi

# Local convenience: reuse an already-downloaded weights file under models/
if [[ -f "$LEGACY_FILE" ]]; then
  echo "linking existing $LEGACY_FILE → $MODEL_FILE"
  ln -f "$LEGACY_FILE" "$MODEL_FILE" 2>/dev/null || cp -n "$LEGACY_FILE" "$MODEL_FILE"
  echo "done: $MODEL_FILE"
  exit 0
fi

echo "downloading $MODEL_URL → $MODEL_FILE (~5.3 GB)…"

if command -v curl > /dev/null 2>&1; then
  curl -L --fail --progress-bar -o "$MODEL_FILE.partial" "$MODEL_URL"
elif command -v wget > /dev/null 2>&1; then
  wget --show-progress -O "$MODEL_FILE.partial" "$MODEL_URL"
else
  echo "error: neither curl nor wget found" >&2
  exit 1
fi

mv "$MODEL_FILE.partial" "$MODEL_FILE"
echo "done: $MODEL_FILE"
