"""Executable developer-presentation contracts, not page-count assertions."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_homepage_and_practical_guides_execute_twice(tmp_path):
    sources = [
        ROOT / "website/src/content/docs/index.mdx",
        ROOT / "docs/usage.md",
    ]
    count = 0
    for source in sources:
        for program in re.findall(r"```python\n(.*?)\n```", source.read_text(), re.S):
            compile(program, str(source), "exec")
            for _ in range(2):
                result = subprocess.run(
                    [sys.executable, "-c", program],
                    cwd=tmp_path,
                    capture_output=True,
                    text=True,
                )
                assert result.returncode == 0, f"{source}: {result.stderr}"
            count += 1
    assert count == 5


def test_guides_are_task_specific_and_have_complete_programs():
    expected = {
        "crud": ("db.delete(2)", "missing"),
        "transactions": ("cancel the group", "inside"),
        "persistence": ("db.checkpoint()", "WAL"),
        "errors": ("oversized UTF-8", "poisons"),
    }
    for slug, phrases in expected.items():
        page = ROOT / f"website/src/content/docs/build/{slug}.md"
        text = page.read_text()
        assert len(re.findall(r"```python\n", text)) == 1
        assert "from refpot import Database, Row" in text
        for phrase in phrases:
            assert phrase in text
        download = ROOT / f"website/public/docs/build-{slug}.md"
        stripped = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S).lstrip()
        stripped = re.sub(r"\n\n\[Download this page as Markdown\].*?\n$", "", stripped)
        assert download.read_text().strip() == stripped.strip()


def test_new_example_runs_twice(tmp_path):
    for _ in range(2):
        subprocess.run(
            [sys.executable, str(ROOT / "examples/quickstart.py")],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
