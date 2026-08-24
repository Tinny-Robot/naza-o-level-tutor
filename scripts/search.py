"""CLI entry point: interactive semantic search over the ingested index.

Run from the project root:

    python scripts/search.py

Optionally enter Subject / Topic / Source filters, then a query. Press Enter
on an empty query (or Ctrl+C / Ctrl+D) to exit.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import TOP_K  # noqa: E402
from app.retrieval.search import format_results, search  # noqa: E402


def _optional_prompt(label: str) -> str | None:
    """Prompt for an optional filter; empty input means no filter."""
    value = input(f"{label} (optional, Enter to skip): ").strip()
    return value or None


def main() -> None:
    """Interactive query loop with optional metadata filters."""
    print(
        "O-Level semantic search. "
        "Optional Subject/Topic/Source filters, then Query. "
        "Empty query or Ctrl+C exits."
    )
    while True:
        try:
            subject = _optional_prompt("Subject")
            topic = _optional_prompt("Topic")
            source = _optional_prompt("Source")
            query = input("Enter query: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not query:
            break
        try:
            results = search(
                query,
                top_k=TOP_K,
                subject=subject,
                topic=topic,
                source=source,
            )
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        except (RuntimeError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        print(format_results(results))
    print("Goodbye.")


if __name__ == "__main__":
    main()
