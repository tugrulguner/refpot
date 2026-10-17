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
