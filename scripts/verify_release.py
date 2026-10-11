from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path


def main() -> None:
    tag = os.environ.get("RELEASE_TAG", "")
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?", tag):
        raise SystemExit(f"invalid release tag {tag!r}; expected v<semver>")
    version = tag[1:]
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    if metadata["project"]["version"] != version:
        raise SystemExit(
            f"tag {tag} does not match project version {metadata['project']['version']}"
        )
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    if re.search(rf"^## \[{re.escape(version)}\](?:\s|$)", changelog, re.MULTILINE) is None:
        raise SystemExit(f"CHANGELOG.md has no exact heading for {version}")
    print(f"{tag} matches pyproject.toml and CHANGELOG.md")


if __name__ == "__main__":
    main()
