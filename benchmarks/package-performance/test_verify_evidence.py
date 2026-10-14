"""Regression tests for offline package benchmark evidence validation."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
VERIFIER = HERE / "verify_evidence.py"


class EvidenceVerifierTests(unittest.TestCase):
    def run_verifier(self, evidence: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VERIFIER), "--evidence-dir", str(evidence)],
            check=False,
            capture_output=True,
            text=True,
        )

    def copied_evidence(self, parent: Path) -> Path:
        target = parent / "evidence"
        shutil.copytree(EVIDENCE, target)
        return target

    def test_complete_bundle_verifies_offline(self) -> None:
        result = self.run_verifier(EVIDENCE)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["trial_records"], 300)
        self.assertEqual(report["recovery_records"], 12)
        self.assertFalse(report["global_2x_sqlite_goal_met"])

    def test_changed_raw_bytes_fail_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            evidence = self.copied_evidence(Path(temp))
            raw = evidence / "baseline1000" / "raw.jsonl"
            raw.write_bytes(raw.read_bytes() + b" ")
            result = self.run_verifier(evidence)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SHA-256 mismatch", result.stderr)

    def test_rehashed_but_invalid_timing_fails_semantic_check(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            evidence = self.copied_evidence(Path(temp))
            raw = evidence / "baseline1000" / "raw.jsonl"
            records = raw.read_text(encoding="utf-8").splitlines()
            record = json.loads(records[0])
            record["service_ns"] += 1
            records[0] = json.dumps(record, sort_keys=True)
            raw.write_text("\n".join(records) + "\n", encoding="utf-8")

            manifest_path = evidence / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"]["baseline1000/raw.jsonl"] = hashlib.sha256(
                raw.read_bytes()
            ).hexdigest()
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result = self.run_verifier(evidence)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("service time arithmetic mismatch", result.stderr)


if __name__ == "__main__":
    unittest.main()
