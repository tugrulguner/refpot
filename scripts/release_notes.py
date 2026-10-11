from __future__ import annotations

import os
import re
from pathlib import Path


def main() -> None:
    version = os.environ.get("RELEASE_TAG", "").removeprefix("v")
    text = Path("CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(
        rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", text, re.MULTILINE | re.DOTALL
    )
    if match is None:
        raise SystemExit(f"no exact changelog section for {version}")
    print(match.group(1).strip())


if __name__ == "__main__":
    main()
