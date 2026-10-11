"""A committed transaction survives reopen; an aborted one does not."""
from pathlib import Path
from tempfile import TemporaryDirectory

from refpot import Database, Row

with TemporaryDirectory(prefix="refpot-transactions-") as directory:
    path = Path(directory) / "transactions.rp"
    with Database(path) as db:
        with db.transaction():
            db.insert(1, 10)
            db.insert(2, 20)
            assert len(db) == 2  # read-your-writes
        try:
            with db.transaction():
                db.update(1, value=99)
                db.delete(2)
                raise RuntimeError("demonstrate rollback")
        except RuntimeError:
            pass
        assert db.get(1) == Row(1, 10, "")
        db.checkpoint()
    with Database(path) as db:
        assert len(db) == 2
        print(db.get(1))
