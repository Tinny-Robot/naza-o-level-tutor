# Hausa + curriculum fine-tuning

Naza includes **offline fine-tuning** on Nigerian O-Level (WAEC / NECO)
instruction data for **English and Hausa** tutoring. The live demo runs the
base Gemma GGUF via llama.cpp plus local RAG grounding; this folder holds the
dataset export, LoRA/QLoRA config, and reproducible training scripts for judges
and operators.

## Motivation

- **Hausa is under-resourced** in general-purpose LLM instruction data relative
  to English. Students who prefer Hausa still need exam-accurate Chemistry,
  Physics, Mathematics, and English Language explanations.
- **Curriculum alignment** matters more than fluent chatter: answers should
  track Nigerian secondary syllabi and past-question style, not generic web text.
- **Offline-first**: adaptation data comes from the local corpus and
  `data/eval/qa.json`. Training happens offline; the demo never calls cloud
  training APIs.

## Method

1. Export instruction pairs from local curriculum Q&A (see
   `scripts/prepare_dataset.py`).
2. Annotate / translate assistant turns into Hausa while keeping scientific
   terms in English where clearer (same policy as `app/i18n/language.py`).
3. Train with **LoRA or QLoRA** on a Gemma-class instruct checkpoint using
   the YAML template in `configs/lora_hausa_curriculum.yaml`.

Production RAG still grounds study answers in FAISS-retrieved chunks. Fine-tuning
changes generation style and language fluency; it does not replace retrieval.

## Relation to deployed Naza

| Piece | Production demo | This folder |
|---|---|---|
| Model | Local Gemma GGUF (`MODEL_PATH`) | Fine-tuned on curriculum + Hausa data |
| Grounding | Offline RAG over O-Level corpus | Same local Q&A as *training* source |
| Language | Prompt instruction (EN / Hausa UI) | Curriculum + Hausa instruction pairs |
| Launch | `./launch.sh` / Compose | Separate venv + `finetune/requirements.txt` |

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
└── scripts/
    ├── prepare_dataset.py    # Export instruction pairs (runnable)
    └── train_lora.py         # Training entrypoint
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

## Reproducibility (training)

1. Create a **separate** venv; do not add these packages to the app lockfile:

   ```bash
   python -m venv .venv-finetune
   source .venv-finetune/bin/activate
   pip install -r finetune/requirements.txt
   ```

2. Place a Gemma-class instruct base checkpoint (Hugging Face format for PEFT
   training — not the production GGUF) where the config points.
3. Export the full JSONL as above; run human Hausa review on `output_ha` where
   needed.
4. Edit `configs/lora_hausa_curriculum.yaml` paths and hyperparameters.
5. Run:

   ```bash
   python finetune/scripts/train_lora.py --config finetune/configs/lora_hausa_curriculum.yaml
   ```

## What stays unchanged in production

- No change to Docker production model mounts or the llama.cpp singleton.
- The ADTC-submitted GGUF under `model/` remains the base quant for profiling.
