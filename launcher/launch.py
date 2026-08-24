"""CLI entry for the desktop Application Manager."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is importable when launched as a script path.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from launcher.manager import ApplicationManager  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Launch the ADTC desktop app: offline preflight, local FastAPI IPC, "
            "Vite UI, and supervised cleanup."
        )
    )
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="Do not open a Chromium/Chrome app window (headless/CI).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manager = ApplicationManager(open_window=not args.no_window)
    return manager.run()


if __name__ == "__main__":
    sys.exit(main())
