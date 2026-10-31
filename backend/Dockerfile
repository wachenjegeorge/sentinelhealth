FROM python:3.12-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=15

COPY backend/pyproject.toml ./
RUN pip install --prefer-binary \
        --index-url https://pypi.org/simple \
        .[dev]

COPY backend/app ./app
COPY backend/scripts ./scripts
COPY backend/migrations ./migrations
COPY backend/tests ./tests
COPY backend/alembic.ini ./
COPY frontend ./frontend

EXPOSE 8000
CMD ["uvicorn", "app.bff.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
