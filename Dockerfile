# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.13.9
ARG POETRY_VERSION=2.3.2

# Сборка
FROM python:${PYTHON_VERSION}-slim AS builder

ARG POETRY_VERSION

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=true \
    POETRY_VIRTUALENVS_IN_PROJECT=true

RUN pip install "poetry==${POETRY_VERSION}"

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

COPY README.md ./
COPY src ./src
RUN poetry install --only main

# Рабочий образ
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}"

RUN groupadd --system --gid 10001 scraper \
 && useradd --system --uid 10001 --gid scraper --home-dir /app --no-create-home scraper \
 && find / -xdev -perm /6000 -type f -exec chmod a-s {} + 2>/dev/null || true

WORKDIR /app

COPY --from=builder --chown=root:root /app/.venv /app/.venv
COPY --from=builder --chown=root:root /app/src /app/src

USER scraper

EXPOSE 8000

ENTRYPOINT ["python", "-m", "coupon_scraper"]
CMD ["api"]
