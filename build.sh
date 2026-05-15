#!/usr/bin/env bash
# Build Script for ThirdParty Access — Render/Postgres safe
set -o errexit

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Optional local-dev SQLite directory
mkdir -p data

# Apply Alembic migrations when explicitly enabled (recommended on Render)
if [ "${RUN_DB_MIGRATIONS:-1}" = "1" ]; then
  echo "Applying database migrations..."
  flask --app run.py db upgrade
fi

# Optional seed hook for non-production environments only
if [ "${SEED_DATABASE_ON_DEPLOY:-0}" = "1" ]; then
  if [ "${FLASK_ENV:-development}" = "production" ]; then
    echo "SEED_DATABASE_ON_DEPLOY is ignored in production for safety."
  else
    echo "Seeding database (non-production)..."
    python scripts/seed_database.py
  fi
fi

echo "Build completed successfully."
