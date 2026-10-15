# syntax=docker/dockerfile:1.7

# ============================================================
# Stage 1 - build the wheel
# ============================================================
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

# Build dependencies; repository inspection only needs git at runtime.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Exact source allowlist - never COPY the whole workspace.
COPY pyproject.toml LICENSE NOTICE README.md ./
COPY rgce/ ./rgce/

RUN python -m pip install --upgrade pip build \
 && python -m build --wheel --outdir /dist

# ============================================================
# Stage 2 - runtime
# ============================================================
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    GIT_CONFIG_NOSYSTEM=1 \
    GIT_TERMINAL_PROMPT=0 \
    RGCE_HOME=/data \
    RGCE_CONTAINER=1 \
    RGCE_PORT=8765

# git is required for repository reads at runtime.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 rgce \
 && useradd --uid 10001 --gid 10001 --no-log-init \
      --create-home --home-dir /home/rgce --shell /usr/sbin/nologin rgce \
 && install -d -o 10001 -g 10001 -m 0750 /data

COPY --from=builder /dist /dist

RUN WHEEL="$(ls /dist/*.whl)" \
 && python -m pip install --no-cache-dir "${WHEEL}[aws,documents]" \
 && rm -rf /dist \
 && install -d -m 0755 /usr/share/doc/rgce

COPY LICENSE NOTICE README.md /usr/share/doc/rgce/
COPY deploy/hermes/broker.py /usr/share/rgce/hermes/broker.py

USER 10001:10001
WORKDIR /data
VOLUME ["/data"]
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/session', timeout=4)"]

ENTRYPOINT ["python", "-m", "rgce"]
CMD ["--home", "/data", "serve", "--container-bind"]
