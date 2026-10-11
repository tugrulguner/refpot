"""Presentation and family-contract regression guards."""

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAMILY_FLASK = (
    "M44 22h10v20c0 5-2.3 9.6-6.2 12.4C34.1 64.3 26 78.2 26 93"
    "c0 17 12.7 25 38 25s38-8 38-25c0-14.8-8.1-28.7-21.8-38.6"
    "C76.3 51.6 74 47 74 42V22h10"
)


class PresentationTests(unittest.TestCase):
    def test_refpot_identity_palette_and_canonical_geometry_parity(self):
        sources = [
            ROOT / "docs/assets/refpot-lockup.svg",
            ROOT / "docs/assets/refpot-execution.svg",
        ]
        copies = [
            ROOT / "website/public/refpot-lockup.svg",
            ROOT / "website/public/refpot-execution.svg",
        ]
        for source, copy in zip(sources, copies, strict=True):
            self.assertEqual(source.read_bytes(), copy.read_bytes())
            text = source.read_text()
            self.assertNotRegex(text, r"(?i)#58dfb4|#39c99a")
            self.assertIn("#F4F2EA", text)
        mark = (ROOT / "website/public/refpot-mark.svg").read_text()
        self.assertNotIn("#58DFB4", mark)
        self.assertIn("#F4F2EA", mark)
        self.assertIn("#F4F2EA", (ROOT / "website/public/social-card.svg").read_text())
        css = (ROOT / "website/src/styles/custom.css").read_text()
        self.assertIn("--mp-accent: #49515e", css)
        self.assertIn("--mp-accent: #f4f2ea", css)
        for stale in ("#58DFB4", "#39c99a", "#087a58", "#f3ead6", "#393326"):
            self.assertNotIn(stale.lower(), css.lower())
        self.assertIn("--mp-selected: #e6e8eb", css)
        self.assertIn("--mp-selected: #35383d", css)
        self.assertIn("--sl-color-text-accent: #49515e", css)
        self.assertIn("--sl-color-text-accent: #f4f2ea", css)
        self.assertIn("--sl-color-accent-high: #f4f2ea", css)

    def test_family_identity(self):
        svg = ET.parse(ROOT / "docs/assets/refpot-lockup.svg").getroot()
        self.assertEqual(svg.attrib["viewBox"], "0 0 1200 900")
        paths = [node.attrib.get("d") for node in svg.iter()]
        self.assertIn(FAMILY_FLASK, paths)
        text = " ".join(svg.itertext())
        for label in (
            "MODEPOT / OPEN SOURCE",
            "refpot",
            "A custom relational engine.",
            "A simple Python ORM.",
        ):
            self.assertIn(label, text)
        self.assertNotIn("linearGradient", {node.tag.split("}")[-1] for node in svg.iter()})

    def test_readme_family_resources_badges_and_package_first_presentation(self):
        text = (ROOT / "README.md").read_text()
        hero = text.index('width="600"')
        resources = text.index('Part of <a href="https://modepot.io/">ModePot')
        promise = text.index("<strong>A custom embedded database preview")
        ci = text.index("actions/workflows/ci.yml")
        quick = text.index("## Quick start")
        inline = text.index("from refpot import Database, Row", quick)
        current_diagram = text.index("refpot-package.png")
        status = text.index("> [!IMPORTANT]")
        self.assertEqual(
            [hero, resources, promise, ci, status, quick, inline, current_diagram],
            sorted([hero, resources, promise, ci, status, quick, inline, current_diagram]),
        )
        for link in (
            "https://modepot.io/",
            "https://refpot.modepot.io/",
            "https://tugrul.modepot.io/",
        ):
            self.assertIn(link, text[:1800])
        for phrase in (
            "Python-3.11--3.14",
            "License-MIT",
            "not a PyPI release",
            "3.04–5.95×",
            "16/16 losses",
            "docs/package-contract.md",
            "examples/crud.py",
            "examples/transactions.py",
        ):
            self.assertIn(phrase, text)
        self.assertNotIn("img.shields.io/pypi", text)
        self.assertIn("docs/assets/refpot-execution.png", text)
        self.assertIn("docs/assets/refpot-package.svg", text)

    def test_homepage_family_page_order_is_task_first_and_honest(self):
        page = (ROOT / "website/src/content/docs/index.mdx").read_text()
        markers = [
            'class="framework-hero"',
            "A custom embedded database for Python.",
            'class="framework-actions"',
            'href="/package/">Quick start',
            'href="https://github.com/tugrulguner/refpot/tree/main/examples">Examples',
            'href="https://github.com/tugrulguner/refpot">GitHub',
            "Created by Tugrul Guner",
            'class="installation-strip"',
            "Unreleased source-build preview",
            'class="planned-architecture"',
            "Run the shipped CRUD and transaction examples",
            "python examples/crud.py",
            "Package contract and qualification",
            "Planned architecture — not shipped",
            "Next — Quick start",
        ]
        positions = [page.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions))
        self.assertLess(positions[-1], page.rindex("(/package/)"))
        self.assertIn('href="/refpot-package.svg"', page)
        self.assertIn('href="/package-contract/"', page)
        self.assertIn("not a PyPI release", page)
        self.assertIn("SQL and ORM are design direction, not shipped functionality", page)
        self.assertNotIn("<iframe", page.lower())
        self.assertNotIn("Playground", page)
        self.assertIn("native package; this site does not simulate database execution", page)

    def test_package_route_and_agent_export_expose_actual_commands(self):
        quick = (ROOT / "website/src/content/docs/package.md").read_text()
        for phrase in (
            "uv pip install .",
            "python examples/crud.py",
            "python examples/transactions.py",
            "Python 3.11–3.14",
            "C++17",
            "not a PyPI release",
            "Next — Reference",
            "/package-contract/",
        ):
            self.assertIn(phrase, quick)
        agent = (ROOT / "website/public/llms.txt").read_text()
        for phrase in (
            "uv pip install .",
            "examples/crud.py",
            "examples/transactions.py",
            "not published on PyPI",
            "signed-64-bit",
            "31-byte UTF-8",
            "16/16 losses",
            "License:** MIT",
        ):
            self.assertIn(phrase, agent)

    def test_planned_boundary_and_unreleased_design_visual(self):
        text = (ROOT / "README.md").read_text()
        self.assertIn("not a PyPI release", text)
        self.assertIn("acceptance target, not an achieved package guarantee", text)
        diagram = ET.parse(ROOT / "docs/assets/refpot-execution.svg").getroot()
        labels = " ".join(diagram.itertext())
        self.assertIn("Planned architecture", labels)
        self.assertIn("not shipped", labels)
        self.assertIn("2× performance is a target, not a result", labels)

    def test_relative_links_and_anchors(self):
        text = (ROOT / "README.md").read_text()
        anchors = {
            re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
            for heading in re.findall(r"^#{1,6} (.+)$", text, re.M)
        }
        for pair in re.findall(r'(?:href|src)="([^"]+)"|\]\(([^)]+)\)', text):
            url = next(value for value in pair if value)
            if url.startswith("#"):
                self.assertIn(url[1:], anchors)
            elif not url.startswith("https://") and not url.startswith("/"):
                self.assertTrue((ROOT / url).is_file(), url)

    def test_static_accessible_svg(self):
        for path in (ROOT / "docs/assets").glob("*.svg"):
            svg = ET.parse(path).getroot()
            self.assertEqual(svg.attrib["aria-labelledby"], "title desc")
            ids = {node.attrib.get("id") for node in svg.iter()}
            self.assertTrue({"title", "desc"} <= ids)
            for node in svg.iter():
                self.assertNotIn(node.tag.split("}")[-1], {"script", "foreignObject", "image"})
                self.assertFalse(
                    any(key.startswith("on") or key.endswith("href") for key in node.attrib)
                )


if __name__ == "__main__":
    unittest.main()
