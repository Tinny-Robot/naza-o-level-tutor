"""RAG generation layer: offline Gemma 4 E4B pipeline over retrieved study chunks."""

from app.generation.pipeline import GenerationPipeline, ask
from app.generation.router import QueryMode, QueryRouter

__all__ = ["GenerationPipeline", "QueryMode", "QueryRouter", "ask"]
