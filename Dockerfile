# Build stage: some locked deps (pyppmd/pybcj/inflate64/pyyaml) have no cp315 wheels yet and are built from sdist, which needs a compiler.
FROM python:3.15-slim AS builder
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

# Runtime stage: slim, no compiler. The venv is copied over at the same path, so its interpreter symlinks stay valid.
FROM python:3.15-slim
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv

COPY src .
# PYTHONPATH must include /app so that `from ebd_toolchain.x import ...` resolves.
# Without it, `python ebd_toolchain/main.py` only adds /app/ebd_toolchain/ to sys.path.
ENV PYTHONPATH=/app
ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "ebd_toolchain/main.py", "-i", "/container/ebd.docx", "-o", "/container/output", "-t", "json", "-t", "dot", "-t", "svg", "-t", "puml"]
# to test this image run
# $ docker build -t local-test-image .
# $ docker compose up --build --abort-on-container-exit
