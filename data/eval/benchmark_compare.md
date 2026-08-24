# Retrieval benchmark: before vs after corpus expansion

| Metric | Before (474 chunks, 315 QA) | After (17709 chunks, full QA) | Delta |
|---|---:|---:|---:|
| n_queries | 315 | 1681 | - |
| index_chunks | 474 | 17709 | - |
| recall@5 | 0.9524 | 0.9905 | +0.0381 |
| recall@10 | 0.9587 | 0.9952 | +0.0365 |
| mrr | 0.9364 | 0.9722 | +0.0358 |
| hit_rate | 0.9587 | 0.9952 | +0.0365 |
| precision@5 | 0.8463 | 0.9438 | +0.0975 |
| latency_mean_ms | 377.8 | 716.0 | +338.2 |

Notes:
- Before: old 4-subject index.
- After: full SS + pq-pdfs + Reference corpus; expanded grounded qa.json.
- Absolute recall may drop as the corpus grows (harder retrieval); compare with that in mind.
