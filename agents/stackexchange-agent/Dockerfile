# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License").
#
# Container image for the Stack Exchange A2A agent (LangGraph graph self-served
# over A2A with a2a-sdk 1.x). Built for GKE.

FROM python:3.12-slim

# Install uv (fast, reproducible installs from the committed uv.lock).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first (better layer caching), then the app.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app

# Install the project itself (so `app` is importable).
RUN uv sync --frozen --no-dev

ENV PORT=8080
EXPOSE 8080

# uvicorn serves the ASGI app defined in app/server.py.
CMD ["uv", "run", "--no-dev", "uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8080"]
