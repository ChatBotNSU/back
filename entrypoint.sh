#!/usr/bin/env sh
set -e

# Run DB migrations on boot when RUN_MIGRATIONS=1 (set on the api service only,
# so the worker doesn't race it).
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  echo "Applying Alembic migrations..."
  alembic upgrade head
fi

exec "$@"
