"""Subprocess coverage for the fixture-first public SQL-agent example."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "sql_agent.py"


def test_fixture_example_runs_twice_without_network_or_checkout_injection(tmp_path):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["TMPDIR"] = str(tmp_path)
    env.pop("OPENROUTER_API_KEY", None)
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, str(EXAMPLE)],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "Rows: ((1, 8), (3, 12))" in result.stdout
        assert "Generated query: SELECT id, quantity FROM items" in result.stdout
        assert "Parameters: (5,)" in result.stdout
        assert "Read-your-writes with ordinary SQL: ((1, 21),)" in result.stdout
        assert "Plan:" in result.stdout
        assert "Protocol fixture: no model or network calls" in result.stdout
        assert "Clarification needed: What quantity threshold should be used?" in result.stdout
        assert "Generation refused inside transaction" in result.stdout
        assert "OPENROUTER_API_KEY" not in result.stderr
