#!/usr/bin/env bash
# Turnkey entry point for Naza (Offline O-Level RAG Tutor).
# Auto-detects and bootstraps environment, frontend build, models, and FAISS index.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# 1. Resolve Python environment
PYTHON=""
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
elif command -v uv >/dev/null 2>&1; then
  echo "[1/5] Syncing uv dependencies..."
  uv sync
  PYTHON="$ROOT/.venv/bin/python"
else
  echo "[1/5] Setting up Python virtual environment..."
  python3 -m venv "$ROOT/.venv"
  "$ROOT/.venv/bin/pip" install -r "$ROOT/requirements.txt"
  PYTHON="$ROOT/.venv/bin/python"
fi

# 2. Ensure Desktop UI build exists
if [[ ! -f "$ROOT/desktop/dist/index.html" ]]; then
  echo "[2/5] Building desktop frontend..."
  if command -v npm >/dev/null 2>&1; then
    (cd "$ROOT/desktop" && npm install && npm run build)
  else
    echo "Warning: npm not found; desktop UI will serve dynamically if Vite is configured." >&2
  fi
fi

# 3. Ensure Gemma GGUF model exists
MODEL_FILE="${MODEL_PATH:-$ROOT/model/gemma-4-E4B-it-IQ3_M.gguf}"
if [[ ! -f "$MODEL_FILE" ]]; then
  echo "[3/5] Downloading Gemma 4 E4B-it GGUF model weights..."
  bash "$ROOT/download_model.sh"
fi

# 4. Ensure local embedding model exists
EMBEDDING_DIR="${EMBEDDING_MODEL_PATH:-$ROOT/models/embeddings/KEmbed-naija-v3}"
if [[ ! -f "$EMBEDDING_DIR/model.safetensors" ]]; then
  echo "[4/5] Downloading KEmbed-naija-v3 embedding snapshot..."
  mkdir -p "$EMBEDDING_DIR"
  "$PYTHON" -c "from huggingface_hub import snapshot_download; snapshot_download('matt-wisdom/KEmbed-naija-v3', local_dir='$EMBEDDING_DIR')"
fi

# 5. Ensure FAISS index exists
INDEX_FILE="$ROOT/data/index/index.faiss"
if [[ ! -f "$INDEX_FILE" ]]; then
  echo "[5/5] Ingesting curriculum data and building FAISS index..."
  "$PYTHON" "$ROOT/scripts/ingest.py"
fi

# 6. Execute Application Manager
exec "$PYTHON" "$ROOT/launcher/launch.py" "$@"
