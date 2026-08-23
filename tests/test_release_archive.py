"""Project: Reus | Founder: Lotfi Mahiddine | Organization: Reulink."""
from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_archive_contains_source_only_and_excludes_local_state(tmp_path: Path):
    archive = tmp_path / "reus-source.zip"
    result = subprocess.run(
        ["bash", "scripts/package_release.sh", str(archive)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert archive.is_file()

    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()

    assert "README.md" in names
    assert "scripts/reusctl.sh" in names
    assert "templates/local-settings-template.txt" in names
    assert "tests/test_release_archive.py" in names

    forbidden_prefixes = (".git/", ".venv/", "data/", "storage/", "__pycache__/")
    forbidden_suffixes = (".pem", ".key", ".sqlite", ".sqlite3", ".db", ".jsonl", ".log")
    assert not any(name == ".env" or name.startswith(".env.") for name in names)
    assert not any(name.startswith(forbidden_prefixes) for name in names)
    assert not any(name.endswith(forbidden_suffixes) for name in names)
