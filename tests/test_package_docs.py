"""Regression guards for truthful published package documentation and exports."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PackageDocumentationTests(unittest.TestCase):
    def test_contract_states_exact_preview_boundaries(self):
        text = (ROOT / "docs/package-contract.md").read_text()
        for phrase in (
            "Experimental alpha",
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
        self.assertIn("below 2×", text)
        self.assertIn("The overall **2×-over-SQLite goal remains unmet**", text)
        self.assertIn("row-local effects", text)
        self.assertNotIn("Mutation and diff-scan paths copy maps", text)
        self.assertIn("locally built wheels carrying 0.1.1 metadata", text)

    def test_readme_package_presentation_and_scoped_benchmark(self):
        text = (ROOT / "README.md").read_text()
        self.assertIn("python -m pip install refpot", text)
        self.assertIn("experimental alpha", text)
        self.assertIn("3.04–5.95×", text)
        self.assertIn("historical update harness", text)
        self.assertIn("16/16 losses", text)
        self.assertIn("docs/assets/refpot-package.svg", text)
        self.assertIn("docs/assets/refpot-package.png", text)

    def test_roadmap_does_not_claim_milestone_completion(self):
        text = (ROOT / "ROADMAP.md").read_text()
        self.assertIn("experimental alpha", text)
        self.assertIn("A checked item means only that bounded deliverable exists", text)
        self.assertIn("- [x] Configure package metadata, Python 3.11–3.14 Linux/macOS CI", text)
        self.assertIn("Implemented foundations", text)
        self.assertIn("Still-open qualification and product gates", text)
        self.assertIn("- [x] Implement fixed-schema CRUD, explicit transactions", text)
        self.assertIn("- [ ] Complete native CRUD/transaction/recovery failure qualification", text)
        self.assertIn("overall SQLite goal is unmet", text)

    def test_repository_agent_guidance_stays_local_and_scoped(self):
        agents = (ROOT / "AGENTS.md").read_text()
        skill = (ROOT / "skills/refpot-database/SKILL.md").read_text()
        self.assertIn("skills/refpot-database/SKILL.md", agents)
        self.assertIn("latest published package", skill)
        self.assertIn("physical power-loss", skill.lower())
        self.assertIn("initial six-cell performance screen", skill)
        self.assertIn("overall SQLite target is unmet", skill)
        self.assertIn(
            "installable [RefPot database skill](https://github.com/tugrulguner/refpot/blob/main/skills/refpot-database/SKILL.md)",
            (ROOT / "README.md").read_text(),
        )
        frontmatter = skill.split("---", 2)[1]
        import yaml

        metadata = yaml.safe_load(frontmatter)
        self.assertEqual(metadata["name"], "refpot-database")
        self.assertEqual(metadata["platforms"], ["linux", "macos"])

    def test_skill_install_flow_and_exact_limits_are_self_contained(self):
        skill = (ROOT / "skills/refpot-database/SKILL.md").read_text()
        for command in (
            "git clone https://github.com/tugrulguner/refpot.git",
            "cd refpot",
            "uv venv --python 3.11",
            "uv pip install --python .venv/bin/python .",
            ".venv/bin/python examples/crud.py",
            ".venv/bin/python examples/transactions.py",
        ):
            self.assertIn(command, skill)
        for boundary in ("signed 64-bit", "31 UTF-8 encoded bytes", "64 MiB", "trusted", "fork()"):
            self.assertIn(boundary, skill)
        self.assertIn("does not automatically install this agent skill", skill)

    def test_skill_python_example_runs_twice_without_existing_data(self):
        import re
        import subprocess
        import sys
        import tempfile

        skill = (ROOT / "skills/refpot-database/SKILL.md").read_text()
        examples = re.findall(r"```python\n(.*?)\n```", skill, re.DOTALL)
        self.assertEqual(len(examples), 1)
        with tempfile.TemporaryDirectory(prefix="refpot-skill-test-") as directory:
            for _ in range(2):
                result = subprocess.run(
                    [sys.executable, "-c", examples[0]],
                    cwd=directory,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Row(key=1, value=43, text='answer')", result.stdout)

    def test_new_guidance_links_are_portable_in_markdown_exports(self):
        for path in ("README.md", "website/public/docs/project-readme.md"):
            text = (ROOT / path).read_text()
            self.assertIn(
                "https://github.com/tugrulguner/refpot/blob/main/skills/refpot-database/SKILL.md",
                text,
            )
            self.assertIn("https://github.com/tugrulguner/refpot/blob/main/AGENTS.md", text)
            self.assertNotIn('href="skills/', text)
            self.assertNotIn("[RefPot database skill](skills/", text)

    def test_public_guides_execute_literal_examples_twice(self):
        import re
        import subprocess
        import sys
        import tempfile

        guides = [ROOT / "README.md", ROOT / "website/src/content/docs/package.md"]
        for guide in guides:
            text = guide.read_text()
            self.assertIn("python -m pip install refpot", text)
            examples = re.findall(r"```python\n(.*?)\n```", text, re.DOTALL)
            examples.extend(re.findall(r"python - <<'PY'\n(.*?)\nPY", text, re.DOTALL))
            self.assertEqual(len(examples), 1, guide)
            with tempfile.TemporaryDirectory(prefix="refpot-guide-") as directory:
                for _ in range(2):
                    result = subprocess.run(
                        [sys.executable, "-c", examples[0]],
                        cwd=directory,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(result.returncode, 0, f"{guide}: {result.stderr}")

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
        self.assertIn("EXPERIMENTAL ALPHA", labels)
        self.assertNotIn("0.1.2", labels)
        self.assertNotIn("RELEASE PREPARATION", labels)
        self.assertIn("Stage row-local", labels)
        self.assertIn("publish without alloc", labels)
        self.assertIn("row-local replay", labels)
        self.assertIn("qualification limited", labels)
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
        self.assertIn("experimental alpha", homepage)
        self.assertIn("/project/package-performance/", homepage)
        self.assertIn("project/package-performance", config)
        self.assertTrue((ROOT / "website/src/content/docs/project/package-performance.md").is_file())
        self.assertTrue((ROOT / "website/public/docs/project-package-performance.md").is_file())


if __name__ == "__main__":
    unittest.main()
