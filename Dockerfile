FROM ghcr.io/astral-sh/uv:0.12.1 AS uv

FROM python:3.13-slim AS builder
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.13-slim AS runtime
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN groupadd --gid 10001 parser \
    && useradd --uid 10001 --gid parser --no-create-home --shell /usr/sbin/nologin parser \
    && mkdir -p /app/config /data \
    && chown -R parser:parser /app /data

WORKDIR /app
COPY --from=builder --chown=parser:parser /app/.venv /app/.venv
USER parser

ENTRYPOINT ["parser-tg"]
CMD ["run"]
