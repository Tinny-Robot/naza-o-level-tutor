"""CLI entry point: evaluate retrieval quality against data/eval/qa.json.

Run from the project root:

    python scripts/evaluate.py

Requires a built index (unless RETRIEVAL_MODE=bm25) and a populated
``data/eval/qa.json``. An empty dataset prints a clear message and exits 0.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.evaluation.evaluator import RetrievalEvaluator, run_evaluation  # noqa: E402
from app.evaluation.loader import QADatasetError  # noqa: E402
from app.utils.logging import get_logger  # noqa: E402

logger = get_logger(__name__)


def main() -> None:
    """Load the eval set, run retrieval metrics, print the summary banner."""
    try:
        metrics = run_evaluation()
    except QADatasetError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except (RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if metrics.get("empty"):
        print(
            "Evaluation dataset is empty (data/eval/qa.json). "
            "Add hand-curated items - see data/eval/qa.example.json - then re-run."
        )
        print(RetrievalEvaluator.format_summary(metrics))
        return

    print(RetrievalEvaluator.format_summary(metrics))
    print(f"Queries evaluated: {metrics['n_queries']}")
    print(
        f"Precision@5: {metrics['precision@5']:.4f}  "
        f"Precision@10: {metrics['precision@10']:.4f}"
    )


if __name__ == "__main__":
    main()
