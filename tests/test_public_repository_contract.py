"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARABIC_SCRIPT = re.compile(r"[\u0600-\u06FF]")
PUBLIC_FILES = (
    "README.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "GOVERNANCE.md",
    "SUPPORT.md",
    "LICENSE_STATUS.md",
    "CHANGELOG.md",
    "docs/ARCHITECTURE.md",
    "docs/BRAND_POLICY.md",
    "docs/QUICKSTART.md",
    "docs/RELEASE_CHECKLIST.md",
    "docs/public_claims_evidence.md",
    "templates/local-settings-template.txt",
    "Run.bat",
    "Setup.bat",
    "run.sh",
    "scripts/install_local.sh",
    "scripts/package_release.sh",
    "scripts/reus_doctor.py",
    "scripts/reusctl.sh",
    "scripts/run_local_quality.sh",
    "scripts/run_node.py",
    "scripts/run_tests_isolated.sh",
    "scripts/update-lockfiles.sh",
)


def test_public_docs_and_bootstrap_surfaces_are_english():
    non_english = [relative for relative in PUBLIC_FILES if ARABIC_SCRIPT.search((ROOT / relative).read_text(encoding="utf-8"))]
    assert not non_english, f"Arabic script remains in public GitHub surfaces: {non_english}"


def test_readme_names_official_reulink_identity():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Lotfi Mahiddine" in readme
    assert "Reulink" in readme
    assert "https://reulink.app" in readme
