"""Exercise the archived evidence verifier in ordinary repository CI."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

DIRECTORY = Path(__file__).parents[1] / "benchmarks" / "package-performance"


def test_archived_evidence_regressions() -> None:
    result = subprocess.run(
        [sys.executable, str(DIRECTORY / "test_verify_evidence.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "relative,field",
    [
        ("baseline1000/summary.json", "refpot_speedup"),
        ("comparison.json", "sqlite_relative_speedup"),
    ],
)
def test_rehashed_summary_cannot_disagree_with_raw(
    tmp_path: Path,
    relative: str,
    field: str,
) -> None:
    evidence = tmp_path / "evidence"
    shutil.copytree(DIRECTORY / "evidence", evidence)
    path = evidence / relative
    summary = json.loads(path.read_text())
    summary["summary"][0][field] *= 10
    path.write_text(json.dumps(summary))
    manifest_path = evidence / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"][relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    result = subprocess.run(
        [sys.executable, str(DIRECTORY / "verify_evidence.py"), "--evidence-dir", str(evidence)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "mismatch" in result.stderr
