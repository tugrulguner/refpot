from pathlib import Path
from tempfile import TemporaryDirectory

from refpot import Database, Row

with TemporaryDirectory(prefix="refpot-quickstart-") as directory:
    path = Path(directory) / "example.rp"  # Parent directory must already exist.
    with Database(path) as db:
        db.insert(1, 42, "answer")
        db.update(1, value=43)
        assert db.get(1) == Row(1, 43, "answer")
        with db.transaction():
            db.insert(2, 99)
        try:
            with db.transaction():
                db.update(1, value=100)
                raise RuntimeError("roll back this transaction")
        except RuntimeError:
            pass
        assert db.get(1) == Row(1, 43, "answer")
        db.delete(2)
        db.checkpoint()
    with Database(path) as db:
        assert db.get(1) == Row(1, 43, "answer")
        print(db.get(1))
