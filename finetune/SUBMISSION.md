# Submission note: Naza adaptation story

## Problem

Nigerian O-Level students need offline, exam-aligned tutoring in English and
Hausa. Cloud tutors are unreliable on constrained networks; generic models
under-serve Hausa and drift from WAEC / NECO syllabus language.

## Approach (what judges see in the demo)

**Naza** runs fully offline: local Gemma GGUF + FAISS RAG over Nigerian
O-Level materials (English, Mathematics, Physics, Chemistry), with a desktop
tutor UI that supports English and Hausa preferences. Retrieval grounds study
answers; the base GGUF is unchanged for the demo.

## Hausa + curriculum adaptation (what lives in `finetune/`)

Separately from launch, this repo includes an **optional offline LoRA / QLoRA
pipeline**:

- Export instruction pairs from local curriculum Q&A (`data/eval/qa.json`).
- Schema supports English outputs and Hausa-targeted fields for annotation.
- Config template for Gemma-class PEFT training; deps stay in
  `finetune/requirements.txt`, not the production app lockfile.
- Adapter slot under `finetune/artifacts/adapters/` - **not loaded by default**.

## Demo vs fine-tune folder

| Demo (`./launch.sh`) | `finetune/` |
|---|---|
| Base GGUF + RAG | Dataset prep + train skeleton |
| Student-facing product | Judge-inspectable methodology |
| No adapter auto-load | Place adapters here only if you train |

Judges: start at [`finetune/README.md`](README.md), then
`configs/`, `data/schema.md`, and `scripts/prepare_dataset.py`.
