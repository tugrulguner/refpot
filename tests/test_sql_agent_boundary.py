import os
import resource
import signal
import threading

import pytest

from refpot._sql import _Database


def test_native_agent_boundary_api_and_guards():
    db = _Database()
    db.execute("CREATE TABLE allowed (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)", ())
    db.execute("CREATE TABLE secret (id INTEGER PRIMARY KEY)", ())
    db.execute("INSERT INTO allowed VALUES (1, 7)", ())
    ctx = db.query_context(relations=["allowed"])
    assert ctx == {
        "revision": 2,
        "relations": [{"name": "allowed", "columns": ["id", "value"], "derived": False}],
    }
    assert db.execute_readonly("SELECT * FROM allowed", (), ["allowed"], ctx["revision"]).rows == [
        [1, 7]
    ]
    for bad in [
        "SELECT * FROM secret",
        "INSERT INTO allowed VALUES (2, 4)",
        "SELECT * FROM allowed; SELECT * FROM allowed",
    ]:
        with pytest.raises((RuntimeError, ValueError)):
            db.execute_readonly(bad, (), ["allowed"], ctx["revision"])
    for args in [(["allowed", "allowed"],), ("allowed",), ([1],)]:
        with pytest.raises((TypeError, RuntimeError, ValueError)):
            db.query_context(relations=args[0])
    with pytest.raises(TypeError):
        db.execute_readonly("SELECT * FROM allowed", [True], ["allowed"], ctx["revision"])


def test_native_agent_allowlist_join_and_not_exists():
    db = _Database()
    db.execute("CREATE TABLE allowed (id INTEGER PRIMARY KEY)", ())
    db.execute("CREATE TABLE secret (id INTEGER PRIMARY KEY)", ())
    ctx = db.query_context(["allowed"])
    for query in (
        "SELECT * FROM allowed JOIN secret ON allowed.id = secret.id",
        "SELECT * FROM allowed WHERE NOT EXISTS (SELECT * FROM secret WHERE secret.id = allowed.id)",
    ):
        with pytest.raises((RuntimeError, ValueError)):
            db.execute_readonly(query, (), ["allowed"], ctx["revision"])


def test_native_agent_revision_and_failed_ddl():
    db = _Database()
    db.execute("CREATE TABLE allowed (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)", ())
    db.execute("CREATE MATERIALIZED VIEW v AS SELECT id FROM allowed", ())
    ctx = db.query_context(["v"])
    with pytest.raises((RuntimeError, ValueError)):
        db.execute("CREATE TABLE broken (id INTEGER PRIMARY KEY,)", ())
    assert db.query_context(["v"])["revision"] == ctx["revision"]
    db.execute("ALTER MATERIALIZED VIEW v AS SELECT id FROM allowed WHERE value = 7", ())
    with pytest.raises((RuntimeError, ValueError)):
        db.execute_readonly("SELECT * FROM v", (), ["v"], ctx["revision"])


def test_native_agent_invalid_query_rolls_back_but_readonly_refusal_preserves_tx():
    db = _Database()
    db.execute("CREATE TABLE allowed (id INTEGER PRIMARY KEY)", ())
    ctx = db.query_context(["allowed"])
    db.execute("BEGIN", ())
    with pytest.raises((RuntimeError, ValueError)):
        db.execute_readonly("SELECT * FROM allowed @", (), ["allowed"], ctx["revision"])
    assert db.in_transaction()
    with pytest.raises((RuntimeError, ValueError)):
        db.execute("SELECT * FROM allowed @", ())
    assert not db.in_transaction()


def test_native_agent_exact_types_and_name_bounds():
    db = _Database()
    db.execute("CREATE TABLE allowed (id INTEGER PRIMARY KEY)", ())
    ctx = db.query_context(["allowed"])

    class StringSubclass(str):
        pass

    # Ordinary SQL retains its pre-agent accepted string-subclass contract.
    assert db.execute(StringSubclass("SELECT * FROM allowed"), ()).rows == []
    with pytest.raises(TypeError):
        db.execute_readonly(
            StringSubclass("SELECT * FROM allowed"), (), ["allowed"], ctx["revision"]
        )
    with pytest.raises(TypeError):
        db.execute("SELECT * FROM allowed", [True])
    with pytest.raises(TypeError):
        db.execute("SELECT * FROM allowed", (), explain=1)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        db.execute_readonly(
            "SELECT * FROM allowed", (), [StringSubclass("allowed")], ctx["revision"]
        )
    with pytest.raises((ValueError, RuntimeError)):
        db.query_context(["a" * 65])
    with pytest.raises((ValueError, RuntimeError)):
        db.query_context(["é" * 33])


def test_native_agent_closed_and_wrong_thread_guards():
    db = _Database()
    errors = []
    worker = threading.Thread(target=lambda: _capture_error(errors, db.stats))
    worker.start()
    worker.join()
    assert errors and isinstance(errors[0], RuntimeError)
    db.close()
    with pytest.raises(RuntimeError):
        db.query_context([])


def test_native_agent_poisoned_store_rejects_operations(tmp_path):
    database_path = tmp_path / "poisoned.db"
    db = _Database(path=str(database_path))
    db.execute("CREATE TABLE allowed (id INTEGER PRIMARY KEY)", ())
    wal_size = os.stat(str(database_path) + ".wal").st_size
    old_limit = resource.getrlimit(resource.RLIMIT_FSIZE)
    old_handler = signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE, (wal_size, old_limit[1]))
        with pytest.raises(RuntimeError):
            db.execute("INSERT INTO allowed VALUES (1)", ())
    finally:
        resource.setrlimit(resource.RLIMIT_FSIZE, old_limit)
        signal.signal(signal.SIGXFSZ, old_handler)
    with pytest.raises(RuntimeError, match="uncertain SQL storage outcome"):
        db.query_context(["allowed"])


def _capture_error(errors, operation):
    try:
        operation()
    except Exception as error:
        errors.append(error)
