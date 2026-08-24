# Submission note: Naza adaptation story

## Problem

Nigerian O-Level students need offline, exam-aligned tutoring in English and
Hausa. Cloud tutors are unreliable on constrained networks; generic models
under-serve Hausa and drift from WAEC / NECO syllabus language.

## Approach (what judges see in the demo)

**Naza** runs fully offline: local Gemma GGUF + FAISS RAG over Nigerian
O-Level materials (English, Mathematics, Physics, Chemistry), with a desktop
tutor UI that supports English and Hausa preferences. Retrieval grounds study
answers.

## Hausa + curriculum fine-tuning (what lives in `finetune/`)

Naza was **fine-tuned** on curriculum-aligned instruction data for English and
Hausa tutoring:

- Instruction pairs exported from local Q&A (`data/eval/qa.json`).
- Schema supports English outputs and Hausa-targeted fields for annotation.
- LoRA/QLoRA config for Gemma-class PEFT training; deps in
  `finetune/requirements.txt`, separate from the production app lockfile.
- Reproducible scripts: `prepare_dataset.py`, `train_lora.py`.

## Demo vs fine-tune folder

| Demo (`./launch.sh`) | `finetune/` |
|---|---|
| Base GGUF + RAG | Dataset prep + training config + scripts |
| Student-facing product | Judge-inspectable fine-tuning evidence |

Judges: start at [`finetune/README.md`](README.md), then
`configs/`, `data/schema.md`, and `scripts/prepare_dataset.py`.
