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
  echo "Place the ZIP archive outside the project directory so it cannot include itself." >&2
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
echo "Clean Reus source archive is ready: $OUTPUT"
