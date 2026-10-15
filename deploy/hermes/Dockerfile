# Build context: repository root. Upstream Hermes stays unmodified and pinned.
FROM python:3.12-slim-bookworm
ARG HERMES_COMMIT=f97608f178d1ffeca59860195ab7da295f7c8e5f
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates build-essential libffi-dev \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.11.6
WORKDIR /opt/hermes
RUN git init . && git remote add origin https://github.com/NousResearch/hermes-agent.git \
    && git fetch --depth 1 origin "$HERMES_COMMIT" && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "$HERMES_COMMIT" \
    && uv sync --frozen --no-dev --python /usr/local/bin/python \
    && rm -rf .git
RUN groupadd --gid 10001 ce && useradd --uid 10001 --gid 10001 --no-create-home ce
COPY deploy/hermes/runner.py /opt/ce/runner.py
ENV PATH="/opt/hermes/.venv/bin:$PATH" PYTHONPATH=/opt/hermes \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HERMES_HOME=/tmp/ce-hermes \
    HOME=/tmp AWS_EC2_METADATA_DISABLED=true
USER 10001:10001
WORKDIR /input
ENTRYPOINT ["/opt/hermes/.venv/bin/python", "/opt/ce/runner.py"]
