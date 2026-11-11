from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]


def test_current_identity_describes_shipped_database_not_future_orm():
    for path in [ROOT / "docs/assets/refpot-lockup.svg", ROOT / "website/public/social-card.svg"]:
        root = ElementTree.fromstring(path.read_text())
        text = " ".join(root.itertext())
        assert "A simple Python ORM" not in text
        assert "NOT RELEASED" not in text
        assert "not released" not in text
        assert "CRUD" in text
        assert "transactions" in text.lower()
        assert "experimental alpha" in text.lower()


def test_homepage_is_category_qualified_and_keeps_alpha_boundary():
    text = (ROOT / "website/src/content/docs/index.mdx").read_text()
    assert "title: Embedded Database for Python" in text
    assert "qualification remains limited" in text
    assert "SQL, ORM" in text
    assert "public-info-1" in text
    assert "custom relational engine and simple Python ORM" not in text


def test_website_workflows_pin_matching_playwright_runtime_image():
    image = "mcr.microsoft.com/playwright:v1.63.0-noble@sha256:eff16c30e6f3f4af0a03fa4b706120d5e9b0891c344a27d64559aff5900a4a27"
    for workflow in ["website.yml", "deploy-website.yml"]:
        text = (ROOT / ".github/workflows" / workflow).read_text()
        assert image in text
        assert "--init --shm-size=1g" in text
        assert 'git config --global --add safe.directory "$GITHUB_WORKSPACE"' in text
        assert "fetch-depth: 0" in text
        assert "astral-sh/setup-uv@d0d8abe699bfb85fec6de9f7adb5ae17292296ff" in text
        assert "npx playwright install --with-deps" not in text
        assert "uv venv --managed-python --python 3.11 /tmp/pyenv" in text
        assert "uv pip install --python /tmp/pyenv/bin/python pip" in text
        assert "npm run check && npm run build" in text
