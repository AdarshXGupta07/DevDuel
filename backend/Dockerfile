# DevDuel API.
#
# Note this image is NOT the judge sandbox — the runner images in docker/runner/ are.
# This container talks to the host's Docker daemon to start those, which is why the
# compose file mounts the socket. That mount is effectively root on the host, so the
# API container and the judge must eventually live on separate machines (see
# docs/deploy.md § Hardening).
FROM python:3.12.7-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, in their own layer: requirements.txt changes far less often than
# the source, so a code edit rebuilds in seconds instead of re-resolving every wheel.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The Docker CLI, so the judge can start containers on the mounted daemon socket.
RUN apt-get update \
    && apt-get install -y --no-install-recommends docker.io curl \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# Non-root, like the runners. It needs group access to the Docker socket, which
# compose grants via group_add.
RUN useradd --uid 10002 --create-home appuser \
    && chown -R appuser:appuser /app
USER 10002

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# One worker on purpose. The matchmaking queue, socket presence, grace timers and rate
# limiter are all per-process, so a second worker would behave *incorrectly*, not just
# differently (ADR-0015). Redis lifts this on Day 25.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
