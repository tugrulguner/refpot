"""Whole-model reopen through the public Python SQL interface."""

import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from refpot.sql import Database, SQLError


def test_reopen_retains_catalog_bags_assertions_and_continued_writes(tmp_path):
    path = tmp_path / "model.rpsql"
    with Database(path) as db:
        db.execute("CREATE TABLE resources (id INTEGER PRIMARY KEY)")
        db.execute("CREATE TABLE reservations (id INTEGER PRIMARY KEY, resource INTEGER NOT NULL)")
        db.execute(
            "CREATE MATERIALIZED VIEW booked AS SELECT resource, COUNT(*) AS n FROM reservations GROUP BY resource"
        )
        db.execute(
            "CREATE MATERIALIZED VIEW missing AS SELECT r.id, r.resource FROM reservations AS r WHERE NOT EXISTS (SELECT * FROM resources AS s WHERE s.id = r.resource)"
        )
        db.execute("CREATE ASSERTION resource_exists CHECK (NOT EXISTS (SELECT * FROM missing))")
        with db.transaction():
            db.execute("INSERT INTO reservations VALUES (1, 7)")
            db.execute("INSERT INTO reservations VALUES (2, 7)")
            db.execute("INSERT INTO resources VALUES (7)")
    with Database(path, mode="modular") as db:
        assert db.execute("SELECT * FROM reservations").rows == ((1, 7), (2, 7))
        assert db.execute("SELECT * FROM booked").rows == ((7, 2),)
        assert db.execute("SELECT * FROM missing").rows == ()
        try:
            with db.transaction():
                db.execute("DELETE FROM resources")
        except SQLError:
            pass
        else:
            raise AssertionError("recovered assertion was not enforced")
        db.execute("DELETE FROM reservations WHERE id = 1")
        db.checkpoint()
    with Database(path) as db:
        assert db.execute("SELECT * FROM reservations").rows == ((2, 7),)
        assert db.execute("SELECT * FROM booked").rows == ((7, 1),)
        assert db.execute("SELECT * FROM missing").rows == ()


@pytest.mark.parametrize("checkpoint", [False, True])
def test_multiple_named_assertions_on_same_relation_survive(tmp_path, checkpoint):
    path = tmp_path / "assertions.db"
    with Database(path) as db:
        db.execute("CREATE TABLE forbidden (id INTEGER PRIMARY KEY)")
        for name in ("first_guard", "second_guard"):
            db.execute(f"CREATE ASSERTION {name} CHECK (NOT EXISTS (SELECT * FROM forbidden))")
        if checkpoint:
            db.checkpoint()
    with Database(path) as db:
        for name in ("first_guard", "second_guard"):
            with pytest.raises(SQLError, match="assertion already exists"):
                db.execute(f"CREATE ASSERTION {name} CHECK (NOT EXISTS (SELECT * FROM forbidden))")
        with pytest.raises(SQLError, match="required-empty"):
            db.execute("INSERT INTO forbidden VALUES (1)")
        assert db.execute("SELECT * FROM forbidden").rows == ()


@pytest.mark.parametrize(
    "path,error",
    [(b"db", TypeError), ("", ValueError), ("db\0x", ValueError), ("\ud800", ValueError)],
)
def test_invalid_path_rejected_before_filesystem_access(path, error):
    with pytest.raises(error):
        Database(path)


@pytest.mark.parametrize("checkpoint,offset", [(False, 36), (False, 48), (True, 36), (True, 48)])
def test_corruption_rejected_without_repairing_complete_records(tmp_path, checkpoint, offset):
    path = tmp_path / "corrupt.db"
    with Database(path) as db:
        db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO t VALUES (1)")
        if checkpoint:
            db.checkpoint()
    damaged = path if checkpoint else path.with_name(path.name + ".wal")
    content = bytearray(damaged.read_bytes())
    assert len(content) > offset
    content[offset] ^= 1
    damaged.write_bytes(content)
    with pytest.raises(RuntimeError, match="corrupt"):
        Database(path)
    assert damaged.read_bytes() == content


def test_sql_rejects_fixed_schema_format_without_modification(tmp_path):
    from refpot import Database as FixedDatabase

    path = tmp_path / "fixed.db"
    with FixedDatabase(path) as fixed:
        fixed.insert(1, 12, "retained")
        fixed.checkpoint()
    snapshot = path.read_bytes()
    with pytest.raises(RuntimeError):
        Database(path)
    assert path.read_bytes() == snapshot
    with FixedDatabase(path) as fixed:
        assert fixed.get(1).value == 12


@pytest.mark.parametrize("managed", [False, True])
def test_checkpoint_rejection_preserves_active_transaction(tmp_path, managed):
    path = tmp_path / "transaction.db"
    with Database(path) as db:
        db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        if managed:
            with db.transaction():
                db.execute("INSERT INTO t VALUES (1)")
                with pytest.raises(SQLError, match="inside a transaction"):
                    db.checkpoint()
                assert db.execute("SELECT * FROM t").rows == ((1,),)
        else:
            db.execute("BEGIN")
            db.execute("INSERT INTO t VALUES (1)")
            with pytest.raises(SQLError, match="inside a transaction"):
                db.checkpoint()
            db.execute("COMMIT")
    with Database(path) as db:
        assert db.execute("SELECT * FROM t").rows == ((1,),)


def test_persistent_owner_lock_close_and_wrong_thread(tmp_path):
    path = tmp_path / "owned.db"
    db = Database(path)
    db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    with pytest.raises(RuntimeError):
        Database(path)
    with ThreadPoolExecutor(max_workers=1) as pool:
        for operation in (db.checkpoint, db.close, lambda: db.execute("SELECT * FROM t")):
            with pytest.raises(RuntimeError, match="creating process and thread"):
                pool.submit(operation).result(timeout=5)
    db.execute("INSERT INTO t VALUES (1)")
    db.close()
    db.close()
    with pytest.raises(RuntimeError, match="closed"):
        db.checkpoint()
    with Database(path) as reopened:
        assert reopened.execute("SELECT * FROM t").rows == ((1,),)


def test_fork_cannot_use_inherited_persistent_owner(tmp_path):
    path = tmp_path / "fork.db"
    with Database(path) as db:
        db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        pid = os.fork()
        if pid == 0:
            try:
                for operation in (db.checkpoint, db.close, lambda: db.execute("SELECT * FROM t")):
                    try:
                        operation()
                    except RuntimeError as exc:
                        assert "creating process and thread" in str(exc)
                    else:
                        os._exit(2)
            except BaseException:
                os._exit(3)
            os._exit(0)
        _, status = os.waitpid(pid, 0)
        assert os.waitstatus_to_exitcode(status) == 0
        db.execute("INSERT INTO t VALUES (1)")
    with Database(path) as reopened:
        assert reopened.execute("SELECT * FROM t").rows == ((1,),)
