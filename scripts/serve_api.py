"""Start the local FastAPI tutor API on 127.0.0.1:8010.

Run from the project root:

    python scripts/serve_api.py

Warm-starts embedder + Gemma + GenerationPipeline once, then serves the
desktop UI endpoints. Never binds off-loopback.

Port 8010 avoids clashes with other local apps that commonly bind :8000.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    from scripts.preflight import run_all as _preflight

    _preflight()

    import uvicorn

    uvicorn.run(
        "backend.api.main:app",
        host="127.0.0.1",
        port=8010,
        reload=False,
    )


if __name__ == "__main__":
    main()
