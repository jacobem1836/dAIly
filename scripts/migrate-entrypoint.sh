#!/bin/sh
# Runs `alembic upgrade head` against DATABASE_URL, then exits.
#
# Intended to run as the `migrate` one-shot service in docker-compose.prod.yml,
# reusing the api image with this script mounted read-only and set as the
# entrypoint. alembic.ini ships with a hardcoded local dev sqlalchemy.url
# (owned by another agent's config surface) so this script rewrites the
# *runtime container's copy* of alembic.ini in place — it never touches the
# tracked source file.
set -eu

: "${DATABASE_URL:?DATABASE_URL must be set (e.g. postgresql+asyncpg://user:pass@host:5432/db)}"

sed -i "s#^sqlalchemy.url = .*#sqlalchemy.url = ${DATABASE_URL}#" alembic.ini

echo "migrate: running alembic upgrade head against ${DATABASE_URL%%://*}://<redacted>"
exec uv run alembic upgrade head
