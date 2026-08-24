# ADTC 2026 inference memory experiment

Date: 2026-08-12

## Scope and validity

This is a subprocess-isolated pilot over one deterministic, long-form item
selected from the unchanged 1,681-item `data/eval/qa.json`. Every configuration
received the same question, retrieved chunks, prompt templates, sampling
controls, and RAG settings.

The full matrix is supported by the benchmark script, but was not completed in
this run. The baseline item took 187 seconds after loading; extrapolation puts
one full 1,681-question configuration at roughly 87 hours and the complete
matrix at several weeks on this host.

The measured host is not the stated 8 GB ADTC laptop. It is a KVM VM with an
Intel Xeon Platinum 8175M, 8 logical CPUs, and 30.98 GiB RAM. Peak RSS remains
useful for the 7 GiB qualification gate, but speed must be repeated on the
actual competition laptop before a production decision.

## Current production configuration

- Model: `models/gemma-4-E4B-it-Q4_K_M.gguf`
- Model size: 4,977,171,584 bytes (4.635 GiB)
- Quantization: GGUF Q4_K_M, `general.file_type=15`
- Backend: `llama-cpp-python 0.3.34`, bundled llama.cpp commit `e3546c794`
- CPU-only: `n_gpu_layers=0`
- Context: 4096
- Batch and ubatch: 512 and 512
- Threads: 7
- Mmap: already enabled by the installed llama.cpp binding default
- Mlock: already disabled by the installed binding default
- Flash Attention: enabled and active in the current build
- SWA full cache: disabled
- KV cache: F16 K and F16 V
- Sampling: temperature 0.1; benchmark controls retain default top-p 0.95,
  top-k 40, min-p 0.05, and add deterministic seed 2026 to every run
- RAG: dense FAISS, KEmbed-naija-v3, top-k 5, unchanged 3,000-token context
  budget, unchanged prompts and citation construction

The production wrapper does not explicitly pass mmap, mlock, batch, ubatch, or
KV types. The installed binding defaults therefore apply. The audit verified
the active context parameters after model creation rather than assuming them.

## Current bottleneck

The primary bottleneck is not the KV cache. Before generation, the embedding
model uses about 806 MiB and loading the GGUF raises RSS to about 7,888 MiB.
Loading the retriever brings ready RSS to about 7,987 MiB. The first long RAG
generation then reaches 8,701 MiB (8.497 GiB).

Because llama.cpp already uses mmap, repeating the mmap configuration produces
the same memory footprint. Once inference touches the mapped model pages, they
count in process RSS. Q8/Q4 KV quantization and smaller context save only tens
of MiB because model/runtime-repack memory plus the embedding model dominate.

## Results

| Configuration | Accuracy | Peak RSS | Headroom | Gen tok/s | Prompt tok/s | TTFT | Latency | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Baseline | 0.375 | 8.497 GiB | -1.497 GiB | 4.900 | 30.507 | 81.570 s | 187.282 s | FAIL |
| Mmap | 0.375 | 8.498 GiB | -1.498 GiB | 4.402 | 25.044 | 99.361 s | 216.925 s | FAIL |
| Mmap + Q8 KV | 0.125 | 8.452 GiB | -1.452 GiB | 5.175 | 23.108 | 107.698 s | 125.659 s | FAIL |
| Mmap + Q4 KV | 0.125 | 8.418 GiB | -1.418 GiB | 5.291 | 24.693 | 100.774 s | 128.481 s | FAIL |
| Mmap + 4096 context | 0.375 | 8.497 GiB | -1.497 GiB | 4.535 | 27.706 | 89.816 s | 203.940 s | FAIL |
| Mmap + 3072 context | 0.375 | 8.478 GiB | -1.478 GiB | 4.435 | 27.115 | 91.779 s | 208.413 s | FAIL |
| Mmap + 2048 context | 0.000 | 8.345 GiB | -1.345 GiB | n/a | n/a | n/a | 0.651 s | FAILED: prompt too large |
| Best measured combined (Q4, 4096) | 0.125 | 8.419 GiB | -1.419 GiB | 5.495 | 24.688 | 100.794 s | 127.472 s | FAIL |

Accuracy is mean recall of each evaluation item's existing
`expected_keywords`. Exact match was zero for the long-form question. The
baseline processed 2,488 prompt tokens and generated 511 tokens.

## Relative changes from baseline

| Configuration | RAM reduction | Speed change | Accuracy change |
|---|---:|---:|---:|
| Mmap | -0.003% | -10.16% | 0.0 pp |
| Q8 KV | 0.530% | +5.61% | -25.0 pp |
| Q4 KV | 0.938% | +7.97% | -25.0 pp |
| 3072 context | 0.225% | -9.48% | 0.0 pp |
| 2048 context | 1.789% | failed | -37.5 pp |
| Best combined | 0.927% | +12.14% | -25.0 pp |

The identical baseline/mmap pair varied materially in speed despite identical
settings. This demonstrates that one-question speed deltas are noisy and must
not be treated as production-grade evidence.

## Decision

Do not adopt any tested configuration in production yet.

- Mmap is already enabled, so there is no new mmap optimization to adopt.
- Q8/Q4 KV cache reduces peak RSS by less than 1% and remains about 1.4 GiB
  above the competition limit.
- The pilot answer score dropped with quantized KV. A full evaluation is needed
  to determine whether this is systematic or sample noise.
- A 3072 context does not materially reduce memory.
- A 2048 context is incompatible with the unchanged RAG prompt for this item.
- No tested configuration qualifies under the 7 GiB limit.

## Reproduction

Run the exact pilot matrix:

```bash
cd /home/ubuntu/O-Level/O-Level
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python scripts/benchmark_inference.py --config all --limit 1
```

Run the full unchanged evaluation set:

```bash
cd /home/ubuntu/O-Level/O-Level
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python scripts/benchmark_inference.py --config all
```

Reproduce the best measured combined pilot directly after the component runs:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python scripts/benchmark_inference.py --config best --limit 1
```

## Next investigation

The next experiment should target the dominant resident components rather than
the KV cache: isolate the embedding model from the generation process, measure
runtime tensor repacking/model buffers, and test whether the application can
release or move the embedder to a separate process before generation. This must
remain a new isolated experiment because it changes process architecture and
was explicitly outside the scope of this benchmark.

Also restore the missing `app/evaluation/loader.py` source before relying on
the legacy `scripts/evaluate.py`; only compiled cache files remain, so that
entry point currently fails from source. The new benchmark reads the existing
JSON directly and does not modify it.
