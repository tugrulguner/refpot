"""Run the matched old/new native SQL workload and verify persisted records."""

import itertools
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PackageSQLComparisonTests(unittest.TestCase):
    def test_retained_aggregates_match_raw_operations(self):
        evidence = ROOT / "research/package-sql/evidence"
        records = [json.loads(line) for line in (evidence / "raw.jsonl").read_text().splitlines()]
        aggregate = json.loads((evidence / "aggregate.json").read_text())

        def key(row):
            return row["control"], row["mode"], row["size"], row["case"]

        lookup = {key(row): row for row in records}
        self.assertEqual(len(lookup), len(records))
        self.assertEqual(len(aggregate), len(records))
        self.assertEqual({key(row) for row in aggregate}, set(lookup))
        for row in aggregate:
            original = lookup[key(row)]
            operations = original["operations"]
            self.assertEqual(row["executed_statements"], len(operations))
            self.assertEqual(row["operator_new_calls"], sum(op["new_calls"] for op in operations))
            self.assertEqual(
                row["requested_bytes"], sum(op["requested_bytes"] for op in operations)
            )
            self.assertEqual(
                row["final_table_rows"],
                {name: len(rows) for name, rows in original["final_tables"].items()},
            )

    def test_actual_native_controls_match_full_states(self):
        with tempfile.TemporaryDirectory(prefix="refpot-sql-comparison-") as directory:
            output = Path(directory) / "campaign"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "research/package-sql/run.py"),
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            records = [json.loads(line) for line in (output / "raw.jsonl").read_text().splitlines()]
            expected = set(
                itertools.product(
                    ("baseline", "package"),
                    ("overlay", "modular"),
                    (32, 128),
                    ("repeated-key", "growing-key", "create-populated"),
                )
            )
            self.assertEqual(len(records), len(expected))
            self.assertEqual(
                {(r["control"], r["mode"], r["size"], r["case"]) for r in records}, expected
            )
            self.assertTrue(
                all(sum(op["new_calls"] for op in r["operations"]) > 0 for r in records)
            )
            summary = json.loads((output / "summary.json").read_text())
            for key in (
                "all_final_states_equal",
                "all_read_your_writes",
                "all_rollbacks_verified",
                "source_hashes_unchanged",
            ):
                self.assertTrue(summary[key], key)


if __name__ == "__main__":
    unittest.main()
