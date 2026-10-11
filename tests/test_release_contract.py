from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReleaseContractTests(unittest.TestCase):
    def test_metadata_has_single_version_and_honest_platform_bounds(self) -> None:
        data = tomllib.loads((ROOT / "pyproject.toml").read_text())
        project = data["project"]
        self.assertEqual(project["version"], "0.1.1")
        self.assertEqual(project["requires-python"], ">=3.11,<3.15")
        self.assertEqual(project["license"], "MIT")
        self.assertIn("LICENSE", project["license-files"])
        self.assertEqual(project["authors"], [{"name": "Tugrul Guner"}])
        self.assertNotIn("Windows", " ".join(project["classifiers"]))
        self.assertNotIn("Free Threading", " ".join(project["classifiers"]))

    def test_required_workflows_are_pinned_and_scoped(self) -> None:
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        wheels = (ROOT / ".github/workflows/wheels.yml").read_text()
        release = (ROOT / ".github/workflows/release.yml").read_text()
        for version in ("3.11", "3.12", "3.13", "3.14"):
            self.assertIn(f"'{version}'", ci)
            self.assertIn(f"python: '{version}'", wheels)
        self.assertIn("ubuntu-latest, macos-latest", ci)
        self.assertIn("contents: write", release)
        self.assertIn("id-token: write", release)
        self.assertIn("environment: pypi", release)
        self.assertIn("uv sync --all-groups --locked", ci)
        self.assertNotIn("windows-latest", wheels)
        self.assertNotIn("3.14t", wheels)
        for workflow in (ci, wheels, release):
            for line in workflow.splitlines():
                if "uses:" in line and "./.github/" not in line:
                    self.assertRegex(line, r"@[0-9a-f]{40} # v")

    def test_changelog_requires_current_pr_fragments_and_unique_orphan(self) -> None:
        workflow = (ROOT / ".github/workflows/changelog.yml").read_text()
        config = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["towncrier"]
        self.assertIn("labeled, unlabeled", workflow)
        self.assertIn("skip-changelog", workflow)
        self.assertIn("orphan slug collision", workflow)
        self.assertEqual(config["directory"], "changelog.d")
        self.assertTrue((ROOT / "changelog.d/+engine-package.added.md").is_file())
        self.assertIn("must be unique", (ROOT / "CONTRIBUTING.md").read_text())

    def test_release_verifier_accepts_version_and_rejects_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "pyproject.toml").write_text((ROOT / "pyproject.toml").read_text())
            (root / "CHANGELOG.md").write_text(
                "# Changelog\n\n## [0.1.1] - 2026-01-01\n\n- Released.\n"
            )
            env = dict(os.environ, RELEASE_TAG="v0.1.1")
            good = subprocess.run(
                [sys.executable, str(ROOT / "scripts/verify_release.py")],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(good.returncode, 0, good.stderr)
            bad = subprocess.run(
                [sys.executable, str(ROOT / "scripts/verify_release.py")],
                cwd=root,
                env=dict(env, RELEASE_TAG="v9.9.9"),
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(bad.returncode, 0)

    def test_release_routes_exact_wheels_sdist_and_avoids_artifact_collisions(self) -> None:
        wheels = (ROOT / ".github/workflows/wheels.yml").read_text()
        release = (ROOT / ".github/workflows/release.yml").read_text()
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("name: source-dist-${{ github.run_id }}-${{ github.run_attempt }}", wheels)
        self.assertIn("needs: source", wheels)
        self.assertIn("package-dir: ${{ env.SOURCE_ROOT }}", wheels)
        self.assertIn('"$SOURCE_ROOT"/tests/test_database.py', wheels)
        self.assertIn("source-dist-${{ github.run_id }}-${{ github.run_attempt }}", release)
        self.assertNotIn("uv build --sdist", release)
        self.assertIn("uv build", ci)
        self.assertIn("twine check dist/*.whl dist/*.tar.gz", ci)
        self.assertIn("dist/*.whl dist/*.tar.gz", release)

    def test_artifact_validator_checks_real_built_distributions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            dist = Path(temporary)
            wheel = dist / "refpot-0.1.1-py3-none-any.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                for name in (
                    "refpot/__init__.py",
                    "refpot/_core.pyi",
                    "refpot/py.typed",
                    "refpot-0.1.1.dist-info/licenses/LICENSE",
                    "refpot-0.1.1.dist-info/METADATA",
                ):
                    archive.writestr(
                        name,
                        "Metadata-Version: 2.4\nName: refpot\nVersion: 0.1.1\nLicense-Expression: MIT\n\n"
                        if name.endswith("METADATA")
                        else "test",
                    )
            sdist = dist / "refpot-0.1.1.tar.gz"
            with tarfile.open(sdist, "w:gz") as archive:
                for name in (
                    "src/refpot/native/core.cpp",
                    "src/refpot/CMakeLists.txt",
                    "src/refpot/LICENSE",
                    "src/refpot/tests/test_database.py",
                    "src/scripts/verify_artifacts.py",
                ):
                    data = b"test"
                    import io

                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    archive.addfile(info, io.BytesIO(data))
            result = subprocess.run(
                [sys.executable, "scripts/verify_artifacts.py", str(dist)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(wheel) as archive:
                self.assertTrue(
                    any(name.endswith("licenses/LICENSE") for name in archive.namelist())
                )
            digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
            self.assertEqual(len(digest), 64)


if __name__ == "__main__":
    unittest.main()
