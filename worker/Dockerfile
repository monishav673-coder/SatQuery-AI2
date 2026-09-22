# ── SATQUERY AI — Worker Dockerfile ──────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt requirements.txt
COPY worker/requirements-worker.txt requirements-worker.txt
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir \
        -r requirements.txt \
        -r requirements-worker.txt

FROM python:3.11-slim AS runtime

RUN useradd -m -u 1001 satquery

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

COPY backend/   ./backend/
COPY ml_service/ ./ml_service/
COPY worker/    ./worker/

RUN mkdir -p /app/backend/uploads /app/backend/database /app/backend/.model_cache \
    && chown -R satquery:satquery /app

USER satquery

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/backend:/app

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import redis; r=redis.from_url('${REDIS_URL:-redis://redis:6379/0}'); r.ping()" || exit 1

CMD ["python", "/app/worker/worker_main.py"]
