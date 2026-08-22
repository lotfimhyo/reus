#!/usr/bin/env bash
# Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink
# Unified local control surface. It favors explicit safe actions over hidden
# background processes or implicit cloud configuration.
if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
COMMAND="${1:-help}"
shift || true

usage() {
  cat <<'EOF'
استخدام Reus المحلي:
  bash scripts/reusctl.sh install                 تهيئة .venv و.env محلي آمن
  bash scripts/reusctl.sh doctor [--strict]       فحص غير معدّل للجاهزية
  bash scripts/reusctl.sh start-core              فحص صارم ثم تشغيل API المحلية
  bash scripts/reusctl.sh start-node <args...>    تشغيل عقدة Reus (مرّر --role و--data-dir)
  bash scripts/reusctl.sh start-first-node         عقدة أولى محلية (text-node)
  bash scripts/reusctl.sh join-node --seed-url URL عقدة تابعة محلية (cipher-node)

لا يشغّل هذا الأمر Telegram أو Kimi أو Supabase أو أي نشر سحابي تلقائياً.
EOF
}

case "$COMMAND" in
  install) exec bash scripts/install_local.sh "$@" ;;
  doctor)
    if [ -x .venv/bin/python ]; then
      exec .venv/bin/python scripts/reus_doctor.py "$@"
    fi
    exec python3 scripts/reus_doctor.py "$@"
    ;;
  start-core)
    if [ ! -x .venv/bin/python ]; then
      echo "لا توجد بيئة .venv؛ شغّل: bash scripts/reusctl.sh install" >&2
      exit 1
    fi
    .venv/bin/python scripts/reus_doctor.py --strict
    exec .venv/bin/bash run.sh "$@"
    ;;
  start-node)
    if [ ! -x .venv/bin/python ]; then
      echo "لا توجد بيئة .venv؛ شغّل: bash scripts/reusctl.sh install" >&2
      exit 1
    fi
    .venv/bin/python scripts/reus_doctor.py
    exec .venv/bin/python scripts/run_node.py "$@"
    ;;
  start-first-node)
    if [ ! -x .venv/bin/python ]; then
      echo "لا توجد بيئة .venv؛ شغّل: bash scripts/reusctl.sh install" >&2
      exit 1
    fi
    .venv/bin/python scripts/reus_doctor.py
    exec .venv/bin/python scripts/run_node.py \
      --role "${REUS_FIRST_NODE_ROLE:-text-node}" \
      --data-dir "${REUS_FIRST_NODE_DATA_DIR:-$HOME/.local/share/reus/node-a}" \
      --mtls-host "${REUS_NODE_BIND_HOST:-127.0.0.1}" \
      --mtls-port "${REUS_FIRST_NODE_MTLS_PORT:-8443}" \
      --bootstrap-host "${REUS_NODE_BIND_HOST:-127.0.0.1}" \
      --bootstrap-port "${REUS_FIRST_NODE_BOOTSTRAP_PORT:-8080}" \
      "$@"
    ;;
  join-node)
    if [ ! -x .venv/bin/python ]; then
      echo "لا توجد بيئة .venv؛ شغّل: bash scripts/reusctl.sh install" >&2
      exit 1
    fi
    if [[ " $* " != *" --seed-url "* ]]; then
      echo "يتطلب join-node عنوان العقدة الأولى: --seed-url http://HOST:8080" >&2
      exit 2
    fi
    .venv/bin/python scripts/reus_doctor.py
    exec .venv/bin/python scripts/run_node.py \
      --role "${REUS_JOIN_NODE_ROLE:-cipher-node}" \
      --data-dir "${REUS_JOIN_NODE_DATA_DIR:-$HOME/.local/share/reus/node-b}" \
      --mtls-host "${REUS_NODE_BIND_HOST:-127.0.0.1}" \
      --mtls-port "${REUS_JOIN_NODE_MTLS_PORT:-8444}" \
      --bootstrap-host "${REUS_NODE_BIND_HOST:-127.0.0.1}" \
      --bootstrap-port "${REUS_JOIN_NODE_BOOTSTRAP_PORT:-8081}" \
      "$@"
    ;;
  help|-h|--help) usage ;;
  *) echo "أمر غير معروف: $COMMAND" >&2; usage >&2; exit 2 ;;
esac
