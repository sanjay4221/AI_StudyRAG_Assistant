# Dockerfile — StudyRAG
# Python 3.11 slim — small, stable, matches development environment

FROM python:3.11-slim

WORKDIR /app

# Install OS build tools needed for bcrypt, chromadb, sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first
# Docker caches this layer — only reinstalls if requirements.txt changes
COPY backend/requirements.txt ./requirements.txt
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Create persistent data directories (mounted as volumes)
RUN mkdir -p /data/uploads /data/vectorstore /data/logs

# Environment
ENV PYTHONPATH=/app/backend \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    PORT=8000

EXPOSE 8000

# Run from backend/ so imports resolve correctly (same as running locally)
WORKDIR /app/backend

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
