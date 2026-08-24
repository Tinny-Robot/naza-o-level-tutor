# Offline fine-tuning (optional)

**This folder is not part of the production deploy.** Naza at runtime uses the
base Gemma GGUF via llama.cpp plus local RAG grounding. Nothing under
`finetune/` is loaded by `./launch.sh`, Docker Compose, or
`app/generation/llm.py`.

This package documents an **optional offline LoRA / QLoRA adaptation pipeline**
aimed at Hausa-language tutoring and Nigerian O-Level (WAEC / NECO) curriculum
alignment. Judges can inspect methodology, data preparation, and config
templates here without changing the demo model path.

## Motivation

- **Hausa is under-resourced** in general-purpose LLM instruction data relative
  to English. Students who prefer Hausa still need exam-accurate Chemistry,
  Physics, Mathematics, and English Language explanations.
- **Curriculum alignment** matters more than fluent chatter: answers should
  track Nigerian secondary syllabi and past-question style, not generic web text.
- **Offline-first**: adaptation data comes from the local corpus and
  `data/eval/qa.json`. Training (when run) happens offline; the demo never
  calls cloud training APIs.

## Method (proposed)

1. Export instruction pairs from local curriculum Q&A (see
   `scripts/prepare_dataset.py`).
2. Optionally annotate / translate assistant turns into Hausa while keeping
   scientific terms in English where clearer (same policy as
   `app/i18n/language.py`).
3. Train a **LoRA or QLoRA** adapter on a Gemma-class instruct checkpoint using
   the YAML template in `configs/lora_hausa_curriculum.yaml`.
4. Keep adapters under `artifacts/adapters/` for offline evaluation only.
   Production continues on the base GGUF unless an operator **explicitly**
   merges / swaps weights outside this repo's launch path.

Production RAG still grounds study answers in FAISS-retrieved chunks. An
adapter would only change generation style / language fluency; it does not
replace retrieval.

## Relation to deployed Naza

| Piece | Production demo | This folder |
|---|---|---|
| Model | Local Gemma GGUF (`MODEL_PATH`) | Optional LoRA/QLoRA adapter (not wired) |
| Grounding | Offline RAG over O-Level corpus | Uses same local Q&A as *training* source |
| Language | Prompt instruction (EN / Hausa UI) | Curriculum + Hausa adaptation data |
| Launch | `./launch.sh` / Compose | Separate venv + `finetune/requirements.txt` |

If README or pitch text says we "fine-tune", read it as: **we ship a
reproducible adaptation pipeline and curriculum-aligned dataset export**. A
full GPU train is operator-run; this machine may only hold configs, scripts,
and sample exports - not fabricated wandb runs or fake weight files.

## Layout

```
finetune/
├── README.md                 # This file
├── SUBMISSION.md             # Short judge blurb
├── requirements.txt          # Training-only deps (not in app pyproject)
├── configs/
│   └── lora_hausa_curriculum.yaml
├── data/
│   ├── schema.md             # JSONL record contract
│   └── exports/              # Sample / full JSONL (large dumps gitignored)
├── scripts/
│   ├── prepare_dataset.py    # Export instruction pairs (runnable)
│   └── train_lora.py         # Training entrypoint skeleton
└── artifacts/
    └── adapters/             # Place trained adapters here (not auto-loaded)
```

## Reproducibility (dataset export)

From the project root (stdlib only; no training deps required):

```bash
# Small inspectable sample (checked into exports/ optionally as sample_*.jsonl)
python finetune/scripts/prepare_dataset.py --limit 20 --out finetune/data/exports/sample_instruction_pairs.jsonl

# Full export from data/eval/qa.json (gitignored *.jsonl)
python finetune/scripts/prepare_dataset.py --out finetune/data/exports/full_instruction_pairs.jsonl
```

See `data/schema.md` for field definitions (English + Hausa-targeted columns).

## Reproducibility (training - optional GPU machine)

1. Create a **separate** venv; do not add these packages to the app lockfile:

   ```bash
   python -m venv .venv-finetune
   source .venv-finetune/bin/activate
   pip install -r finetune/requirements.txt
   ```

2. Place a Gemma-class instruct base checkpoint (Hugging Face format for PEFT
   training - not the production GGUF) where the config points.
3. Export the full JSONL as above; run human Hausa review on `output_ha` where
   needed.
4. Edit `configs/lora_hausa_curriculum.yaml` paths and hyperparameters.
5. Run:

   ```bash
   python finetune/scripts/train_lora.py --config finetune/configs/lora_hausa_curriculum.yaml
   ```

   The skeleton documents the intended PEFT entrypoint. It will refuse to
   pretend a train completed if heavy deps or data are missing.

6. Save adapters under `finetune/artifacts/adapters/<run_id>/`. To use them in a
   **non-default** offline experiment, merge to GGUF / load with PEFT yourself;
   do not change `launch.sh` or `MODEL_PATH` unless you intentionally fork
   production.

## What is intentionally absent

- No fake completed training metrics or wandb run IDs.
- No binary adapter weights pretending a full train ran here.
- No change to Docker production model mounts or the llama.cpp singleton.
