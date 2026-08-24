"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Request

from app.generation.pipeline import GenerationPipeline


def get_pipeline(request: Request) -> GenerationPipeline:
    """Return the warm-started pipeline stored on ``app.state``."""
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise RuntimeError(
            "GenerationPipeline is not initialized. "
            "Ensure the API lifespan warm-start completed."
        )
    return pipeline
