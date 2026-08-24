# Memory breakdown diagnostic

All measurements use Linux `/proc/self/status` and `/proc/self/smaps_rollup` in fresh processes. USS is private clean + private dirty memory; PSS proportionally attributes shared mappings.

## Baseline stages

| Stage | RSS MiB | Delta previous | Delta baseline | PSS MiB | USS MiB |
|---|---:|---:|---:|---:|---:|
| 01_process_start | 21.5 | +0.0 | +0.0 | 13.6 | 10.8 |
| 02_after_application_imports | 50.9 | +29.4 | +29.4 | 41.6 | 38.6 |
| 03_after_embedding_model | 804.5 | +753.6 | +783.1 | 794.8 | 791.8 |
| 04_after_faiss_and_chunks | 879.0 | +74.5 | +857.5 | 869.3 | 866.2 |
| 04b_after_rag_retrieval | 1470.7 | +591.7 | +1449.2 | 1460.9 | 1457.9 |
| 05_after_llama_cpp_initialization | 1473.5 | +2.8 | +1452.0 | 1463.8 | 1460.7 |
| 06_after_gguf_model | 8479.2 | +7005.7 | +8457.8 | 8469.5 | 8466.4 |
| 07_after_inference_context | 8583.5 | +104.2 | +8562.0 | 8573.7 | 8570.6 |
| 07b_after_llama_batch | 8583.5 | +0.0 | +8562.0 | 8573.7 | 8570.6 |
| 07c_after_high_level_llama | 8585.2 | +1.7 | +8563.7 | 8575.4 | 8572.3 |
| 08_before_generation | 8585.2 | +0.0 | +8563.7 | 8575.4 | 8572.3 |
| 09_after_generation | 8707.1 | +121.9 | +8685.6 | 8697.3 | 8694.3 |
| 10_peak_during_generation | 8707.1 | +0.0 | +8685.6 | 8697.3 | 8694.3 |

## Component estimates

| Component | RSS MiB | PSS MiB | USS MiB | Measurement method |
|---|---:|---:|---:|---|
| Python + application imports | +29.4 | +27.9 | +27.8 | stage delta: 01_process_start -> 02_after_application_imports |
| KEmbed-naija-v3 | +753.6 | +753.3 | +753.2 | stage delta: 02_after_application_imports -> 03_after_embedding_model |
| FAISS index + chunks | +74.5 | +74.5 | +74.5 | stage delta: 03_after_embedding_model -> 04_after_faiss_and_chunks |
| First embedding query working set | +591.7 | +591.6 | +591.7 | stage delta: 04_after_faiss_and_chunks -> 04b_after_rag_retrieval |
| llama.cpp import/runtime | +2.8 | +2.9 | +2.8 | stage delta: 04b_after_rag_retrieval -> 05_after_llama_cpp_initialization |
| GGUF model load | +7005.7 | +7005.7 | +7005.7 | stage delta: 05_after_llama_cpp_initialization -> 06_after_gguf_model |
| Inference context | +104.2 | +104.2 | +104.2 | stage delta: 06_after_gguf_model -> 07_after_inference_context |
| Llama batch | +0.0 | +0.0 | +0.0 | stage delta: 07_after_inference_context -> 07b_after_llama_batch |
| Python high-level buffers | +1.7 | +1.7 | +1.7 | stage delta: 07b_after_llama_batch -> 07c_after_high_level_llama |
| Generation working set | +121.9 | +121.9 | +121.9 | stage delta: 08_before_generation -> 10_peak_during_generation |

## Experiment comparison

| Experiment | Repack | Batch | Ubatch | Peak RSS | Headroom vs 7 GiB | Peak PSS | Peak USS | Gen tok/s | Keyword score |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | True | 512 | 512 | 8707.1 | -1539.1 | 8697.3 | 8694.3 | 4.533 | 0.375 |
| release_embedder | True | 512 | 512 | 7854.4 | -686.4 | 7844.8 | 7841.7 | 4.046 | n/a |
| release_embedder_faiss | True | 512 | 512 | 7741.4 | -573.4 | 7731.7 | 7728.6 | 3.715 | n/a |
| batch_256 | True | 256 | 256 | 8636.6 | -1468.6 | 8626.9 | 8623.9 | 5.181 | n/a |
| ubatch_128 | True | 512 | 128 | 8610.4 | -1442.4 | 8600.2 | 8596.8 | 5.201 | n/a |
| batch_128 | True | 128 | 128 | 8605.4 | -1437.4 | 8595.3 | 8591.9 | 4.776 | n/a |
| no_repack | False | 512 | 512 | 6541.3 | +626.7 | 6531.6 | 6528.4 | 4.807 | 0.125 |
| release_embedder_no_repack | False | 512 | 512 | 5689.1 | +1478.9 | 5679.4 | 5676.4 | 4.963 | n/a |

## llama.cpp reported allocations

- Tensors: **720**
- CPU mapped model buffer: **4731.51 MiB**
- CPU repack model buffer: **2165.62 MiB**
- Total model buffers: **6897.13 MiB**
- KV buffers: **104.00 MiB**
- Reserved compute buffer: **527.02 MiB**

## Findings

1. Largest measured component: **GGUF model load**, 7005.7 MiB RSS by stage delta.
2. KEmbed load contribution: **753.6 MiB RSS**, 753.3 MiB PSS, 753.2 MiB USS.
3. The first embedding query adds another **591.7 MiB RSS** of framework/allocator working memory.
4. KEmbed actually returned after reference clearing, GC, and malloc trim: **897.7 MiB RSS**.
5. Additional FAISS/chunk release: **110.0 MiB RSS**.
6. Baseline CPU repacking duplicates **2165.62 MiB** beyond the 4731.51 MiB mapped weights.
7. No-repack peak: **6541.3 MiB** (6.388 GiB), with **626.7 MiB headroom** under 7 GiB.
8. Releasing KEmbed plus no-repack peaks at **5689.1 MiB** (5.556 GiB).
9. The embedder is required for every new dense query. Releasing it after one retrieval is safe only when that request's retrieved chunks are retained and no further retrieval occurs in the same process without reloading the model.
10. No-repack is a diagnostic candidate, not a production recommendation. It must pass the full accuracy and speed benchmark because changing tensor buffer layout can alter numerical output.

## Reproduce

```bash
cd /home/ubuntu/O-Level/O-Level
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python scripts/benchmark_memory_breakdown.py --experiment all
```
