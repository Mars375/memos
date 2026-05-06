# syntax=docker/dockerfile:1

FROM python:3.11-slim@sha256:6d85378d88a19cd4d76079817532d62232be95757cb45945a99fec8e8084b9c2 AS builder

WORKDIR /build

# Build dependencies stay in the builder image only.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./

RUN python - <<'PY' > /tmp/requirements.txt
import tomllib

with open("pyproject.toml", "rb") as f:
    pyproject = tomllib.load(f)

requirements = list(pyproject["project"]["dependencies"])
extras = pyproject["project"]["optional-dependencies"]
for extra in ("server", "chroma", "parquet"):
    requirements.extend(extras[extra])

print("\n".join(requirements))
PY

RUN --mount=type=cache,target=/root/.cache/pip \
    pip wheel --wheel-dir /wheels -r /tmp/requirements.txt

COPY src/ src/

RUN --mount=type=cache,target=/root/.cache/pip \
    pip wheel --no-deps --wheel-dir /wheels .

FROM python:3.11-slim@sha256:6d85378d88a19cd4d76079817532d62232be95757cb45945a99fec8e8084b9c2 AS runtime

WORKDIR /app

ENV MEMOS_BACKEND=local
ENV MEMOS_HOST=0.0.0.0
ENV MEMOS_PORT=8000
ENV MEMOS_CHROMA_URL=http://chroma:8000
ENV MEMOS_PERSIST_PATH=/data/.memos/store.json
ENV MEMOS_CACHE_PATH=/data/.memos/embeddings.db

RUN groupadd --system memos && \
    useradd --system --gid memos --home-dir /home/memos --create-home memos && \
    mkdir -p /data/.memos && \
    chown -R memos:memos /data /home/memos

COPY --from=builder /wheels /wheels
COPY --from=builder /build/LICENSE /licenses/memos/LICENSE
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

USER memos

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()"

CMD ["python", "-m", "memos.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]
