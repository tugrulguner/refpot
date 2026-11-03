"""Repository discovery gate for the isolated in-process SQL preview."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class NativeSQLTests(unittest.TestCase):
    def test_native_sql_and_outside_checkout_consumer(self):
        with tempfile.TemporaryDirectory(prefix="refpot-native-sql-") as directory:
            output = Path(directory) / "evidence"
            result = subprocess.run(
                [sys.executable, str(ROOT / "research/native-sql/run.py"), "--output", str(output)],
                cwd=ROOT,
                env={**os.environ, "TMPDIR": directory},
                text=True,
                capture_output=True,
                timeout=240,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertTrue(all(step["exit_code"] == 0 for step in manifest["steps"]))
            self.assertEqual(result.stdout.count("After commit:"), 4)
            self.assertIn("Independent SQLite query comparisons: 1680", result.stdout)
            self.assertIn("native parser prefixes=594 seeded malformed strings=4000", result.stdout)


if __name__ == "__main__":
    unittest.main()
