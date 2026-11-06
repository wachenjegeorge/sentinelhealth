#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Seeding facility data..."
python -m scripts.seed_all_facilities

echo "Starting the application..."
exec uvicorn app.combined:app --host 0.0.0.0 --port $PORT
