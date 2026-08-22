#!/usr/bin/env bash
# Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink
# Build a source-only distributable archive. Runtime data, private keys,
# identity material, local env files and test caches are excluded explicitly.
if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT="${1:-$ROOT/../Reus_release_lotfi_Mahiddine.zip}"
OUTPUT="$(readlink -m "$OUTPUT")"
if [[ "$OUTPUT" == "$ROOT"/* ]]; then
  echo "ضع ملف ZIP خارج مجلد المشروع كي لا يدخل في الحزمة نفسها." >&2
  exit 2
fi
mkdir -p "$(dirname "$OUTPUT")"
rm -f "$OUTPUT"
cd "$ROOT"
zip -qr "$OUTPUT" . \
  -x '.git/*' '.venv/*' '.env' '.env.*' '__pycache__/*' '*/__pycache__/*' \
     '.pytest_cache/*' '.mypy_cache/*' 'data/*' 'storage/*' '*.sqlite' '*.sqlite3' '*.db' \
     '*.jsonl' '*.pem' '*.key' '*.raw' 'component_identity.json' 'raft_state.json' \
     'raft_state.json.snapshot' 'pending_joins.json' 'peers.json' 'trust_bundle.pem' '*.log' \
     'coverage.xml' 'htmlcov/*' 'dist/*' 'build/*' '*.zip'
echo "حزمة Reus النظيفة جاهزة: $OUTPUT"
