#!/usr/bin/env bash
# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app
# A single direct run script for starting the server locally without Docker.
#
# This script needs real bash (indirect variable expansion `${!var}`,
# `[[ ]]` conditionals) — it is not POSIX-sh compatible. If it's invoked
# as `sh run.sh` (a common habit, and the default on some systems where
# /bin/sh is dash, not bash), it previously failed immediately and
# confusingly at `set -o pipefail` (dash doesn't support that flag) before
# doing anything useful. Reproduced directly, not assumed. Fixed by
# re-executing itself under bash the moment that's detected.
if [ -z "${BASH_VERSION:-}" ]; then
    if command -v bash >/dev/null 2>&1; then
        exec bash "$0" "$@"
    else
        echo "❌ This script requires bash, and bash was not found on PATH." >&2
        echo "   Install bash, or run: bash run.sh (after installing it)." >&2
        exit 1
    fi
fi
#
# Why this is more than a thin wrapper around uvicorn: the "Running it" section
# in the README assumed `.env` exists and is set up with real keys — it didn't
# actually check that, so running it for the first time with no `.env` produced
# either a confusing error or (worse) a server running silently with unsafe
# default keys. This script actually checks before starting, not after.
#
# For a full run with real Postgres+pgvector and Redis, use this instead:
#   docker compose up
# This script is lighter: suited for fast dev iteration with storage_backend=memory
# (the default), with no external service needed at all.
set -euo pipefail
cd "$(dirname "$0")"

HOST="${REUS_RUN_HOST:-0.0.0.0}"
PORT="${REUS_RUN_PORT:-8000}"
RELOAD="${REUS_RUN_RELOAD:-true}"

echo "== Reus-Veritas OS — direct local run =="

# --- 1. Check .env -----------------------------------------------------------
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "⚠️  No .env found — copying from .env.example automatically now."
        echo "   Edit .env with your real keys before any non-local-dev use."
        cp .env.example .env
    else
        echo "❌ Neither .env nor .env.example exists. Cannot proceed safely."
        exit 1
    fi
fi

# shellcheck disable=SC1091
set -o allexport
source .env
set +o allexport

# --- 2. Check for unsafe default keys -----------------------------------------
UNSAFE_DEFAULTS_FOUND=false
for var_name in REUS_API_KEY REUS_USER_API_KEY; do
    value="${!var_name:-}"
    if [[ "$value" == change-me* ]] || [ -z "$value" ]; then
        echo "⚠️  $var_name is still an unsafe default/empty value."
        UNSAFE_DEFAULTS_FOUND=true
    fi
done
if [ "$UNSAFE_DEFAULTS_FOUND" = true ]; then
    echo "   Fine for local development only — set real values before any real deployment."
fi

# --- 3. Check dependencies are actually installed -----------------------------
if ! python3 -c "import fastapi, uvicorn" 2>/dev/null; then
    echo "❌ fastapi/uvicorn are not installed. Run first:"
    echo "   pip install -r requirements-dev.txt --break-system-packages"
    exit 1
fi

# --- 4. Warn if postgres is required but no encryption key is set -------------
if [ "${REUS_STORAGE_BACKEND:-memory}" = "postgres" ] && [ -z "${REUS_ENCRYPTION_KEY:-}" ]; then
    echo "❌ REUS_STORAGE_BACKEND=postgres requires REUS_ENCRYPTION_KEY. Generate one:"
    echo "   python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    exit 1
fi

# --- 4b. Warn: Telegram enabled with a placeholder/empty token produces repeated polling errors ---
if [ "${REUS_TELEGRAM_ENABLED:-false}" = "true" ]; then
    token="${REUS_TELEGRAM_BOT_TOKEN:-}"
    if [ -z "$token" ] || [[ "$token" == REDACTED* ]] || [[ "$token" == change-me* ]]; then
        echo "⚠️  REUS_TELEGRAM_ENABLED=true but REUS_TELEGRAM_BOT_TOKEN is empty/placeholder."
        echo "   The server will run normally, but repeated Telegram polling errors will appear in the log."
        echo "   Set a real token via @BotFather, or set REUS_TELEGRAM_ENABLED=false for development."
    fi
fi

# --- 4c. Warn: /chat will not actually work with the default task executor ----
# Discovered via a real live run of the full system, not theoretically: the
# default REUS_TASK_EXECUTOR ("default") does not support free-text chat at
# all — every /chat request will return 502. See
# infrastructure/default_task_executor.py for details.
executor="${REUS_TASK_EXECUTOR:-default}"
if [ "$executor" = "default" ]; then
    echo "⚠️  REUS_TASK_EXECUTOR=\"default\" (or unset) — /chat will return 502 on every request."
    echo "   To actually enable /chat, set REUS_TASK_EXECUTOR to \"ollama\" or \"model_router\" (not \"cognitive\" -- that mode needs a specific capability target, not free-text chat)."
fi

# --- 5. Actually start ---------------------------------------------------------
echo ""
echo "Server: http://${HOST}:${PORT}  (interactive docs: /docs)"
echo "storage_backend=${REUS_STORAGE_BACKEND:-memory}  event_bus_backend=${REUS_EVENT_BUS_BACKEND:-memory}"
echo ""

RELOAD_FLAG=""
if [ "$RELOAD" = "true" ]; then
    RELOAD_FLAG="--reload"
fi

exec uvicorn api.main:app --host "$HOST" --port "$PORT" $RELOAD_FLAG
