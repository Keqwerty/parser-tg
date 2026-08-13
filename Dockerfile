FROM ghcr.io/astral-sh/uv:0.12.1@sha256:cf4eedcaa81655197f625739489effcbe71b61ceb1506f332c3facae5deceded AS uv

FROM python:3.13.15-slim-trixie@sha256:ffb752e139c0a19692a43af8d8523b274222dd68eebad5d583b45c2201c6e30a AS builder
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.13.15-slim-trixie@sha256:ffb752e139c0a19692a43af8d8523b274222dd68eebad5d583b45c2201c6e30a AS runtime
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

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["parser-tg", "healthcheck"]

ENTRYPOINT ["parser-tg"]
CMD ["run"]
