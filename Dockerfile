FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app/worker

COPY worker/pyproject.toml ./pyproject.toml
COPY worker/app ./app
COPY database ./database
COPY scripts ./scripts

RUN pip install --upgrade pip setuptools wheel && pip install --no-cache-dir .

EXPOSE 8000

CMD ["sh", "-c", "python ./scripts/run_migrations.py && uvicorn app.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8000}"]
