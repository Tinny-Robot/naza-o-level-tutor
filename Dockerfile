# syntax=docker/dockerfile:1
# Offline tutor image: built Vite UI + uv-managed Python runtime.
# GGUF, embeddings snapshot, and FAISS index are bind-mounted at run time.

FROM node:22-bookworm-slim AS ui
WORKDIR /ui
COPY desktop/package.json desktop/package-lock.json ./
RUN npm ci
COPY desktop/ ./
# Host browser on published ports talks to 127.0.0.1:8010 (default prod base).
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime
WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    BIND_HOST=0.0.0.0 \
    NAZA_DOCKER=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY backend ./backend
COPY launcher ./launcher
COPY scripts ./scripts
COPY --from=ui /ui/dist ./desktop/dist

EXPOSE 8010 5151

CMD ["uv", "run", "--no-dev", "python", "scripts/serve_docker.py"]
