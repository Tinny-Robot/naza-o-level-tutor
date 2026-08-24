# Inference benchmark

The benchmark runs each llama.cpp configuration in a fresh subprocess and
records Linux `VmRSS`/`VmHWM`, llama.cpp performance counters, deterministic
answer quality, prompt tokens, generated tokens, TTFT, and load time.

Production code, prompts, retrieval settings, the FAISS index, and
`data/eval/qa.json` remain unchanged.

## Commands

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python scripts/benchmark_inference.py --config baseline

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python scripts/benchmark_inference.py --config mmap

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python scripts/benchmark_inference.py --config mmap_kv

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python scripts/benchmark_inference.py --config mmap_context_3072

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python scripts/benchmark_inference.py --config all
```

The default uses all 1,681 questions. For a reproducible pilot, pass
`--limit N`; selection is evenly spaced and deterministic from the unchanged
evaluation file.

## Outputs

- `<config>.json`: machine-readable metrics and per-question details
- `<config>.md`: human-readable configuration report
- `summary.json`: relative changes from baseline
- `summary.md`: ADTC-oriented comparison table
- `report.md`: audit findings and recommendation

## Memory breakdown diagnostic

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python scripts/benchmark_memory_breakdown.py --experiment all
```

This creates `memory_breakdown.json`, `memory_breakdown.md`, per-experiment
JSON files, and verbose llama.cpp allocation logs. The `no_repack` experiment
sets the installed llama.cpp model parameter `use_extra_bufts=False` only in
the diagnostic subprocess; production configuration remains unchanged.
