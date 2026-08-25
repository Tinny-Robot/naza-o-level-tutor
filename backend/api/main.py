"""Local FastAPI app: warm GenerationPipeline + desktop UI routes."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import MODEL_NAME
from app.generation.llm import get_llm
from app.generation.pipeline import GenerationPipeline
from app.generation.prompt_manager import get_prompt_manager
from app.generation.rag import RetrievalService
from app.ingestion.embedder import get_embedder
from app.retrieval.search import get_retriever
from app.utils.logging import get_logger
from app.utils.offline import enable_offline_mode
from backend.api.routes import chat, exams, learn, lesson, media, practice_api, progress, quiz, revision, student

logger = get_logger(__name__)

# Localhost-only SPA origins (any port on loopback).
_LOCAL_ORIGIN_RE = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"


def warm_pipeline() -> GenerationPipeline:
    """Eagerly load embedder, prompts, LLM, and one GenerationPipeline."""
    enable_offline_mode()
    logger.info("Warm-starting offline models for API…")
    prompts = get_prompt_manager()
    embedder = get_embedder()
    _ = embedder.model
    llm = get_llm()
    retriever = get_retriever()
    if getattr(retriever, "embedder", None) is not None:
        retriever.embedder = embedder
    pipeline = GenerationPipeline(
        retrieval=RetrievalService(retriever=retriever),
        llm=llm,
        prompts=prompts,
    )
    logger.info("API warm-start complete (model=%s)", MODEL_NAME)
    return pipeline


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Warm singletons once; skip when tests pre-seed ``app.state.pipeline``."""
    if getattr(app.state, "pipeline", None) is None:
        app.state.pipeline = warm_pipeline()
    yield


def create_app(*, lifespan_fn=lifespan) -> FastAPI:
    """Build the FastAPI application (factory for tests)."""
    application = FastAPI(
        title="O-Level Offline Tutor API",
        version="0.1.0",
        lifespan=lifespan_fn,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origin_regex=_LOCAL_ORIGIN_RE,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(chat.router)
    application.include_router(student.router)
    application.include_router(practice_api.router)
    application.include_router(exams.router)
    application.include_router(media.router)
    application.include_router(learn.router)
    application.include_router(lesson.router)
    application.include_router(quiz.router)
    application.include_router(progress.router)
    application.include_router(revision.router)

    @application.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "offline": True, "model": MODEL_NAME}

    return application


app = create_app()
