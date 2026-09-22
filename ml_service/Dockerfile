# ── SATQUERY AI — ML Service Dockerfile ──────────────────────────────────────
# Separate image so heavy ML deps (torch, transformers) don't inflate the
# base backend image.  GPU support via nvidia/cuda base (optional).
#
# To use CPU:  docker build -f ml_service/Dockerfile -t satquery-ml .
# To use GPU:  docker build --build-arg BASE_IMAGE=nvidia/cuda:12.1.0-runtime-ubuntu22.04 \
#              -f ml_service/Dockerfile -t satquery-ml .

ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE} AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ git libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt                 backend-requirements.txt
COPY ml_service/requirements-ml.txt          ml-requirements.txt
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir \
        -r backend-requirements.txt \
        -r ml-requirements.txt

FROM ${BASE_IMAGE} AS runtime

RUN useradd -m -u 1001 satquery 2>/dev/null || true

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libsm6 libxext6 libxrender-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

COPY backend/   ./backend/
COPY ml_service/ ./ml_service/
COPY worker/    ./worker/

RUN mkdir -p /app/backend/uploads /app/backend/.model_cache \
    && chown -R satquery:satquery /app 2>/dev/null || true

USER satquery

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/backend:/app \
    MODEL_CACHE_DIR=/app/backend/.model_cache

CMD ["python", "-c", "print('ML service container ready. Models load on first inference request.')"]
