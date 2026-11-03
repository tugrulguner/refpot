"""Public contract guard for the unreleased volatile SQL preview docs."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SQLPreviewDocsTests(unittest.TestCase):
    def test_preview_contract_is_linked_without_replacing_fixed_schema_api(self):
        readme = (ROOT / "README.md").read_text()
        contract = (ROOT / "docs/package-contract.md").read_text()
        self.assertIn("docs/sql-preview.md", readme)
        self.assertIn("sql-preview.md", contract)
        self.assertIn("from refpot import Database, Row", contract)
        self.assertIn("from refpot.sql import Database, Result, SQLError", contract)
        self.assertIn("Database(path)", contract)
        self.assertIn(
            "caught validation/missing/duplicate error does not undo earlier valid staged operations",
            contract,
        )
        self.assertIn("not included in the currently published package", contract)
        self.assertIn("examples/sql_preview.py", readme)

    def test_sql_preview_doc_is_unreleased_scoped_and_complete(self):
        doc = ROOT / "docs/sql-preview.md"
        self.assertTrue(doc.exists(), "the canonical preview contract is missing")
        text = doc.read_text()
        for phrase in (
            "not included in the currently published package",
            "volatile",
            "Database()",
            'mode="overlay"',
            'mode="modular"',
            "transaction()",
            "stats()",
            "explain=True",
            "process and thread that created it",
            "signed 64-bit",
            "SUM",
            "whole explicit transaction",
            "examples/sql_preview.py",
            "M1",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase.lower(), text.lower())
        self.assertNotIn("ctypes.CDLL", text)
        self.assertNotIn("--library", text)
        self.assertNotIn("M1 is complete", text)
        self.assertNotIn("SQLite's integer-overflow-to-float behavior", text)
        self.assertIn("SQLite integer `SUM` raises on intermediate integer overflow", text)
        self.assertIn("not included", text.lower())

    def test_runnable_example_uses_only_the_public_preview_api(self):
        example = ROOT / "examples/sql_preview.py"
        self.assertTrue(example.exists(), "the documented source example is missing")
        text = example.read_text()
        self.assertIn("from refpot.sql import Database", text)
        self.assertIn(".execute(", text)
        self.assertIn(".transaction()", text)
        self.assertNotIn("ctypes.CDLL", text)
        self.assertNotIn("--library", text)
        self.assertNotIn("sys.path", text)

    def test_only_the_native_sql_preview_changelog_is_added(self):
        fragments = list((ROOT / "changelog.d").glob("+volatile-native-sql-preview.added.md"))
        self.assertEqual(len(fragments), 1)
        self.assertIn("unreleased", fragments[0].read_text().lower())


if __name__ == "__main__":
    unittest.main()
