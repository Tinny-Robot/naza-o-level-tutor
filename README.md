# ADTC 2026 - Naza (Laptop LLM track)

Submission layout follows the official
[ADTC 2026 submission template](https://github.com/Africa-Deep-Tech-Foundation/adtc-2026-submission-template).
Submit the public GitHub URL via [adtc-2026.devpost.com](https://adtc-2026.devpost.com).

---

## Submission checklist

Before submitting, confirm every item:

- [x] Repository is **public** on GitHub
- [x] `metadata.json` is fully filled - replace every `REPLACE_WITH_*` placeholder
- [x] `metadata.json` has exactly **2** `test_prompts`
- [x] `bash download_model.sh` downloads a valid **GGUF** into `model/`
- [x] `model/` and `*.gguf` are gitignored - **do not** commit weights
- [x] `REPORT.md` is filled and factual
- [x] Model runs **offline** during inference (no network after download)
- [x] `finetune/` documents the Hausa + curriculum training pipeline

---



## Required ADTC file structure

```
.
├── metadata.json          ← Team, domain, languages, 2 test prompts, model meta
├── download_model.sh      ← Public download of .gguf → model/
├── REPORT.md              ← Technical writeup for judges / audit
├── model/
│   └── gemma-4-E4B-it-IQ3_M.gguf   ← via download_model.sh (NOT in git)
├── LICENSE                ← GPL-3.0 (template)
├── .gitignore             ← Excludes *.gguf and model weights
├── finetune/              ← Hausa + curriculum fine-tuning (dataset, config, scripts)
└── …                      ← Full offline tutor app (see below)
```



### Quick Start: One-Command Launch

You can run the entire application with a single turnkey command. `./launch.sh` automatically detects and bootstraps missing Python dependencies, the desktop frontend build, offline model weights, and the FAISS index:

```bash
./launch.sh
```

*(Headless / browser mode: `./launch.sh --no-window` — access the UI at `http://127.0.0.1:5151`)*

---

### Manual Setup (Step-by-Step)

Alternatively, if you want to inspect or run each setup stage individually:

#### Step 1: Set Up Python Environment
Using [uv](https://docs.astral.sh/uv/):
```bash
uv sync
```
Or using standard `venv` + `pip`:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

#### Step 2: Build Desktop Frontend UI
```bash
cd desktop
npm install
npm run build
cd ..
```

#### Step 3: Download Offline Model Weights
1. **Gemma-4-E4B-it LLM (GGUF)**:
   ```bash
   bash download_model.sh
   ```
   *(Downloads and verifies `model/gemma-4-E4B-it-IQ3_M.gguf`)*

2. **KEmbed-naija-v3 Embedding Model**:
   ```bash
   python -c "from huggingface_hub import snapshot_download; snapshot_download('matt-wisdom/KEmbed-naija-v3', local_dir='models/embeddings/KEmbed-naija-v3')"
   ```

#### Step 4: Ingest Curriculum Data & Build FAISS Index
```bash
python scripts/ingest.py
```
*(Processes raw textbooks/syllabi from `data/raw/` and builds `data/index/index.faiss`)*

#### Step 5: Launch the Application
- **Interactive Desktop / Browser GUI**:
  ```bash
  ./launch.sh
  ```
  *(Or headless mode: `./launch.sh --no-window` — access UI at `http://127.0.0.1:5151`)*
- **Interactive CLI Tutor**:
  ```bash
  python scripts/ask.py
  ```
- **CLI Semantic Search**:
  ```bash
  python scripts/search.py
  ```

---

### ADTC Profiler Benchmark

```bash
pip install "git+https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler.git"
adtc-profiler run \
  --submission . \
  --mode participant \
  --output submission.json \
  --skip-accuracy
```

### Metadata you must edit

Open `[metadata.json](metadata.json)` and set:

- `team_id`, `submitter.name`, `submitter.email`
- Keep `budget_laptop_claim: true`, `model.runtime: "llama.cpp"`
- `language_scope`: `["en", "ha"]` (English + Hausa)
- `african_alpha_claim: true` (Nigerian O-Level education use case)
- `domain`: `math_scientific_reasoning`

---



# Naza - Offline O-Level RAG Tutor

Semantic retrieval and grounded tutoring over Nigerian O-Level study materials
(English, Physics, Mathematics, Chemistry). Raw textbooks, syllabi and past
exam questions are cleaned, chunked, embedded with a **local**
`KEmbed-naija-v3` sentence-transformer snapshot, indexed with FAISS, and
answered via a fully offline retrieve-then-generate (RAG) layer powered by
**Gemma-4-E4B-it** (GGUF) through llama.cpp. No cloud APIs or Hugging Face downloads
at runtime.

The project also includes an **offline fine-tuning pipeline** for curriculum-
aligned **English and Hausa** tutoring data: instruction-pair export,
LoRA/QLoRA config, and reproducible scripts under `[finetune/](finetune/)`.
The submitted GGUF is the quantized base model; RAG grounding keeps product
answers tied to local syllabus materials at demo time.

Optional upgrades (off or dense-only by default so existing behaviour is
unchanged): BM25 / hybrid RRF retrieval, cross-encoder reranking, metadata
filters, and a retrieval evaluation harness.

> **Note:** Both the ADTC profiler and the full product demo use the pinned GGUF
> under `model/` by default. `download_model.sh` verifies its exact size and
> SHA-256 before the model is used offline.



## Project structure

```
O-Level/
├── metadata.json            # ADTC submission metadata
├── download_model.sh        # ADTC GGUF download → model/
├── REPORT.md                # ADTC technical report
├── model/                   # ADTC weights directory (gguf gitignored)
├── app/
│   ├── config.py              # Paths, embedding, chunking, retrieval, LLM settings
│   ├── ingestion/
│   │   ├── loader.py          # Load txt/md/json/jsonl/csv from data/raw/
│   │   ├── cleaner.py         # Unicode (NFC) normalization, whitespace cleanup
│   │   ├── chunker.py         # Word-based sliding-window chunking with overlap
│   │   ├── embedder.py        # SentenceTransformer wrapper (lazy-loaded)
│   │   └── pipeline.py        # run_ingestion(): load -> clean -> chunk -> embed -> index
│   ├── retrieval/
│   │   ├── faiss_store.py     # FaissStore around faiss.IndexFlatIP (normalized vectors)
│   │   ├── bm25_store.py      # BM25Retriever over chunk texts (rank_bm25)
│   │   ├── reranker.py        # Optional CrossEncoder reranker
│   │   ├── retriever.py       # dense / bm25 / hybrid (RRF) + filters + rerank
│   │   └── search.py          # Cached retriever, search() and format_results()
│   ├── evaluation/
│   │   ├── loader.py          # Validate/load data/eval/qa.json
│   │   ├── metrics.py         # Recall@K, Precision@K, MRR, Hit Rate
│   │   └── evaluator.py       # Run eval over retriever, print summary
│   ├── generation/
│   │   ├── llm.py             # Gemma-4-E4B-it llama.cpp singleton + tokenize()
│   │   ├── router.py          # Offline Study vs General query routing
│   │   ├── context_builder.py # Dedupe, sort, token-budget, [Chunk id] format
│   │   ├── prompt_manager.py  # Cached study + general prompt templates
│   │   ├── citations.py       # Citation records from post-budget chunks
│   │   ├── hallucination.py   # Refuse when retrieval is empty / low-score
│   │   ├── rag.py             # Retrieval interface only
│   │   └── pipeline.py        # Route → Study RAG or General LLM-only
│   ├── prompts/
│   │   ├── system.txt         # Study system tutoring prompt
│   │   ├── user.txt           # Study user template ({context} / {question})
│   │   ├── general_system.txt # General Conversation system prompt
│   │   └── general_user.txt   # General user template ({question})
│   ├── models/document.py     # Document and Chunk dataclasses
│   └── utils/logging.py       # get_logger() helper
├── models/                    # Local embedding snapshot (gitignored weights)
├── model/                     # Pinned app + ADTC GGUF (entire directory gitignored)
├── finetune/                  # Hausa + curriculum fine-tuning (dataset, config, scripts)
├── data/
│   ├── raw/                   # Source corpus, one folder per subject (keep)
│   ├── processed/             # chunks.json, metadata.json, embeddings.npy
│   ├── index/                 # index.faiss
│   └── eval/                  # qa.json (hand-curated); qa.example.json
├── backend/
│   └── api/                   # Local FastAPI IPC (chat + lesson/quiz/progress/revision)
├── launcher/                  # Application Manager (preflight, start, supervise)
│   ├── manager.py             # FastAPI + Vite orchestration + cleanup
│   └── launch.py              # CLI entry used by ./launch.sh
├── scripts/
│   ├── ingest.py              # Load/clean/chunk (and optionally embed + index)
│   ├── build_index.py         # Build index.faiss from embeddings.npy
│   ├── search.py              # Interactive retrieval CLI (optional filters)
│   ├── ask.py                 # Interactive offline RAG tutor CLI (self-check + warm-start)
│   ├── serve_api.py           # Advanced/debug: uvicorn on 127.0.0.1:8010
│   ├── serve_docker.py        # Container entry: API + SPA on 0.0.0.0
│   ├── benchmark.py           # Cold/warm latency, tokens/sec, RAM
│   └── evaluate.py            # Retrieval metrics against data/eval/qa.json
├── desktop/                   # ADTC desktop UI (Vite + React + TypeScript)
│   ├── src/                   # AppShell, features, design tokens, motion
│   ├── stitch/                # Stitch HTML exports
│   └── DESIGN.md              # Design system + Stitch project link
├── tests/                     # pytest suite (mocks embeddings and LLM)
├── launch.sh                  # Official entry: ./launch.sh
├── pyproject.toml             # uv / pip project + lock source
├── uv.lock                    # Frozen Python deps
├── requirements.txt           # uv export (pip fallback)
├── Dockerfile                 # UI build + uv runtime
├── compose.yaml               # Publish :5151 / :8010, mount models + data
├── .env.example               # Optional local LLM / embedding overrides
└── README.md
```



## Desktop + API

Premium dark-mode learning shell designed in [Google Stitch](https://stitch.withgoogle.com/projects/628528694332230301) and implemented as a Vite React app. FastAPI is the **internal IPC layer** (loopback only): the UI talks only to `http://127.0.0.1:8010`. Judges and demos should use one command.

### Launch the app

Run the turnkey launcher from the project root (automatically bootstraps missing environment, desktop frontend build, offline models, and FAISS index):

```bash
./launch.sh
```

*(For headless/browser mode: `./launch.sh --no-window` — access the UI at `http://127.0.0.1:5151`)*



### Docker (uv image)

The image contains code plus a production UI build. It does **not** copy `.env`, the GGUF, embedding weights, or the FAISS index. Mount those from the host:

```bash
# Run download_model.sh, then place models/embeddings/KEmbed-naija-v3/
# plus data/index/index.faiss and data/processed/* as in Setup below.
docker compose up --build
```

UI: [http://127.0.0.1:5151/](http://127.0.0.1:5151/) · API: [http://127.0.0.1:8010/health](http://127.0.0.1:8010/health)

If `models/embeddings/KEmbed-naija-v3` is a symlink into `~/.cache/huggingface`, copy the snapshot into `models/embeddings/` (or add a compose volume for that cache). The container cannot follow a host-only symlink.

Warm-start can take several minutes. Stop with Ctrl+C. `.env` is never baked into the image.

**PM2 (API + UI together):**

```bash
pm2 start ecosystem.config.cjs
pm2 status          # naza-api (:8010), naza-ui (:5151)
pm2 logs naza-api   # wait until /health is ok (Gemma warm-start)
```

UI: [http://127.0.0.1:5151/](http://127.0.0.1:5151/) · API: [http://127.0.0.1:8010/health](http://127.0.0.1:8010/health)  
Stop: `pm2 stop naza-api naza-ui` · Restart: `pm2 restart ecosystem.config.cjs`

This runs the Application Manager which:

1. Enables offline mode and verifies GGUF, embeddings, and FAISS assets
2. Starts local FastAPI IPC on `127.0.0.1:8010` and waits for `GET /health` (`status: ok`; warm-start may take several minutes)
3. Starts the Vite desktop UI on `127.0.0.1:5151` (routes use hash URLs, e.g. `/#/tutor`)
4. Opens a Chromium/Chrome `--app=` window (falls back to the default browser)
5. Supervises both processes and cleans up on window close / Ctrl+C

Optional: `./launch.sh --no-window` for headless/CI (UI still served at `http://127.0.0.1:5151`).  
Optional UI override: `VITE_API_BASE=http://127.0.0.1:8010` (default). See `[desktop/DESIGN.md](desktop/DESIGN.md)` for tokens, motion, and screen map.

IPC contract (stable for a future Electron shell):


| Method | Path                                 | Role                                  |
| ------ | ------------------------------------ | ------------------------------------- |
| GET    | `/health`                            | readiness                             |
| POST   | `/chat`                              | tutor IPC (chat or structured lesson) |
| GET    | `/student/summary`                   | Learning Plan + mastery aggregates    |
| POST   | `/practice/next`, `/practice/answer` | adaptive practice                     |
| POST   | `/exams/start`, `/exams/submit`      | CBT mock exams                        |
| GET    | `/media`                             | textbook diagram files                |


Invisible Learning Profile lives in project-root `student/` (gitignored).

### Future packaging

Electron packaging is **not** included yet. A future shell would replace the Vite/Chrome `--app` window and load a `desktop` production build; the Application Manager would still start FastAPI, gate on `/health`, and keep the same API contract. Do not move FastAPI into the renderer.

### Advanced / debug (not the primary path)

To run services separately while debugging:

```bash
.venv/bin/python scripts/serve_api.py   # Terminal A - API only
cd desktop && npm run dev               # Terminal B - UI only
```



## Setup

From the project root, using [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv sync
cd desktop && npm install && npm run build && cd ..
cp .env.example .env   # optional overrides only
```

pip fallback if you are not using uv:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd desktop && npm install && npm run build && cd ..
```



### Local GGUF (required for LLM tutoring)

The app **never downloads** model weights at runtime. Place a **Gemma 4 E4B-it IQ3_M** GGUF at:

```text
model/gemma-4-E4B-it-IQ3_M.gguf
```

(or set `MODEL_PATH` in `.env`). `*.gguf` files and `model/` are gitignored.

Download and verify the pinned public artifact:

```bash
bash download_model.sh
```

Requires `llama-cpp-python>=0.3.34` (bundled llama.cpp with `gemma4` arch support).

### Local embedding model (required)

Embeddings load only from disk (`local_files_only=True`) with
`HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1`. Default path:

```text
models/embeddings/KEmbed-naija-v3/
```

Download the local snapshot directly via Python:

```bash
python -c "from huggingface_hub import snapshot_download; snapshot_download('matt-wisdom/KEmbed-naija-v3', local_dir='models/embeddings/KEmbed-naija-v3')"
```

Alternatively, if you already have the snapshot cached locally:

```bash
mkdir -p models/embeddings
SNAP="$HOME/.cache/huggingface/hub/models--matt-wisdom--KEmbed-naija-v3/snapshots/$(cat "$HOME/.cache/huggingface/hub/models--matt-wisdom--KEmbed-naija-v3/refs/main")"
ln -sfn "$SNAP" models/embeddings/KEmbed-naija-v3
```

Ensure the directory contains `config.json`, `modules.json`, and `model.safetensors`. Override with `EMBEDDING_MODEL_PATH` in `.env` if stored elsewhere.

## Environment / generation settings


| Variable               | Default                             | Description                               |
| ---------------------- | ----------------------------------- | ----------------------------------------- |
| `MODEL_NAME`           | `Gemma-4-E4B-it`                    | Display / log name                        |
| `MODEL_PATH`           | `model/gemma-4-E4B-it-IQ3_M.gguf`   | Path to the GGUF                          |
| `EMBEDDING_MODEL_PATH` | `models/embeddings/KEmbed-naija-v3` | Local SentenceTransformer dir             |
| `HF_HUB_OFFLINE`       | `1` (set by `ask.py`)               | Block Hugging Face hub access             |
| `TRANSFORMERS_OFFLINE` | `1` (set by `ask.py`)               | Block Transformers downloads              |
| `CONTEXT_LENGTH`       | `4096`                              | llama.cpp `n_ctx`                         |
| `THREADS`              | `max(2, cpu_count - 1)`             | CPU threads                               |
| `MAX_TOKENS`           | `512`                               | Generation cap                            |
| `TEMPERATURE`          | `0.1`                               | Sampling temperature                      |
| `MAX_CONTEXT_TOKENS`   | `3000`                              | Retrieved-context budget (real tokenizer) |
| `MIN_RETRIEVAL_SCORE`  | `0.35`                              | Refuse below this top score               |
| `PROMPTS_DIR`          | `app/prompts`                       | Prompt template directory                 |


No cloud API keys or provider selection.

## Building the index (ingestion)

There are two ways to build the index, depending on the machine.

### Flow A: full local ingestion

```bash
.venv/bin/python scripts/ingest.py
```

This walks `data/raw/`, cleans and chunks every supported file, embeds the
chunks from the **local** `EMBEDDING_MODEL_PATH` snapshot (never downloads),
and writes:

- `data/processed/chunks.json`
- `data/processed/metadata.json`
- `data/processed/embeddings.npy`
- `data/index/index.faiss`



### Flow B: split GPU flow (chunk locally, embed elsewhere)

```bash
.venv/bin/python scripts/ingest.py --skip-embedding
```

This writes only `chunks.json` and `metadata.json`. Compute embeddings
externally with the same `matt-wisdom/KEmbed-naija-v3` model (float32
`(num_chunks, dim)` ordered the same as `chunks.json`), save to
`data/processed/embeddings.npy`, then:

```bash
.venv/bin/python scripts/build_index.py
```



## Searching (retrieval only)

```bash
.venv/bin/python scripts/search.py
```

Optionally enter Subject, Topic, and Source filters (Enter to skip each), then
a query. Results show Rank, Score, Subject, Topic, Source, Chunk ID, and Text.
Empty query / Ctrl+C / Ctrl+D exits.

```python
from app.retrieval.search import search
results = search(
    "What is subject-verb concord?",
    top_k=5,
    subject="english",   # optional
    topic=None,
    source=None,
)
```



### Retriever API

```python
from app.retrieval.retriever import Retriever

retriever = Retriever()
hits = retriever.retrieve(
    query,
    top_k=5,
    subject=None,  # exact match (case-insensitive)
    topic=None,    # exact match (case-insensitive)
    source=None,   # substring match (case-insensitive)
)
# each hit: {"score": float, "text": str, "metadata": dict}
```

Metadata filters reduce the candidate set **before** dense / BM25 scoring
(BM25 scores only matching docs; FAISS searches then keeps matching ids).

## Asking (offline tutor with Study vs General routing)

```bash
.venv/bin/python scripts/ask.py
```

Startup prints a self-check (GGUF, local embeddings, FAISS, prompts, offline
flags), a banner, then warm-loads the embedding model, Gemma GGUF, and prompts
once so later questions do not reload. Visible reasoning / think blocks
are stripped from every generated answer.

Type a question at `Enter question:`. A **rule-based offline router** (no
network, no LLM classification) chooses:

- **Study** - exam / syllabus / subject cues → existing RAG path (retrieve →
hallucination guard → context → study prompts → same local Gemma-4-E4B-it).
- **General Conversation** - greetings, casual chat, programming, careers,
etc. → same in-memory Gemma-4-E4B-it via `get_llm()`, with general prompts only
(no retrieval, no citations).

Each answer prints Mode, Confidence, Latency, Tokens Generated, Tokens/sec,
Memory Usage, and Citations (Study only).

### Offline benchmark

```bash
.venv/bin/python scripts/benchmark.py
```

Reports cold start, warm start, average latency, tokens/sec, RAM, and model
load times on fixed Study + General sample questions.

```python
from app.generation.pipeline import ask
result = ask("Explain Ohm's law", top_k=5)
print(result["mode"], result["answer"])
print(result["refused"], result["confidence"])
print(result["citations"])
print(result["retrieved_chunks"])
```

Response schema:

```python
{
    "mode": "study" | "general",
    "answer": str,
    "citations": list[dict],      # [] in general; else subject/topic/source/chunk_id/score
    "confidence": float,          # 1.0 in general; else 0.7 * top + 0.3 * mean(top_3)
    "retrieved_chunks": list[dict],  # [] in general
    "refused": bool,              # always False in general
}
```

Requires a built index (for Study) and the GGUF at `MODEL_PATH`.

## Hybrid / BM25 retrieval

Configure in `app/config.py`:


| Setting          | Default   | Meaning                                    |
| ---------------- | --------- | ------------------------------------------ |
| `RETRIEVAL_MODE` | `"dense"` | `"dense"` (FAISS), `"bm25"`, or `"hybrid"` |
| `RRF_K`          | `60`      | Reciprocal Rank Fusion constant            |


- **dense** - cosine similarity via FAISS `IndexFlatIP` (unchanged default for
`ask.py` / RAG).
- **bm25** - lexical BM25Okapi over chunk texts (`rank_bm25`).
- **hybrid** - run dense + BM25, fuse ranks with RRF:
`score(d) = Σ 1 / (RRF_K + rank_i(d))`.

Example: set `RETRIEVAL_MODE = "hybrid"` in `app/config.py`, then re-run
`scripts/search.py` or `scripts/evaluate.py`.

## Cross-encoder reranker


| Setting             | Default                                | Meaning                                          |
| ------------------- | -------------------------------------- | ------------------------------------------------ |
| `ENABLE_RERANKER`   | `False`                                | Master switch (off avoids forced model download) |
| `RERANK_CANDIDATES` | `30`                                   | Retrieve this many, then rerank                  |
| `RERANKER_MODEL`    | `cross-encoder/ms-marco-MiniLM-L-6-v2` | HF model id                                      |


Flow when enabled: retrieve top `RERANK_CANDIDATES` → CrossEncoder scores →
return top `top_k` (usually 5). If `ENABLE_RERANKER=True` and the model cannot
be loaded, retrieval raises a clear `RuntimeError`.

## Retrieval evaluation

Hand-curate items in `data/eval/qa.json` (starts as `[]`). Schema:

```json
[
  {
    "id": "chem-atom-001",
    "question": "What is the electronic configuration of Zn2+?",
    "answer": "1s2 2s2 2p6 3s2 3p6 3d10",
    "subject": "chemistry",
    "topic": "Structure of the Atom",
    "expected_keywords": ["zinc", "Zn", "electronic configuration", "3d10"]
  }
]
```

See `data/eval/qa.example.json` for a filled example. **Do not invent large
auto-generated sets** - ground questions in your corpus.

```bash
.venv/bin/python scripts/evaluate.py
```

Prints:

```
========================
Evaluation Results
Recall@5:
Recall@10:
MRR:
Hit Rate:
========================
```

An empty `qa.json` exits cleanly with a message to add items.

### Relevance judgment

A retrieved doc is **relevant** if (case-insensitive):

1. its `metadata.subject` matches the item subject **and** (no keywords, or at
  least one `expected_keywords` substring appears in text/topic/subject), or
2. any expected keyword overlaps text/topic/subject (even if subject differs).



### Metric definitions

- **Recall@K** - fraction of queries with ≥1 relevant doc in the top-K.
- **Precision@K** - mean fraction of top-K docs that are relevant.
- **MRR** - mean of `1/rank` of the first relevant doc (0 if none).
- **Hit Rate** - fraction of queries with ≥1 relevant doc in the retrieved list.

Eval retrieves at least 10 docs per query so Recall@10 is meaningful.

## Fine-tuning pipeline (Hausa + curriculum)

The repository provides a reproducible training pipeline for **Nigerian O-Level
curriculum instruction data** in **English and Hausa**. The submitted artifact
and live demo use the **base Gemma GGUF + local RAG**; no adapter is merged into
the competition GGUF.


| Piece   | Contents                                                                    |
| ------- | --------------------------------------------------------------------------- |
| Dataset | Instruction pairs exported from `data/eval/qa.json` (EN + Hausa schema)     |
| Config  | LoRA/QLoRA hyperparameters in `finetune/configs/lora_hausa_curriculum.yaml` |
| Scripts | `prepare_dataset.py` (export JSONL), `train_lora.py` (training entrypoint)  |


See `[finetune/README.md](finetune/README.md)`, `[finetune/SUBMISSION.md](finetune/SUBMISSION.md)`,
and `[finetune/scripts/prepare_dataset.py](finetune/scripts/prepare_dataset.py)`.
The submitted ADTC GGUF remains the base quant under `model/`.

## Adding new datasets

Place files under `data/raw/<subject>/`. Supported formats:

- `.txt` / `.md` - one document per file
- `.json` / `.jsonl` - Q&A records rendered into readable text
- `.csv` - each row becomes a document of `key: value` lines

Unsupported or corrupt files are skipped with a warning. After changes,
re-run ingestion (and recompute embeddings if using Flow B).

## Running the tests

```bash
pytest
# or: .venv/bin/pytest
# or: uv run pytest
```

Tests mock the embedding model, CrossEncoder, and local LLM tokenizer, so they
do not download the GGUF or call external APIs.

## Configuration

Tunables live in `app/config.py`:


| Setting                                  | Default                                | Notes                         |
| ---------------------------------------- | -------------------------------------- | ----------------------------- |
| `EMBEDDING_MODEL`                        | `matt-wisdom/KEmbed-naija-v3`          | Metadata / docs id only       |
| `EMBEDDING_MODEL_PATH`                   | `models/embeddings/KEmbed-naija-v3`    | Local SentenceTransformer dir |
| `CHUNK_SIZE` / `CHUNK_OVERLAP`           | `220` / `40`                           | Words                         |
| `TOP_K`                                  | `5`                                    | Final results returned        |
| `RETRIEVAL_MODE`                         | `"dense"`                              | `dense` | `bm25` | `hybrid`   |
| `RRF_K`                                  | `60`                                   | Hybrid fusion constant        |
| `ENABLE_RERANKER`                        | `False`                                | Cross-encoder on/off          |
| `RERANK_CANDIDATES`                      | `30`                                   | Pool size before rerank       |
| `RERANKER_MODEL`                         | `cross-encoder/ms-marco-MiniLM-L-6-v2` |                               |
| `EVAL_DIR` / `QA_PATH`                   | `data/eval`, `data/eval/qa.json`       | Eval dataset                  |
| `MODEL_PATH` / `TEMPERATURE` / `THREADS` | see above                              | Offline Gemma-4-E4B-it        |


