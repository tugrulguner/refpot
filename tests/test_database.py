from __future__ import annotations

import subprocess
import sys

import pytest

from refpot import Database, Row


def test_crud_reopen_and_process_exit(tmp_path):
    path = tmp_path / "db.rp"
    with Database(path) as db:
        db.insert(7, -9, "héllo")
        assert db.get(7) == Row(7, -9, "héllo")
        db.update(7, value=12)
        assert db.get(7) == Row(7, 12, "héllo")
        db.delete(7)
        assert len(db) == 0
        db.insert(8, 2)
    subprocess.run([sys.executable, "-c", "from refpot import Database; import sys; d=Database(sys.argv[1]); assert d.get(8).value==2; d.close()", str(path)], check=True)
    with Database(path) as db:
        assert db.get(8).value == 2


def test_transactions_commit_rollback_and_read_your_writes(tmp_path):
    with Database(tmp_path / "db") as db:
        with db.transaction():
            db.insert(1, 10)
            assert db.get(1).value == 10
        with pytest.raises(RuntimeError):
            with db.transaction():
                db.update(1, value=20)
                raise RuntimeError("rollback")
        assert db.get(1).value == 10
        with db.transaction():
            db.insert(2, 2)
            with pytest.raises(ValueError):
                db.insert(2, 3)
        assert db.get(2).value == 2
        with db.transaction():
            with pytest.raises(RuntimeError):
                with db.transaction():
                    pass


def test_errors_and_validation_are_non_mutating(tmp_path):
    with Database(tmp_path / "db") as db:
        with pytest.raises(KeyError):
            db.get(1)
        with pytest.raises(KeyError):
            db.delete(1)
        for args in [(True, 1, ""), (1, 2**63, ""), (1, 1, "é" * 16), (1, 1, b"bad")]:
            with pytest.raises((TypeError, ValueError, OverflowError)):
                db.insert(*args)
        db.insert(1, 1)
        with pytest.raises(ValueError):
            db.insert(1, 2)
        assert len(db) == 1


def test_lock_exclusion(tmp_path):
    path = tmp_path / "db"
    first = Database(path)
    try:
        with pytest.raises(RuntimeError):
            Database(path)
    finally:
        first.close()
