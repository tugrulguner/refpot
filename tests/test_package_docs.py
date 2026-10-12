"""Regression guards for truthful unreleased package documentation and exports."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PackageDocumentationTests(unittest.TestCase):
    def test_contract_states_exact_preview_boundaries(self):
        text = (ROOT / "docs/package-contract.md").read_text()
        for phrase in (
            "not a PyPI release",
            "signed 64-bit",
            "31 encoded bytes",
            "file, not a directory",
            "thread-affine",
            "RPSNAP2",
            "two identical checksummed copies",
            "64 MiB",
            "uncertain write poisons",
            "physical power-loss safety",
        ):
            self.assertIn(phrase, text)
        self.assertNotIn(
            "broad recovery qualification",
            text.lower().replace("not broad recovery qualification", ""),
        )

    def test_readme_package_presentation_and_scoped_benchmark(self):
        text = (ROOT / "README.md").read_text()
        self.assertIn("uv pip install .", text)
        self.assertIn("not a PyPI release", text)
        self.assertIn("3.04–5.95×", text)
        self.assertIn("historical update harness", text)
        self.assertIn("16/16 losses", text)
        self.assertIn("docs/assets/refpot-package.svg", text)
        self.assertIn("docs/assets/refpot-package.png", text)

    def test_roadmap_does_not_claim_milestone_completion(self):
        text = (ROOT / "ROADMAP.md").read_text()
        self.assertIn("not a PyPI release", text)
        self.assertIn("A checked item means only that bounded deliverable exists", text)
        self.assertIn("- [x] Add package metadata, supported-platform/interpreter CI", text)
        self.assertIn("- [x] Align README, package contract, website documentation and exports", text)
        self.assertIn("- [ ] Complete native CRUD/transaction/recovery failure qualification", text)
        self.assertIn("qualification remains in progress", text)

    def test_repository_agent_guidance_stays_local_and_scoped(self):
        agents = (ROOT / "AGENTS.md").read_text()
        skill = (ROOT / "skills/refpot-database/SKILL.md").read_text()
        self.assertIn("skills/refpot-database/SKILL.md", agents)
        self.assertIn("not published on PyPI", skill)
        self.assertIn("physical power-loss", skill)
        self.assertIn("Performance is unqualified", skill)
        self.assertIn("installable [RefPot database skill](skills/refpot-database/SKILL.md)", (ROOT / "README.md").read_text())
        frontmatter = skill.split("---", 2)[1]
        import yaml

        metadata = yaml.safe_load(frontmatter)
        self.assertEqual(metadata["name"], "refpot-database")
        self.assertEqual(metadata["platforms"], ["linux", "macos"])

    def test_diagram_source_and_website_copy_are_identical_and_accessible(self):
        import xml.etree.ElementTree as ET

        svg = ROOT / "docs/assets/refpot-package.svg"
        self.assertEqual(
            svg.read_bytes(), (ROOT / "website/public/refpot-package.svg").read_bytes()
        )
        self.assertEqual(
            (ROOT / "docs/assets/refpot-package.png").read_bytes(),
            (ROOT / "website/public/refpot-package.png").read_bytes(),
        )
        root = ET.parse(svg).getroot()
        labels = " ".join(root.itertext())
        self.assertIn("UNRELEASED SOURCE-BUILD PREVIEW", labels)
        self.assertIn("Not independent physical replicas", labels)
        self.assertIn("qualification in progress", labels)
        self.assertEqual(root.attrib["aria-labelledby"], "title desc")

    def test_public_api_and_capacity_errors_are_documented(self):
        text = (ROOT / "docs/package-contract.md").read_text()
        for phrase in (
            "insert(key, value, text=",
            "get(key)",
            "update(key, *,",
            "delete(key)",
            "transaction()",
            "checkpoint()",
            "close()",
            "KeyError",
            "ValueError",
            "OverflowError",
            "TypeError",
            "creating process",
            "capacity",
        ):
            self.assertIn(phrase, text)

    def test_website_exports_and_navigation(self):
        config = (ROOT / "website/astro.config.mjs").read_text()
        sync = (ROOT / "website/scripts/sync-public-docs.mjs").read_text()
        self.assertIn("slug: 'package-contract'", config)
        self.assertIn("slug: 'package'", config)
        for path in (
            "src/content/docs/package-contract.md",
            "src/content/docs/package.md",
            "docs/package-contract.md",
            "docs/package-recommendation.md",
        ):
            self.assertIn(path, sync)
        homepage = (ROOT / "website/src/content/docs/index.mdx").read_text()
        self.assertIn("/refpot-package.png", homepage)
        self.assertIn("/refpot-package.svg", homepage)
        self.assertIn("not a PyPI release", homepage)


if __name__ == "__main__":
    unittest.main()
