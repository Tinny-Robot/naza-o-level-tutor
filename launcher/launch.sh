#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  exec "$ROOT/.venv/bin/python" "$ROOT/launcher/launch.py" "$@"
fi

if command -v uv >/dev/null 2>&1; then
  exec uv run python "$ROOT/launcher/launch.py" "$@"
fi

echo "error: no project environment found." >&2
echo "Run: uv sync" >&2
echo "Or:  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
exit 1
