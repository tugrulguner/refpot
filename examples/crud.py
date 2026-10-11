"""Run a fresh database, then reopen actual caller-provided records."""

from pathlib import Path
from tempfile import TemporaryDirectory

from refpot import Database, Row

with TemporaryDirectory(prefix="refpot-crud-") as directory:
    path = Path(directory) / "example.rp"
    with Database(path) as db:
        db.insert(1, 42, "answer")
        db.update(1, value=43)
        assert db.get(1) == Row(1, 43, "answer")
        db.insert(2, 99)
        db.delete(2)
    with Database(path) as db:
        print(db.get(1))
        assert len(db) == 1
