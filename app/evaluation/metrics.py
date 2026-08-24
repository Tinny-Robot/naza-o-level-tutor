"""Retrieval quality metrics with keyword/subject-based relevance.

Relevance judgment
------------------
A retrieved document is considered **relevant** to an evaluation item when
**either** of the following holds (case-insensitive):

1. **Subject match** - the document's ``metadata["subject"]`` equals the
   item's ``subject`` (after strip/lower), **and** at least one of:

   - the item's ``expected_keywords`` is empty (subject alone is enough), or
   - at least one expected keyword appears as a substring in the concatenation
     of document ``text``, ``metadata["topic"]``, and ``metadata["subject"]``.

2. **Keyword-only match** - when the item has a non-empty
   ``expected_keywords`` list, a document is also relevant if **any** keyword
   overlaps the concatenated text/topic/subject fields, even if the subject
   differs.  (This covers cross-listed or mis-tagged chunks.)

In short: subject match with optional keyword confirmation, **or** keyword
overlap in text/topic/subject.  Documented here so evaluator and tests share
one definition.

Metric definitions
------------------
All metrics take a list of per-query binary relevance lists
``relevances[q][i]`` where ``i`` is the rank (0-based) among retrieved docs.

* **Recall@K** - fraction of queries for which at least one relevant document
  appears in the top-K results.  Equivalent to Hit Rate@K when each query is
  treated as having a binary "found / not found" success criterion (we do not
  require a fixed ground-truth set size beyond the relevance labels of the
  retrieved pool).  Formally::

      Recall@K = (1/|Q|) * sum_q 1[ exists i < K : relevances[q][i] ]

* **Precision@K** - average, over queries, of the fraction of the top-K
  retrieved documents that are relevant::

      Precision@K = (1/|Q|) * sum_q (#{i < K : relevances[q][i]} / K)

* **MRR** (Mean Reciprocal Rank) - average of ``1/rank`` of the first
  relevant document (rank is 1-based); 0 if none in the list::

      MRR = (1/|Q|) * sum_q  1/rank_q   (or 0 if no hit)

* **Hit Rate** - same as Recall@K for the full retrieved list length used
  during evaluation (typically K=10): fraction of queries with ≥1 relevant
  doc in the returned results.
"""

from __future__ import annotations

from typing import Any, Sequence


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def is_relevant(
    retrieved: dict[str, Any],
    *,
    subject: str,
    expected_keywords: Sequence[str],
) -> bool:
    """Return whether ``retrieved`` is relevant under the judgment rule above.

    Args:
        retrieved: A retriever result ``{"score", "text", "metadata"}``.
        subject: Expected subject from the eval item.
        expected_keywords: Keywords from the eval item.

    Returns:
        ``True`` if the document matches subject and/or keyword rules.
    """
    metadata = retrieved.get("metadata") or {}
    text = retrieved.get("text") or ""
    topic = str(metadata.get("topic", ""))
    doc_subject = str(metadata.get("subject", ""))
    haystack = _norm(f"{text} {topic} {doc_subject}")

    keywords = [k for k in expected_keywords if k and str(k).strip()]
    keyword_hit = any(_norm(k) in haystack for k in keywords) if keywords else False
    subject_hit = _norm(doc_subject) == _norm(subject) and bool(subject.strip())

    if subject_hit and (not keywords or keyword_hit):
        return True
    if keywords and keyword_hit:
        return True
    return False


def label_relevances(
    results: Sequence[dict[str, Any]],
    *,
    subject: str,
    expected_keywords: Sequence[str],
) -> list[bool]:
    """Label each retrieved result as relevant or not."""
    return [
        is_relevant(r, subject=subject, expected_keywords=expected_keywords)
        for r in results
    ]


def recall_at_k(relevances: Sequence[Sequence[bool]], k: int) -> float:
    """Fraction of queries with ≥1 relevant document in the top-``k``.

    See module docstring for the full definition.  Queries with an empty
    relevance list contribute 0.
    """
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")
    if not relevances:
        return 0.0
    hits = 0
    for labels in relevances:
        top = list(labels)[:k]
        if any(top):
            hits += 1
    return hits / len(relevances)


def precision_at_k(relevances: Sequence[Sequence[bool]], k: int) -> float:
    """Mean fraction of relevant documents among the top-``k`` per query."""
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")
    if not relevances:
        return 0.0
    total = 0.0
    for labels in relevances:
        top = list(labels)[:k]
        # Pad mentally: missing ranks count as non-relevant.
        relevant_count = sum(1 for flag in top if flag)
        total += relevant_count / k
    return total / len(relevances)


def mean_reciprocal_rank(relevances: Sequence[Sequence[bool]]) -> float:
    """Mean reciprocal rank of the first relevant document per query."""
    if not relevances:
        return 0.0
    total = 0.0
    for labels in relevances:
        rr = 0.0
        for rank, flag in enumerate(labels, start=1):
            if flag:
                rr = 1.0 / rank
                break
        total += rr
    return total / len(relevances)


def hit_rate(relevances: Sequence[Sequence[bool]]) -> float:
    """Fraction of queries with at least one relevant document retrieved.

    Equivalent to :func:`recall_at_k` with ``k`` equal to each list's full
    length when all lists share the same length; implemented as "any hit
    anywhere in the returned list" so shorter lists are handled safely.
    """
    if not relevances:
        return 0.0
    hits = sum(1 for labels in relevances if any(labels))
    return hits / len(relevances)
