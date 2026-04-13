FROM python:3.11-slim

WORKDIR /app

# Install system deps for ChromaDB
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ src/
COPY tests/ tests/
COPY tools/ tools/

RUN pip install --no-cache-dir ".[server,chroma,local,dev]"

# Default: local backend (JSON + sentence-transformers, zero external deps)
ENV MEMOS_BACKEND=local
ENV MEMOS_HOST=0.0.0.0
ENV MEMOS_PORT=8000
ENV MEMOS_CHROMA_URL=http://chroma:8000

EXPOSE 8000

CMD ["python", "-m", "memos.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]
