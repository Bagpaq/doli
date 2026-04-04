# ── Build stage ───────────────────────────────────────────────────────
FROM python:3.12-slim AS base

# System deps for audio / Google libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY agent/      ./agent/
COPY config/     ./config/
COPY templates/  ./templates/
COPY outbound/   ./outbound/

# Working directory is /app/agent so imports resolve correctly
WORKDIR /app/agent

# ── Runtime ───────────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/agent

CMD ["python", "main.py", "start"]
