# One image definition for every service. Pick the dependency set at build time:
#   docker build --build-arg REQUIREMENTS=api -t arbitrage-api .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

ARG REQUIREMENTS=api
WORKDIR /app

COPY requirements/ requirements/
RUN pip install -r requirements/${REQUIREMENTS}.txt

COPY shared shared
COPY services services
COPY scripts scripts
COPY experiments experiments

# Run as a non-root user; data, models and results are mounted volumes.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p data/raw data/processed models experiments/results \
    && chown -R app:app /app
USER app
