"""Run retrieval evaluation over the hand-curated Q&A dataset."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tqdm import tqdm

from app.config import QA_PATH, TOP_K
from app.evaluation.loader import load_qa_dataset
from app.evaluation.metrics import (
    hit_rate,
    label_relevances,
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
)
from app.retrieval.retriever import Retriever
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Evaluate at both cutoffs; retrieve at least this many for fair Recall@10.
EVAL_TOP_K: int = 10


class RetrievalEvaluator:
    """Evaluate a :class:`Retriever` against a validated ``qa.json`` dataset.

    Relevance uses subject and/or ``expected_keywords`` overlap against each
    retrieved document's text and metadata (see :mod:`app.evaluation.metrics`).
    """

    def __init__(
        self,
        retriever: Retriever,
        qa_path: Path | None = None,
        eval_top_k: int = EVAL_TOP_K,
    ) -> None:
        """Bind a retriever and dataset path.

        Args:
            retriever: Configured retriever instance.
            qa_path: Path to ``qa.json`` (defaults to :data:`app.config.QA_PATH`).
            eval_top_k: Number of docs to retrieve per question (must be >= 10
                to report Recall@10 meaningfully; defaults to 10).
        """
        self.retriever = retriever
        self.qa_path = qa_path if qa_path is not None else QA_PATH
        self.eval_top_k = max(eval_top_k, 10)

    def evaluate(self) -> dict[str, Any]:
        """Run every question through the retriever and compute metrics.

        Returns:
            Dict with metric floats, per-item details, and ``n_queries``.
            When the dataset is empty, metrics are 0.0 and ``empty`` is True.

        Raises:
            QADatasetError: If the dataset cannot be loaded/validated.
        """
        items = load_qa_dataset(self.qa_path)
        if not items:
            logger.warning(
                "Evaluation dataset at %s is empty. Add hand-curated items "
                "(see data/eval/qa.example.json).",
                self.qa_path,
            )
            return {
                "empty": True,
                "n_queries": 0,
                "recall@5": 0.0,
                "recall@10": 0.0,
                "precision@5": 0.0,
                "precision@10": 0.0,
                "mrr": 0.0,
                "hit_rate": 0.0,
                "per_item": [],
            }

        all_relevances: list[list[bool]] = []
        per_item: list[dict[str, Any]] = []

        for item in tqdm(items, desc="Evaluating", unit="q"):
            results = self.retriever.retrieve(item["question"], top_k=self.eval_top_k)
            labels = label_relevances(
                results,
                subject=item["subject"],
                expected_keywords=item["expected_keywords"],
            )
            all_relevances.append(labels)
            first_hit = next((i + 1 for i, flag in enumerate(labels) if flag), None)
            per_item.append(
                {
                    "id": item["id"],
                    "question": item["question"],
                    "n_retrieved": len(results),
                    "n_relevant": sum(1 for flag in labels if flag),
                    "first_hit_rank": first_hit,
                }
            )

        metrics = {
            "empty": False,
            "n_queries": len(items),
            "recall@5": recall_at_k(all_relevances, 5),
            "recall@10": recall_at_k(all_relevances, 10),
            "precision@5": precision_at_k(all_relevances, 5),
            "precision@10": precision_at_k(all_relevances, 10),
            "mrr": mean_reciprocal_rank(all_relevances),
            "hit_rate": hit_rate(all_relevances),
            "per_item": per_item,
        }
        logger.info(
            "Evaluation done: n=%d recall@5=%.3f recall@10=%.3f mrr=%.3f hit=%.3f",
            metrics["n_queries"],
            metrics["recall@5"],
            metrics["recall@10"],
            metrics["mrr"],
            metrics["hit_rate"],
        )
        return metrics

    @staticmethod
    def format_summary(metrics: dict[str, Any]) -> str:
        """Format metrics in the standard evaluation banner."""
        lines = [
            "========================",
            "Evaluation Results",
            f"Recall@5: {metrics['recall@5']:.4f}",
            f"Recall@10: {metrics['recall@10']:.4f}",
            f"MRR: {metrics['mrr']:.4f}",
            f"Hit Rate: {metrics['hit_rate']:.4f}",
            "========================",
        ]
        return "\n".join(lines)


def run_evaluation(
    retriever: Retriever | None = None,
    qa_path: Path | None = None,
    top_k: int = TOP_K,  # noqa: ARG001 - kept for API symmetry / future use
) -> dict[str, Any]:
    """Convenience: build a default retriever if needed and evaluate.

    Args:
        retriever: Optional retriever; constructed from config when omitted.
        qa_path: Optional path to ``qa.json``.
        top_k: Unused for cutoff selection (eval always retrieves at least 10);
            retained so callers can pass ``TOP_K`` without breaking.

    Returns:
        Metrics dict from :meth:`RetrievalEvaluator.evaluate`.
    """
    _ = top_k
    if retriever is None:
        retriever = Retriever()
    return RetrievalEvaluator(retriever=retriever, qa_path=qa_path).evaluate()
