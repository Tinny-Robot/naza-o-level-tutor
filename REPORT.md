# Technical Report — Naza: Offline Nigerian O-Level STEM Tutor

**Team ID:** REPLACE_WITH_YOUR_ADTC_TEAM_ID  
**Domain:** math_scientific_reasoning  
**Model:** gemma-4-E4B-it-Q4_K_M (llama.cpp / GGUF Q4_K_M)  
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

- **Base model:** Google **Gemma 4 E4B-it** (edge-scale instruct model, ~4B
  effective parameters), run through **llama.cpp** only (ADTC requirement).
- **Quantization:** **GGUF Q4_K_M** — balances answer quality against the
  **8 GB RAM** laptop profile. Heavier quants (Q5/Q6/Q8) risk memory pressure
  once the OS and optional retrieval stack share RAM; lighter quants degrade
  STEM step quality too aggressively for exam tutoring.
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

## Fine-tuning

**Why:** General instruct models under-serve **Hausa** and often drift from
**WAEC / NECO** syllabus language. Curriculum-aligned fine-tuning teaches
exam-style tutoring tone and subject vocabulary for Chemistry, Physics,
Mathematics, and English Language.

**Data:** Instruction pairs exported from the local practice bank
(`data/eval/qa.json`) and aligned with the same O-Level corpus used for RAG.
Records include English outputs and Hausa-targeted fields (see
`finetune/data/schema.md`).

**Method:** LoRA / QLoRA on a Gemma-class instruct checkpoint. Hyperparameters
and prompt templates live in `finetune/configs/lora_hausa_curriculum.yaml`.
Dataset export and training entrypoints are under `finetune/scripts/`.

**Scope:** Fine-tuning improves language fluency and curriculum alignment.
**RAG still grounds study answers** in FAISS-retrieved chunks at runtime — it
does not replace retrieval.

**ADTC submission:** The GGUF judges download via `download_model.sh` is the
**base quant**. Fine-tuning methodology, config, and reproducible scripts are
documented under `finetune/` for inspection.

---

## Constraints

- **Hardware target:** 4 vCPU, **8 GB RAM**, integrated GPU only; pure CPU
  inference via llama.cpp for evaluation.
- **Offline evaluation:** Zero outbound network during profiling. Weights are
  fetched only by `bash download_model.sh` before the run.
- **Connectivity reality:** Students may have intermittent data — the product
  design keeps corpus, embeddings, and GGUF on disk.
- **Data:** Local textbooks, syllabi, and past-question style items; no cloud
  LLM calls in the demo path (`HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1`).

---

## Benchmarks

Self-reported on the development machine (not official ADTC profiler scores):

| Metric | Value |
|---|---|
| Machine | Linux x86_64 cloud/dev host (CPU llama.cpp) |
| GGUF on disk | ~4.7–5.3 GB (`gemma-4-E4B-it-Q4_K_M.gguf`) |
| Quantization | GGUF Q4_K_M |
| Runtime | llama.cpp (Python bindings in app; ADTC uses llama.cpp) |
| Typical tutor reply | Study-mode RAG + generation (app); profiler uses bare GGUF |
| Thermal throttling | Not profiled on ADTC official laptop — run `adtc-profiler` locally |

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
| `finetune/` | Hausa + curriculum fine-tuning (dataset, config, scripts) |
| `app/`, `desktop/`, `launch.sh` | Full offline tutor product (demo beyond bare GGUF) |

---

## African use-case claim

`african_alpha_claim: true` — the load-bearing pairing is **education** for
Nigerian WAEC/NECO students, with **Hausa** in `language_scope`, offline
operation for low-connectivity contexts, and syllabus-grounded STEM tutoring
rather than a generic coding assistant.
