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
            "not included in the currently published 0.1.2 package",
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

    def test_maintained_sql_scope_transactions_and_caps_are_explicit(self):
        text = (ROOT / "docs/sql-preview.md").read_text()
        normalized = " ".join(text.lower().split())
        for phrase in (
            "create materialized view",
            "comparisons joined with `and`",
            "one equijoin",
            "group by one key",
            "aggregate outputs need aliases",
            "only one distinct `sum` input",
            "unique and addressable",
            "order by`, `limit`, global aggregates",
            "duplicate rows and their multiplicities are preserved",
            "views are read-only",
            "create assertion name check (not exists (select * from relation))",
            "explicit transaction may temporarily violate an assertion and repair it",
            "autocommit",
            "ddl (tables, views and assertions) is forbidden inside explicit transactions",
            "ordinary executed error aborts the whole explicit transaction",
            "`explain=true` parses and binds but does not mutate or abort",
            "does not copy existing source rows",
            "100000 logical rows",
            "200000 distinct keys",
            "1000000 steps per stage/declaration",
            "1024 definitions across source and derived relations",
            "128 public relations and 128 assertions",
            "bounded intermediate can exceed its cap",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, normalized)
        self.assertIn("cumulative work counter, not a speed measure", normalized)
        self.assertIn("not included in the currently published 0.1.2 package", normalized)
        self.assertIn("published 0.1.2", normalized)

    def test_maintained_preview_has_an_unreleased_changelog_fragment(self):
        text = (ROOT / "changelog.d/+sql-maintained-relations.added.md").read_text()
        self.assertIn("unreleased source preview", text.lower())
        self.assertIn("not part of the published 0.1.2 package", text)

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
