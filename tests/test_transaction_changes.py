from __future__ import annotations

import pytest

from refpot import Database


def test_transaction_changes_preserve_reads_errors_and_repeated_key_semantics(tmp_path):
    path = tmp_path / "changes.db"
    db = Database(path)
    db.insert(1, 10, "before")
    with db.transaction():
        db.update(1, value=11)
        db.insert(2, 20, "new")
        db.delete(2)
        db.insert(2, 21, "reinserted")
        assert len(db) == 2
        assert db.get(1).value == 11
        assert db.get(2).text == "reinserted"
        with pytest.raises(ValueError):
            db.insert(1, 99)
        assert db.get(1).value == 11
    db.close()

    reopened = Database(path)
    assert reopened.get(1).value == 11
    assert reopened.get(2).text == "reinserted"
    reopened.close()


def test_rollback_discards_change_set_and_failed_mutation_is_atomic(tmp_path):
    db = Database(tmp_path / "rollback.db")
    db.insert(1, 1, "original")
    with pytest.raises(RuntimeError):
        with db.transaction():
            db.update(1, value=2, text="changed")
            with pytest.raises(ValueError):
                db.update(1, text="x" * 32)
            assert db.get(1).value == 2
            raise RuntimeError("rollback")
    assert db.get(1).value == 1
    assert db.get(1).text == "original"
    db.close()
