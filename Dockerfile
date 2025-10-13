FROM python:3.13-slim AS base

ENV PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random \
    PYTHONUNBUFFERED=1

WORKDIR /src

FROM base AS builder

ENV PIP_DEFAULT_TIMEOUT=100 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
COPY --from=ghcr.io/astral-sh/uv:0.9.2 /uv /uvx /bin/

COPY pyproject.toml uv.lock ./

RUN uv pip install --system -e .

FROM base AS final

RUN apt-get update && apt-get install -y ffmpeg

COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY src ./src

ENTRYPOINT ["python", "-m", "src"]