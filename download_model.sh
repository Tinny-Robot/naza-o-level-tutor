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
MODEL_FILE="$MODEL_DIR/gemma-4-E4B-it-IQ3_M.gguf"

# Public, revision-pinned GGUF. No Hugging Face token is required.
MODEL_URL="https://huggingface.co/AtomicChat/gemma4-e4b-it-GGUF/resolve/9d268f101321442be9a83de0b1487a38af90999e/gemma-4-E4B-it-IQ3_M.gguf"
MODEL_SHA256="d2b45be3cfc3bb7b0d4e10ad1f796cbc2e2ec473e1ddc93b3aeb6858d57f339c"
MODEL_SIZE="4714697408"

mkdir -p "$MODEL_DIR"

verify_model() {
  [[ -f "$MODEL_FILE" ]] || return 1
  [[ "$(stat -c %s "$MODEL_FILE")" == "$MODEL_SIZE" ]] || return 1
  echo "$MODEL_SHA256  $MODEL_FILE" | sha256sum --check --status
}

if verify_model; then
  echo "verified model already present at $MODEL_FILE - skipping download"
  exit 0
elif [[ -f "$MODEL_FILE" ]]; then
  echo "existing model failed verification; downloading the pinned artifact again" >&2
  rm -f "$MODEL_FILE"
fi

echo "downloading $MODEL_URL → $MODEL_FILE (~4.7 GB)…"

if command -v curl > /dev/null 2>&1; then
  curl -L --fail --progress-bar -o "$MODEL_FILE.partial" "$MODEL_URL"
elif command -v wget > /dev/null 2>&1; then
  wget --show-progress -O "$MODEL_FILE.partial" "$MODEL_URL"
else
  echo "error: neither curl nor wget found" >&2
  exit 1
fi

mv "$MODEL_FILE.partial" "$MODEL_FILE"

if ! verify_model; then
  echo "error: downloaded model failed size or SHA-256 verification" >&2
  rm -f "$MODEL_FILE"
  exit 1
fi

echo "verified: $MODEL_FILE"
