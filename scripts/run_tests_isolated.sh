#!/usr/bin/env bash
# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app
# Runs every test file in a completely separate Python process.
#
# Status of this script: it used to be required as a workaround for a real
# hang caused by an interaction between live mTLS server threads and
# RLIMIT_AS in infrastructure/cognitive_core/resource/sandbox.py's isolation
# — precisely diagnosed (an absolute memory ceiling smaller than the actual
# virtual size inherited via fork, measured by VmSize not RSS) and fixed at
# the root there. Proof: 276 tests now pass in a single process via `pytest`
# directly with no hang at all (see the session log).
#
# This script is kept as a useful optional diagnostic tool (instant isolation
# of any test file that fails for some other, unrelated reason in the
# future), not because it's still necessary. CI now uses `pytest` directly —
# see .github/workflows/ci.yml.
set -uo pipefail

cd "$(dirname "$0")/.."

FAILED_FILES=()
PASSED=0
FAILED=0

for test_file in tests/test_*.py; do
    if python3 -m pytest -q "$test_file" > /tmp/"$(basename "$test_file")".log 2>&1; then
        PASSED=$((PASSED + 1))
    else
        FAILED=$((FAILED + 1))
        FAILED_FILES+=("$test_file")
        echo "❌ FAILED: $test_file"
        tail -n 30 /tmp/"$(basename "$test_file")".log
        echo "---"
    fi
done

echo ""
echo "===================================="
echo "  Passed files: $PASSED"
echo "  Failed files: $FAILED"
echo "===================================="

if [ "$FAILED" -ne 0 ]; then
    echo "Failing test files:"
    printf '  - %s\n' "${FAILED_FILES[@]}"
    exit 1
fi

exit 0
