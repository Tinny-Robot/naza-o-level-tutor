"""Container entry: FastAPI + built SPA on published interfaces.

Local ``./launch.sh`` and ``scripts/serve_api.py`` stay loopback-only.
This process binds ``0.0.0.0`` so Docker can publish :8010 and :5151.
The host browser still talks to 127.0.0.1 (published ports); CORS is unchanged.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> None:
    host = os.getenv("BIND_HOST", "0.0.0.0")
    api_port = int(os.getenv("API_PORT", "8010"))
    ui_port = int(os.getenv("UI_PORT", "5151"))
    ui_root = _ROOT / "desktop" / "dist"
    index = ui_root / "index.html"
    if not index.is_file():
        raise SystemExit(
            f"Missing built UI at {index}. The Docker image must run the UI build stage."
        )

    # Fail fast if the GGUF model is absent — clearer than a crash inside warm_pipeline().
    from scripts.preflight import run_all as _preflight
    _preflight()

    def run_ui() -> None:
        from launcher.static_server import serve

        serve(host, ui_port, ui_root, allow_all_interfaces=True)

    thread = threading.Thread(target=run_ui, daemon=True, name="naza-ui")
    thread.start()

    import uvicorn

    uvicorn.run(
        "backend.api.main:app",
        host=host,
        port=api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
