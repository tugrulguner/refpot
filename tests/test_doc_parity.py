"""README-to-site evidence coverage and immutable-artwork guards."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_every_readme_supporting_image_has_a_homepage_consumer():
    readme = (ROOT / "README.md").read_text()
    homepage = (ROOT / "website/src/content/docs/index.mdx").read_text()
    illustrations = re.findall(r'src="docs/assets/(refpot-[^"?]+\.png)(?:\?[^"]*)?"', readme)
    assert set(illustrations) == {
        "refpot-lockup.png",
        "refpot-execution.png",
        "refpot-package.png",
        "refpot-benchmark.png",
    }
    for filename in illustrations:
        assert homepage.count(f'src="/{filename}') == 1, filename
        assert (ROOT / "docs/assets" / filename).read_bytes() == (
            ROOT / "website/public" / filename
        ).read_bytes()


def test_benchmark_has_full_results_and_reproduction_in_hosted_docs():
    page = (ROOT / "website/src/content/docs/project/benchmarks.md").read_text()
    for phrase in (
        "672 records",
        "100,000 rows / 1 clients",
        "1,000,000 rows / 64 clients",
        "slower for native in all 16 cells",
        "not an ordinary update-only SQLite baseline",
        "Linux ARM64",
        "not physical power-loss validation",
        "reproduce.py verify",
        "reproduce.py smoke",
        "about 10 hours",
        "data/raw-records.tar.gz",
        "AUDIT.md",
    ):
        assert phrase in page
    assert "![" in page and "/refpot-benchmark.png" in page
    method = (ROOT / "website/src/content/docs/performance-method.md").read_text()
    assert "/refpot-benchmark.png" in method
    assert "/project/benchmarks/" in method


def test_evidence_is_discoverable_without_erasing_alpha_boundaries():
    home = (ROOT / "website/src/content/docs/index.mdx").read_text()
    for phrase in (
        "Historical benchmark findings",
        "3.04–5.95×",
        "16/16 losses",
        "not a package claim",
        "/project/benchmarks/",
        "/project/contributing/",
        "/reference/agent-guide/",
    ):
        assert phrase in home
    assert "Package performance is unqualified" in home
    for source in ["website/astro.config.mjs", "website/src/components/FamilyHeader.astro"]:
        assert "project/benchmarks" in (ROOT / source).read_text()


def test_package_report_distinguishes_recorded_labels_from_build_provenance():
    for relative in (
        "benchmarks/package-performance/RESULTS.md",
        "website/src/content/docs/project/package-performance.md",
        "website/public/docs/project-package-performance.md",
    ):
        text = (ROOT / relative).read_text()
        assert "operator-supplied" in text
        assert "extension hashes, not wheel hashes" in text
        assert "not a verified source-to-artifact attestation" in text
        assert "Source identities and wheel hashes" not in text


def test_package_performance_results_are_exported_and_links_resolve():
    source = (ROOT / "benchmarks/package-performance/RESULTS.md").read_text()
    route = ROOT / "website/src/content/docs/project/package-performance.md"
    download = ROOT / "website/public/docs/project-package-performance.md"
    assert route.is_file() and download.is_file()
    page = route.read_text()
    assert "Recomputed result matrix" in page
    assert "Separate recovery diagnostic" in page
    assert "## Limits" in page
    assert "Protocol and provenance" in page
    assert "source revisions pinned below" in page
    assert "/docs/project-package-performance.md" in page
    assert "(benchmarks/package-performance/verify_evidence.py)" not in page
    assert "(evidence/frozen-harness.py)" not in page
    assert "python3 benchmarks/package-performance/verify_evidence.py" in page
    assert "python benchmarks/package-performance/recovery_fixture.py" in page
    assert "locally built wheels carrying `0.1.1` version metadata" in source
    assert "### Limits" in source
    contract = (ROOT / "website/src/content/docs/package-contract.md").read_text()
    assert "](/project/package-performance/)" in contract
    assert "(../benchmarks/package-performance/RESULTS.md)" not in contract
    assert re.search(
        r"\(https://github\.com/tugrulguner/refpot/tree/[a-f0-9]{40}/benchmarks/package-performance\)",
        contract,
    )
    assert (
        "https://github.com/tugrulguner/refpot/tree/main/benchmarks/package-performance"
        not in contract
    )
