#!/usr/bin/env bash
# Build Script for ThirdParty Access — platform-agnostic (works on any host)
set -o errexit

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Create data directory for SQLite database
mkdir -p data

# Seed database with test accounts (only if DB doesn't exist yet)
if [ ! -f "data/database.sqlite" ]; then
    echo "First deploy — seeding database with test accounts..."
    python scripts/seed_database.py
    echo "Database seeded successfully!"
else
    echo "Database already exists, skipping seed."
    # Still initialize DB to run any new table migrations
    python -c "from app import create_app; app = create_app(); print('DB schema updated.')"
fi
