# Technical Report - Naza: Offline Nigerian O-Level STEM Tutor

**Team ID:** `naza`
**Devpost:** https://devpost.com/software/naza
**Domain:** math_scientific_reasoning
**Model:** gemma-4-E4B-it-IQ3_M (llama.cpp / GGUF IQ3_M)
**Languages:** English (`en`), Hausa (`ha`)

---

## Problem

Millions of Nigerian secondary students prepare for **WAEC** and **NECO** under
unreliable connectivity and limited access to specialist tutors. Generic cloud
chatbots often invent syllabus content, ignore local exam style, and under-serve
**Hausa**-preferring learners.

**Naza** is an offline-first laptop tutor for O-Level **Mathematics, Physics,
Chemistry, and English Language**. It targets African students who need
exam-aligned explanations on consumer hardware, without calling cloud APIs at
inference time.

---

## Design Decisions

- **Base model:** Google **Gemma 4 E4B-it** (about 4.5B effective parameters;
  7.52B tensors reported by the profiler), run through **llama.cpp** only.
- **Quantization:** **GGUF IQ3_M** - selected after Q4_K_M exceeded the desired
  memory headroom. IQ3_M reduces the model artifact to about 4.71 GB while
  retaining better low-bit quality than similarly sized conventional Q3
  variants. This is a deliberate trade-off for an **8 GB RAM** laptop.
- **Grounding (product layer):** Outside the profiler-only GGUF path, the full
  Naza app adds **local FAISS RAG** over Nigerian O-Level materials and a
  curated `data/eval/qa.json` practice bank so study answers stay syllabus-
  oriented. Embeddings use a local **KEmbed-naija-v3** snapshot (no HF download
  at runtime).
- **Language:** UI and system prompts support **English and Hausa**.
- **Alternatives considered:** Larger 7B+ instruct models at Q4 often exceed
  comfortable headroom on 8 GB with context; tiny sub-1B models struggle with
  multi-step Physics/Chemistry reasoning.

---

## Adaptation and fine-tuning status

General instruct models under-serve **Hausa** and often drift from **WAEC /
NECO** syllabus language. Naza's submitted GGUF is an unmodified quantized base
model; the competition artifact does not claim weight-level fine-tuning.

The repository includes a reproducible LoRA/QLoRA pipeline and instruction data
exported from the local practice bank
(`data/eval/qa.json`) and aligned with the same O-Level corpus used for RAG.
Records include English outputs and Hausa-targeted fields (see
`finetune/data/schema.md`).

Hyperparameters and prompt templates live in
`finetune/configs/lora_hausa_curriculum.yaml`; dataset export and training
entrypoints are under `finetune/scripts/`. These files document planned and
reproducible weight adaptation, but no adapter is merged into the submitted
GGUF.

The current product adaptation is therefore the fully offline application
layer: local FAISS retrieval, curriculum data, language-aware prompts, and the
curated practice bank. The bare GGUF profiler intentionally measures only the
submitted model artifact, without RAG.

---

## Constraints

- **Hardware target:** 4 vCPU, **8 GB RAM**, integrated GPU only; pure CPU
  inference via llama.cpp for evaluation.
- **Offline evaluation:** Zero outbound network during profiling. Weights are
  fetched only by `bash download_model.sh` before the run.
- **Connectivity reality:** Students may have intermittent data - the product
  design keeps corpus, embeddings, and GGUF on disk.
- **Data:** Local textbooks, syllabi, and past-question style items; no cloud
  LLM calls in the demo path (`HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1`).

---

## Benchmarks

Measured with `adtc-profiler 0.1.0` in participant mode on August 24, 2026.
Accuracy was intentionally skipped for the required repository smoke test.

| Metric | Value |
|---|---|
| Machine | Intel Xeon Platinum 8175M, Ubuntu 24.04, CPU-only llama.cpp |
| GGUF on disk | 4,714,697,408 bytes (`gemma-4-E4B-it-IQ3_M.gguf`) |
| Quantization | GGUF IQ3_M |
| Generation throughput | 3.61 tokens/second |
| First-token latency | 110,279.04 ms |
| Peak RSS | 5,006.40 MB |
| Steady-state RSS | 4,815.40 MB |
| Parameter check | 7,518,069,290 measured; 7.5B claimed; match passes |
| Thermal throttling | Not detected |

The previous Q4_K_M artifact measured 4.53 tokens/second and 7,178.95 MB peak
RSS on the same host. IQ3_M sacrifices throughput and latency to recover about
2.17 GB of peak memory headroom, which is the safer trade-off for the required
8 GB laptop target. These figures are machine-specific and must be rechecked on
the final participant laptop.

Re-measure on your 8 GB laptop before submit:

```bash
bash download_model.sh
pip install "git+https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler.git"
adtc-profiler run --submission . --mode participant --output submission.json --skip-accuracy
```

---

## Repository map (for judges)

| Path | Role |
|---|---|
| `metadata.json` | ADTC team / domain / 2 test prompts / model meta |
| `download_model.sh` | Public download of GGUF → `model/` |
| `REPORT.md` | This writeup |
| `model/` | Downloaded `.gguf` (gitignored) |
| `finetune/` | Hausa + curriculum training pipeline (data, config, scripts) |
| `app/`, `desktop/`, `launch.sh` | Full offline tutor product (demo beyond bare GGUF) |

---

## African use-case claim

`african_alpha_claim: true` - the load-bearing pairing is **education** for
Nigerian WAEC/NECO students, with **Hausa** in `language_scope`, offline
operation for low-connectivity contexts, and syllabus-grounded STEM tutoring
rather than a generic coding assistant.
