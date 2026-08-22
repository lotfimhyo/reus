#!/usr/bin/env bash
# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app
# Regenerates the lockfiles (requirements.lock, requirements-dev.lock) from
# the human-authored requirements.txt/requirements-dev.txt.
#
# Why two separate files (range + lock) instead of one:
# requirements.txt stays the developer's readable intent (`fastapi>=0.110`)
# — this is what gets edited manually when adding/raising a dependency's
# floor. requirements*.lock is a fully machine-derived artifact (every
# transitive dependency pinned to an exact version) guaranteeing that any
# install — locally, in CI, or in a Docker image — gets exactly the same
# packages, not an open range that might resolve differently each time.
#
# Run this script after any manual edit to requirements.txt or
# requirements-dev.txt, and commit its result in the same commit as the edit.
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v pip-compile &> /dev/null; then
    echo "pip-tools is not installed. Install it first: pip install pip-tools --break-system-packages"
    exit 1
fi

echo "Generating requirements.lock from requirements.txt..."
pip-compile requirements.txt --output-file=requirements.lock --resolver=backtracking

echo "Generating requirements-dev.lock from requirements-dev.txt..."
pip-compile requirements-dev.txt --output-file=requirements-dev.lock --resolver=backtracking

echo ""
echo "Done. Review the diff (git diff) before committing, and check for any"
echo "unexpected upgrades to a sensitive dependency before pushing the change."
echo ""
echo "One mandatory check after every regeneration: find the uvloop line in"
echo "both files and confirm it still carries"
echo '  ; sys_platform != "win32" and platform_python_implementation != "PyPy"'
echo "pip-compile run on Linux/macOS can silently drop this marker (uvloop is"
echo "actually installed in the generating environment, so it gets frozen as"
echo "an unconditional pin). uvloop has no Windows support at all -- this is"
echo "exactly the failure a real first Setup.bat run on Windows hit. If the"
echo "marker is missing after regenerating, add it back by hand."
