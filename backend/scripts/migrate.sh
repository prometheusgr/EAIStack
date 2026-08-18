#!/bin/bash
# Run database migrations

set -e

cd "$(dirname "$0")/.."

echo "Running database migrations..."
python -m alembic upgrade head

echo "Migrations completed successfully!"
