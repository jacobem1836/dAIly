# Stage 1: Source the uv binary
FROM ghcr.io/astral-sh/uv:latest AS uv-source

# Stage 2: Builder — install dependencies into .venv
FROM python:3.11-slim AS builder

COPY --from=uv-source /uv /uvx /bin/

WORKDIR /app

# Copy dependency manifests first (layer caching — deps rebuilt only when these change)
COPY pyproject.toml uv.lock ./

# Install dependencies (no project package yet — keeps this layer cacheable)
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source
COPY src/ ./src/

# Install the project package into the venv
RUN uv sync --frozen --no-dev

# Stage 3: Final runtime image
FROM python:3.11-slim AS final

WORKDIR /app

# Copy the populated virtualenv from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application source
COPY --from=builder /app/src /app/src

# Copy Alembic migration config (needed by entrypoint)
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Copy entrypoint script
COPY scripts/entrypoint.sh /app/entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH"

RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
