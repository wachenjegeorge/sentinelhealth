FROM python:3.12-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=15

COPY pyproject.toml ./
RUN pip install --prefer-binary \
        --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
        --extra-index-url https://pypi.org/simple \
        .[dev]

COPY app ./app
COPY migrations ./migrations
COPY tests ./tests
COPY alembic.ini ./

EXPOSE 8000
CMD ["uvicorn", "app.bff.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
