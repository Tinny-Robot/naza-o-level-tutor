"""Retrieval evaluation: Q&A loading, relevance metrics, and evaluator."""

from app.evaluation.evaluator import RetrievalEvaluator, run_evaluation
from app.evaluation.loader import load_qa_dataset
from app.evaluation.metrics import (
    hit_rate,
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
)

__all__ = [
    "RetrievalEvaluator",
    "hit_rate",
    "load_qa_dataset",
    "mean_reciprocal_rank",
    "precision_at_k",
    "recall_at_k",
    "run_evaluation",
]
