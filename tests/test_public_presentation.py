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
        assert "    container:\n      image: " + image in text
        assert "node-version: 22" in text
        assert "docker run" not in text
        assert "playwright install" not in text
        assert 'uv venv --managed-python --python 3.11 "$RUNNER_TEMP/refpot-presentation"' in text
        assert 'uv pip install --python "$RUNNER_TEMP/refpot-presentation/bin/python" pip' in text
        assert "import ssl; print(ssl.OPENSSL_VERSION)" in text
        for command in ("npm ci", "npm run check", "npm run build"):
            assert f"- run: {command}" in text


def test_native_source_contracts_gate_the_browser_job_from_the_host():
    text = (ROOT / ".github/workflows/website.yml").read_text()
    host = text.split("  presentation:\n")[1].split("  build:\n")[0]
    browser = text.split("  build:\n")[1]
    assert "runs-on: ubuntu-latest" in host
    assert "container:" not in host
    assert "uv sync --locked --managed-python --python 3.11" in host
    assert "python -m unittest discover -s tests -v" in host
    assert "needs: presentation" in browser
    assert "uv sync" not in browser
    assert "if: ${{ always() }}" in browser
    assert 'run: test "$PRESENTATION_RESULT" = success' in browser


def test_native_presentation_gate_fails_closed_for_every_unsuccessful_result():
    import os
    import subprocess

    for status in ("success", "failure", "cancelled", "skipped"):
        completed = subprocess.run(
            ["sh", "-c", 'test "$PRESENTATION_RESULT" = success'],
            env={**os.environ, "PRESENTATION_RESULT": status},
            check=False,
        )
        assert (completed.returncode == 0) == (status == "success")
