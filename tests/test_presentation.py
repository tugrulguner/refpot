"""Documentation-only presentation guards. Run: python3 -m unittest discover -s tests."""
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
        sources = [ROOT / "docs/assets/refpot-lockup.svg", ROOT / "docs/assets/refpot-execution.svg"]
        copies = [ROOT / "website/public/refpot-lockup.svg", ROOT / "website/public/refpot-execution.svg"]
        for source, copy in zip(sources, copies):
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
        for label in ("MODEPOT / OPEN SOURCE", "refpot", "A custom relational engine.", "A simple Python ORM."):
            self.assertIn(label, text)
        self.assertNotIn("linearGradient", {node.tag.split("}")[-1] for node in svg.iter()})

    def test_hero_hierarchy_and_community(self):
        text = (ROOT / "README.md").read_text()
        markers = ['refpot-lockup.png', 'Part of', 'Created by Tugrul Guner', '<strong>', 'Status-Unreleased', 'href="#project-status"', 'refpot-execution.png', '> [!IMPORTANT]']
        positions = [text.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('width="600"', text)
        self.assertIn('width="960"', text)
        self.assertIn('refpot-package.png', text)
        self.assertIn('docs/assets/refpot-package.svg', text)
        self.assertIn('href="https://refpot.modepot.io/"', text)
        self.assertIn('RefPot — research and design</a>', text)
        self.assertNotIn('launch pending', text)
        self.assertIn('href="https://modepot.io/"', text)
        self.assertIn('href="https://tugrul.modepot.io/"', text)
        self.assertIn('href="#community"', text)
        self.assertEqual(text.count("https://discord.gg/u3AANZr6RG"), 2)
        self.assertIn("## Community", text)
        for nonexistent_surface in ('pypi.org', 'badge/License', 'workflows/ci.yml'):
            self.assertNotIn(nonexistent_surface, text)

    def test_planned_boundary(self):
        text = (ROOT / "README.md").read_text()
        self.assertIn("not a PyPI release", text)
        self.assertIn("acceptance target, not an achieved guarantee", text)
        diagram = ET.parse(ROOT / "docs/assets/refpot-execution.svg").getroot()
        labels = " ".join(diagram.itertext())
        self.assertIn("Planned architecture", labels)
        self.assertIn("not shipped", labels)
        self.assertIn("2× performance is a target, not a result", labels)

    def test_relative_links_and_anchors(self):
        text = (ROOT / "README.md").read_text()
        anchors = {re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-") for heading in re.findall(r"^#{1,6} (.+)$", text, re.M)}
        for pair in re.findall(r'(?:href|src)="([^"]+)"|\]\(([^)]+)\)', text):
            url = next(value for value in pair if value)
            if url.startswith("#"):
                self.assertIn(url[1:], anchors)
            elif not url.startswith("https://"):
                self.assertTrue((ROOT / url).is_file(), url)

    def test_static_accessible_svg(self):
        for path in (ROOT / "docs/assets").glob("*.svg"):
            svg = ET.parse(path).getroot()
            self.assertEqual(svg.attrib["aria-labelledby"], "title desc")
            ids = {node.attrib.get("id") for node in svg.iter()}
            self.assertTrue({"title", "desc"} <= ids)
            for node in svg.iter():
                self.assertNotIn(node.tag.split("}")[-1], {"script", "foreignObject", "image"})
                self.assertFalse(any(key.startswith("on") or key.endswith("href") for key in node.attrib))


if __name__ == "__main__":
    unittest.main()
