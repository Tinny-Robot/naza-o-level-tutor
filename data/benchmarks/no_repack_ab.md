# Production vs no-repack controlled A/B benchmark

Label: **representative**

The same GGUF, frozen retrieved chunks, prompts, context, sampling controls, seed, batch/ubatch, CPU threads, and llama.cpp version were used. The only production/no-repack model-runtime difference is `use_extra_bufts`.

## Scope and fairness

- Questions run: 8 of 1681
- Subject allocation: `{"chemistry": 2, "english": 2, "mathematics": 2, "physics": 2}`
- Frozen retrieval hashes matched: True
- Production/no-repack prompt hashes matched: True
- Estimated full two-arm runtime on this VM: 113.6 hours
- Estimated full three-arm runtime on this VM: 181.9 hours

## Primary comparison

| Metric | Production | No-repack | Difference |
|---|---:|---:|---:|
| Questions | 8 | 8 | 0 |
| Accuracy | 0.678 | 0.611 | -0.067 |
| Successful generations | 8 | 8 | 0 |
| Failures | 0 | 0 | 0 |
| Average generated tokens | 213.500 | 150.250 | -63.250 |
| Median generated tokens | 186.000 | 149.500 | -36.500 |
| Average generation tok/s | 5.272 | 5.841 | 0.569 |
| Median generation tok/s | 5.529 | 5.816 | 0.287 |
| Average prompt tok/s | 29.491 | 15.032 | -14.459 |
| Average TTFT seconds | 59.453 | 116.227 | 56.774 |
| Average latency seconds | 100.944 | 142.262 | 41.318 |
| Peak RSS MiB | 8730.602 | 6564.746 | -2165.855 |
| Average RSS MiB | 8716.789 | 6549.392 | -2167.397 |
| Model load seconds | 5.173 | 1.860 | -3.313 |

## Configuration table

| Configuration | Peak RSS | RAM Headroom | Accuracy | Prompt tok/s | Generation tok/s | Avg tokens | Avg latency | ADTC status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| production | 8.526 GiB | -1.526 GiB | 0.678 | 29.491 | 5.272 | 213.500 | 100.944 s | FAIL - ABOVE 7 GiB |
| no_repack | 6.411 GiB | 0.589 GiB | 0.611 | 15.032 | 5.841 | 150.250 | 142.262 s | PASS |
| no_repack_release | 6.492 GiB | 0.508 GiB | 0.611 | 14.767 | 5.524 | 150.250 | 146.251 s | PASS |

## Embedder release experiment

- Average RSS released after retrieval: 962.718 MiB
- Median RSS released after retrieval: 966.080 MiB
- Average sampled generation peak after release: 5666.469 MiB
- Process peak includes the transient period when Gemma and the reloaded embedder coexist: 6647.324 MiB
- Releasing KEmbed per question requires reloading it for the next dense retrieval, so it lowers steady generation RSS but adds reload overhead and does not lower the observed process peak in this long-lived worker.

## Per-question comparison

| ID | Pair | Category | Similarity | Keyword Δ | Token Δ | Finish reasons |
|---|---|---|---:|---:|---:|---|
| chemistry-42574_qp_gamatrain-com_hsoekt-001-80543325 | production_vs_no_repack | materially_different | 0.979 | -0.250 | +4 | stop / stop |
| chemistry-textbook_reference-formula-013-3ba3ecfb | production_vs_no_repack | materially_different | 0.959 | +0.200 | +22 | stop / stop |
| english-past_questions-000-6b19728c | production_vs_no_repack | semantically_equivalent | 0.951 | -0.125 | -17 | stop / stop |
| english-textbook_reference-008-625cec93 | production_vs_no_repack | materially_different | 0.874 | +0.000 | -196 | stop / stop |
| mathematics-42440_qp_gamatrain-com_or5aub-001-b0d77195 | production_vs_no_repack | semantically_equivalent | 0.977 | +0.000 | +27 | stop / stop |
| mathematics-textbook_2-043-1152d764 | production_vs_no_repack | semantically_equivalent | 0.914 | +0.000 | -184 | stop / stop |
| physics-42579_qp_gamatrain-com_hqpqex-001-40dcd10e | production_vs_no_repack | materially_different | 0.937 | -0.500 | -159 | stop / stop |
| physics-textbook_reference-formula-018-4d4fcef2 | production_vs_no_repack | materially_different | 0.987 | +0.143 | -3 | stop / stop |
| chemistry-42574_qp_gamatrain-com_hsoekt-001-80543325 | production_vs_no_repack_release | materially_different | 0.979 | -0.250 | +4 | stop / stop |
| chemistry-textbook_reference-formula-013-3ba3ecfb | production_vs_no_repack_release | materially_different | 0.959 | +0.200 | +22 | stop / stop |
| english-past_questions-000-6b19728c | production_vs_no_repack_release | semantically_equivalent | 0.951 | -0.125 | -17 | stop / stop |
| english-textbook_reference-008-625cec93 | production_vs_no_repack_release | materially_different | 0.874 | +0.000 | -196 | stop / stop |
| mathematics-42440_qp_gamatrain-com_or5aub-001-b0d77195 | production_vs_no_repack_release | semantically_equivalent | 0.977 | +0.000 | +27 | stop / stop |
| mathematics-textbook_2-043-1152d764 | production_vs_no_repack_release | semantically_equivalent | 0.914 | +0.000 | -184 | stop / stop |
| physics-42579_qp_gamatrain-com_hqpqex-001-40dcd10e | production_vs_no_repack_release | materially_different | 0.937 | -0.500 | -159 | stop / stop |
| physics-textbook_reference-formula-018-4d4fcef2 | production_vs_no_repack_release | materially_different | 0.987 | +0.143 | -3 | stop / stop |

## Statistical differences

### no_repack

- Accuracy difference: -0.067
- RAM reduction: 24.81%
- Generation speed difference: 10.791%
- Prompt speed difference: -49.030%
- Latency difference: 40.932%
- Answers different: 100.0%
- Same or semantically equivalent: 37.5%
- Categories: `{"materially_different": 5, "semantically_equivalent": 3}`

### no_repack_release

- Accuracy difference: -0.067
- RAM reduction: 23.86%
- Generation speed difference: 4.781%
- Prompt speed difference: -49.927%
- Latency difference: 44.883%
- Answers different: 100.0%
- Same or semantically equivalent: 37.5%
- Categories: `{"materially_different": 5, "semantically_equivalent": 3}`

## Reproduction

```bash
cd /home/ubuntu/O-Level/O-Level
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python scripts/benchmark_no_repack_ab.py --limit 8 --label representative
```

## Recommendation

**DO NOT ADOPT**

Measured quality or reliability degradation is too large.

No production configuration was changed.
