FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip wheel --no-deps --wheel-dir /wheels .

FROM python:3.12-slim AS runtime

ARG APP_UID=10001
ARG APP_GID=10001
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/tmp \
    AGENT_KB_TENANT_DB_ROOT=/data/tenants \
    AGENT_KB_BACKUP_ROOT=/data/backups

RUN groupadd --gid ${APP_GID} agentkb \
    && useradd --uid ${APP_UID} --gid ${APP_GID} --no-create-home --shell /usr/sbin/nologin agentkb \
    && mkdir -p /app/domains /data/tenants /data/backups /tmp/agent-kb \
    && chown -R ${APP_UID}:${APP_GID} /app /data /tmp/agent-kb

COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/*.whl \
    && rm -rf /wheels
COPY --chown=${APP_UID}:${APP_GID} domains /app/domains

WORKDIR /app
USER ${APP_UID}:${APP_GID}
EXPOSE 8080
VOLUME ["/data"]

CMD ["agent-kb", "--help"]
