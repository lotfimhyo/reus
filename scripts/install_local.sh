#!/usr/bin/env bash
# Project: Reus | Developer: lotfi Mahiddine | Organization: Reulink
# Safe local-first installer. It never enables cloud services, Telegram,
# database storage, cluster peering, or external model providers.
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: Python 3.11+ is required. Install Python, then rerun this script." >&2
  exit 1
fi

PYTHON_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
case "$PYTHON_VERSION" in
  3.1[1-9]|3.[2-9][0-9]) ;;
  *) echo "ERROR: Python 3.11+ is required; found $PYTHON_VERSION." >&2; exit 1 ;;
esac

if [ ! -d .venv ]; then
  python3 -m venv .venv || {
    echo "ERROR: Could not create .venv. Install the Python venv package and retry." >&2
    exit 1
  }
fi

".venv/bin/python" -m pip install --upgrade pip
".venv/bin/python" -m pip install -r requirements-dev.txt

if [ ! -f .env ]; then
  cp .env.example .env
fi
".venv/bin/python" scripts/generate_local_env.py --enable-local-chat
chmod 600 .env 2>/dev/null || true

echo ""
echo "Reus local environment is ready."
if command -v ollama >/dev/null 2>&1; then
  echo "Ollama found. Ensure its service is running and pull the configured model before starting Reus."
else
  echo "Ollama was not found. Install it and pull the model declared by REUS_OLLAMA_MODEL in .env before chat use."
fi
echo "Start Reus with: .venv/bin/bash run.sh"
echo "Keep .env private; it contains generated local API secrets."
