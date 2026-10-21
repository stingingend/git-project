FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 codeatlas
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install '.[postgres]'
USER codeatlas
EXPOSE 8001
# One worker: ingestion and parsing currently share an in-process lock.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
