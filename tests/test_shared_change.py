"""Discover the isolated native foundation experiment in repository CI."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SharedChangeTests(unittest.TestCase):
    def test_native_modes_and_full_state_controls(self):
        with tempfile.TemporaryDirectory(prefix="refpot-shared-change-") as directory:
            output = Path(directory) / "evidence"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "research/shared-change/run.py"),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=240,
                env={**os.environ, "TMPDIR": directory},
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            records = [
                json.loads(line) for line in (output / "records.jsonl").read_text().splitlines()
            ]
            self.assertEqual(len(records), 40)
            self.assertTrue(all(r["oracle_equal"] and r["sqlite_equal"] for r in records))
            for mode in ("modular", "overlay"):
                for publish in (False, True):
                    for _ in range(2):
                        command = [
                            sys.executable,
                            str(ROOT / "examples/experimental_shared_change.py"),
                            "--driver",
                            str(output / mode),
                        ]
                        if publish:
                            command.append("--publish")
                        demo = subprocess.run(
                            command, cwd=directory, capture_output=True, text=True, timeout=30
                        )
                        self.assertEqual(demo.returncode, 0, demo.stdout + demo.stderr)
                        self.assertIn("Published." if publish else "Discarded.", demo.stdout)


if __name__ == "__main__":
    unittest.main()
