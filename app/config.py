"""Central configuration for ingestion, retrieval, and RAG generation.

All tunable values (model names, chunking parameters, paths, LLM settings)
live here so that the rest of the codebase never hard-codes them.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Project root = directory that contains ``app/``, ``data/``, ``scripts/``.
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# Load ``.env`` from the project root if present (no-op when missing).
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR: Path = PROJECT_ROOT / "data"
RAW_DIR: Path = DATA_DIR / "raw"
PROCESSED_DIR: Path = DATA_DIR / "processed"
INDEX_DIR: Path = DATA_DIR / "index"

CHUNKS_PATH: Path = PROCESSED_DIR / "chunks.json"
METADATA_PATH: Path = PROCESSED_DIR / "metadata.json"
EMBEDDINGS_PATH: Path = PROCESSED_DIR / "embeddings.npy"
INDEX_PATH: Path = INDEX_DIR / "index.faiss"

# Evaluation dataset (hand-curated Q&A for retrieval metrics).
EVAL_DIR: Path = DATA_DIR / "eval"
QA_PATH: Path = EVAL_DIR / "qa.json"
EVAL_IMAGES_DIR: Path = EVAL_DIR / "images"

# Local GGUF models (never downloaded by the app).
MODELS_DIR: Path = PROJECT_ROOT / "models"

# Invisible Learning Profile (local student state - never synced to cloud).
STUDENT_DIR: Path = PROJECT_ROOT / "student"

# ---------------------------------------------------------------------------
# Embedding model (local files only - never downloads from Hugging Face)
# ---------------------------------------------------------------------------

# Historical HF repo id (metadata / docs only). Runtime loads from disk.
EMBEDDING_MODEL: str = "matt-wisdom/KEmbed-naija-v3"
EMBEDDING_MODEL_PATH: Path = Path(
    os.getenv(
        "EMBEDDING_MODEL_PATH",
        str(MODELS_DIR / "embeddings" / "KEmbed-naija-v3"),
    )
)
EMBED_BATCH_SIZE: int = 32

# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

# Sizes are measured in words (whitespace-delimited tokens).
CHUNK_SIZE: int = 220
CHUNK_OVERLAP: int = 40
MIN_CHUNK_WORDS: int = 20

# File extensions the loader knows how to parse.
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".txt", ".md", ".json", ".jsonl", ".csv", ".pdf"}
)

# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

TOP_K: int = 5

# Retrieval backend: "dense" (FAISS), "bm25", or "hybrid" (RRF fusion).
RETRIEVAL_MODE: str = "dense"

# Reciprocal Rank Fusion constant: score += 1 / (RRF_K + rank).
RRF_K: int = 60

# Cross-encoder reranker (off by default - avoids forced model download).
ENABLE_RERANKER: bool = False
RERANK_CANDIDATES: int = 30
RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# ---------------------------------------------------------------------------
# Local LLM / RAG generation (Gemma 4 E4B-it via llama.cpp)
# ---------------------------------------------------------------------------

MODEL_NAME: str = os.getenv("MODEL_NAME", "Gemma-4-E4B-it")
MODEL_PATH: Path = Path(
    os.getenv(
        "MODEL_PATH",
        str(PROJECT_ROOT / "model" / "gemma-4-E4B-it-IQ3_M.gguf"),
    )
)

CONTEXT_LENGTH: int = int(os.getenv("CONTEXT_LENGTH", "4096"))
THREADS: int = int(os.getenv("THREADS", str(max(1, (os.cpu_count() or 2) - 1))))
MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "512"))
TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.1"))
MAX_CONTEXT_TOKENS: int = int(os.getenv("MAX_CONTEXT_TOKENS", "3000"))
MIN_RETRIEVAL_SCORE: float = float(os.getenv("MIN_RETRIEVAL_SCORE", "0.35"))

PROMPTS_DIR: Path = PROJECT_ROOT / "app" / "prompts"

REFUSAL_MESSAGE: str = (
    "I couldn't find enough information in the study materials."
)

CONFIDENCE_TOP_WEIGHT: float = 0.7
CONFIDENCE_MEAN_WEIGHT: float = 0.3


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# llama.cpp memory knobs for the Gemma-4-E4B-it IQ3_M submission quant.
FLASH_ATTN: bool = _env_bool("FLASH_ATTN", True)
SWA_FULL: bool = _env_bool("SWA_FULL", False)
