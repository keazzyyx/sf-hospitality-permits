# Build from the REPO ROOT (the image needs packages/catalog):
#   docker build -f apps/api/Dockerfile -t permit-memo-api .
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 UV_SYSTEM_PYTHON=1
WORKDIR /srv

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

# dependency layer
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY packages/precedent/pyproject.toml packages/precedent/pyproject.toml
RUN cd apps/api && uv pip install --system --no-cache "." 2>/dev/null || true

# source + catalog + precedent data layer
COPY packages/catalog packages/catalog
COPY packages/precedent packages/precedent
COPY apps/api apps/api
RUN uv pip install --system --no-cache ./packages/precedent ./apps/api

ARG GIT_SHA=unknown
ENV GIT_SHA=$GIT_SHA ENV=production PORT=8000 CATALOG_DIR=/srv/packages/catalog/data PRECEDENT_DATA_DIR=/srv/data PRECEDENT_RAW_DIR=/srv/data/raw
RUN mkdir -p /srv/data/raw
WORKDIR /srv/apps/api
RUN useradd -r -u 10001 permit_memo && chown -R permit_memo /srv
USER permit_memo
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD curl -fsS http://localhost:${PORT}/healthz || exit 1
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
