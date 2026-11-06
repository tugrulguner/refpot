"""Public contract guard for the unreleased SQL preview documentation."""

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

    def test_canonical_surfaces_do_not_describe_all_sql_as_volatile_only(self):
        for relative in (
            "AGENTS.md",
            "README.md",
            "ROADMAP.md",
            "docs/package-contract.md",
            "docs/sql-preview.md",
            "docs/maintained-sql-design.md",
            "skills/refpot-database/SKILL.md",
        ):
            text = (ROOT / relative).read_text().lower()
            with self.subTest(path=relative):
                self.assertNotIn("in-memory sql preview", text)
                self.assertNotIn(
                    "sql preview uses separate in-memory state and has no persistence", text
                )
                self.assertNotIn("volatile, in-development sql preview", text)

    def test_sql_preview_doc_is_unreleased_scoped_and_complete(self):
        doc = ROOT / "docs/sql-preview.md"
        self.assertTrue(doc.exists(), "the canonical preview contract is missing")
        text = doc.read_text()
        for phrase in (
            "not included in the currently published 0.1.2 package",
            "volatile",
            "Database(path=None",
            'Database(path=None, *, mode="overlay")',
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
            "64 MiB",
            "128 MiB",
            "all changed bags",
            "does not checkpoint",
            "poisons the writer",
            "physical power-loss safety",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase.lower(), text.lower())
        self.assertNotIn("ctypes.CDLL", text)
        self.assertNotIn("--library", text)
        self.assertNotIn("M1 is complete", text)
        self.assertNotIn("SQLite's integer-overflow-to-float behavior", text)
        self.assertIn("SQLite integer `SUM` raises on intermediate integer overflow", text)
        self.assertIn("not included", text.lower())
        self.assertNotIn("has no persistence", text.lower())
        self.assertNotIn("no durable storage", text.lower())

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

    def test_persistent_example_is_documented_and_exercises_recovery(self):
        example = ROOT / "examples/sql_persistence.py"
        self.assertTrue(example.exists(), "the documented persistence example is missing")
        text = example.read_text()
        self.assertIn("Database(path", text)
        self.assertIn('Database(path, mode="modular")', text)
        self.assertIn("resource_exists", text)
        self.assertIn("capacity_ok", text)
        self.assertIn("Database(path)", text)
        self.assertIn("db.checkpoint()", text)
        doc = (ROOT / "docs/sql-preview.md").read_text()
        self.assertIn("examples/sql_persistence.py", doc)
        self.assertIn("does not mark roadmap M1, M3, or M4 complete", doc)

    def test_definition_evolution_contract_and_consumers(self):
        doc = (ROOT / "docs/sql-preview.md").read_text()
        for phrase in (
            "ALTER MATERIALIZED VIEW",
            "same output column names and order",
            "transitive",
            "old or new",
            "examples/sql_evolution.py",
            "older preview binaries",
            "one view",
            "outside explicit transactions",
        ):
            self.assertIn(phrase, doc)
        for name in ("README.md", "docs/package-contract.md", "skills/refpot-database/SKILL.md"):
            self.assertIn("sql_evolution.py", (ROOT / name).read_text())
        for name in (".github/workflows/package.yml", ".github/workflows/wheels.yml"):
            workflow = (ROOT / name).read_text()
            self.assertIn("test_sql_evolution.py", workflow)
            self.assertIn("test_sql_evolution_failures.py", workflow)
            self.assertEqual(workflow.count("examples/sql_evolution.py"), 2)
        roadmap = (ROOT / "ROADMAP.md").read_text()
        self.assertIn("ALTER MATERIALIZED VIEW", roadmap)
        self.assertIn("- [ ] Implement offline atomic schema/definition migration", roadmap)

    def test_initial_preview_fragment_is_retained(self):
        fragment = ROOT / "changelog.d/+volatile-native-sql-preview.added.md"
        self.assertTrue(fragment.exists())
        self.assertIn("unreleased", fragment.read_text().lower())

    def test_whole_model_persistence_has_unreleased_changelog_fragment(self):
        fragment = ROOT / "changelog.d/+sql-whole-model-persistence.added.md"
        self.assertTrue(fragment.exists())
        text = fragment.read_text().lower()
        for phrase in ("unreleased", "whole-model", "not part of the published 0.1.2 package"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
