from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_artifacts.py DIST_DIR")
    dist = Path(sys.argv[1])
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))
    assert len(sdists) == 1, f"expected one sdist, found {len(sdists)}"
    if wheels:
        required = ("refpot/__init__.py", "refpot/_core.pyi", "refpot/py.typed")
        for wheel in wheels:
            with zipfile.ZipFile(wheel) as archive:
                names = set(archive.namelist())
                for member in required:
                    assert member in names, f"{member} missing from {wheel}"
                metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
                metadata = archive.read(metadata_name).decode()
                assert "License-Expression: MIT" in metadata, (
                    f"wheel metadata lacks MIT license: {wheel}"
                )
                assert any(name.endswith(".dist-info/licenses/LICENSE") for name in names), (
                    "wheel has no MIT license payload"
                )
    with tarfile.open(sdists[0]) as archive:
        names = archive.getnames()
        for suffix in (
            "/native/core.cpp",
            "/CMakeLists.txt",
            "/LICENSE",
            "/tests/test_database.py",
            "/scripts/verify_artifacts.py",
        ):
            assert any(name.endswith(suffix) for name in names), f"{suffix} missing from sdist"
    print(f"verified {len(wheels)} wheel(s) and {sdists[0]}")


if __name__ == "__main__":
    main()
