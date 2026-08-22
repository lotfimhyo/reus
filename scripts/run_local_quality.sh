#!/usr/bin/env bash
# Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink
# Local quality gate. PostgreSQL and Redis integration tests are intentionally
# excluded because this script promises a no-service local verification mode.
if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -x .venv/bin/pytest ]; then
  echo "No local test environment exists; run: bash scripts/reusctl.sh install" >&2
  exit 1
fi

export REUS_STORAGE_BACKEND=memory
export REUS_EVENT_BUS_BACKEND=memory
echo "Local quality gate: PostgreSQL and Redis integration tests are excluded because they require real services."
exec .venv/bin/pytest -q \
  --ignore=tests/test_alembic_migrations.py \
  --ignore=tests/test_postgres_repositories.py \
  --ignore=tests/test_redis_event_bus.py \
  "$@"
