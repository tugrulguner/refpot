"""Executable comparison and oracle-mutation checks for maintained SQL."""

import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "research" / "sql-maintenance"
SPEC = importlib.util.spec_from_file_location("maintenance_matched", DIRECTORY / "matched.py")
assert SPEC is not None and SPEC.loader is not None
MATCHED = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MATCHED)


class MaintenanceControlTests(unittest.TestCase):
    def test_sqlite_and_installed_candidate_match_every_transition(self):
        control = MATCHED.run("sqlite")
        expected_count = sum(
            len(txns) for txns in json.loads(MATCHED.PLAN.read_text())["workloads"].values()
        )
        self.assertEqual(MATCHED.validate(control), expected_count)
        for mode in ("overlay", "modular"):
            with self.subTest(mode=mode):
                candidate = MATCHED.run("native", mode)
                self.assertEqual(MATCHED.validate(candidate), expected_count)
                self.assertEqual(candidate["records"], control["records"])

    def test_oracle_rejects_actual_rollback_and_dropped_write_mutants(self):
        for mutant in ("commit-rollback", "drop-operation"):
            with self.subTest(mutant=mutant), self.assertRaises(AssertionError):
                MATCHED.run("sqlite", mutant=mutant)

    def test_persisted_validation_rejects_omitted_and_corrupted_history(self):
        baseline = MATCHED.run("sqlite")
        missing = copy.deepcopy(baseline)
        missing["records"][0]["history"].pop()
        with self.assertRaises(AssertionError):
            MATCHED.validate(missing)
        corrupt = copy.deepcopy(baseline)
        corrupt["records"][0]["history"][0]["state"]["fact"][0][2] += 1
        with self.assertRaises(AssertionError):
            MATCHED.validate(corrupt)


if __name__ == "__main__":
    unittest.main()
