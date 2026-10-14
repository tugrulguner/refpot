"""Create the logical fixture required by the archived recovery diagnostic.

This creates a new fixture, not an original historical artifact. Run with the
separately installed wheel under evaluation. Existing output is never replaced.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from refpot import Database, Row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    path = args.output.resolve()
    if any(Path(str(path) + suffix).exists() for suffix in ("", ".wal", ".lock")):
        raise FileExistsError(f"fixture or sidecar already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with Database(path) as db:
        with db.transaction():
            for i in range(10_000):
                db.insert(3 * i + 1 + int(i % 7 == 0), i % 17, f"row-{i}")
        db.checkpoint()
    with Database(path) as db:
        assert len(db) == 10_000
        for i in range(10_000):
            key = 3 * i + 1 + int(i % 7 == 0)
            assert db.get(key) == Row(key, i % 17, f"row-{i}")
    print(f"Verified new 10,000-row recovery fixture: {path}")


if __name__ == "__main__":
    main()
