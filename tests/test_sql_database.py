"""Consumer tests for the packaged volatile SQL API (no source-path injection)."""

import importlib.util
import os
import unittest
from unittest import mock


class SQLPackageTests(unittest.TestCase):
    def test_public_volatile_sql_entry_point(self):
        self.assertIsNotNone(
            importlib.util.find_spec("refpot.sql"), "packaged SQL preview is missing"
        )
        from refpot.sql import Database

        with Database() as db:
            db.execute("CREATE TABLE stock (id INTEGER PRIMARY KEY, units INTEGER NOT NULL)")
            db.execute("INSERT INTO stock VALUES (?, ?)", (1, 10))
            with db.transaction():
                db.execute("UPDATE stock SET units = ? WHERE id = ?", (6, 1))
                result = db.execute(query="SELECT units FROM stock WHERE id = ?", parameters=(1,))
                self.assertEqual(result.rows, ((6,),))
        self.assertEqual(result.columns, ("units",))
        self.assertEqual(result.rows, ((6,),))

    def test_transaction_context_prevents_caught_error_autocommit(self):
        from refpot.sql import Database, SQLError

        for mode in ("overlay", "modular"):
            with Database(mode=mode) as db:
                db.execute("CREATE TABLE stock (id INTEGER PRIMARY KEY, units INTEGER NOT NULL)")
                db.execute("INSERT INTO stock VALUES (1, 10)")
                with db.transaction():
                    db.execute("UPDATE stock SET units = ? WHERE id = ?", (6, 1))
                    self.assertEqual(db.execute("SELECT units FROM stock").rows, ((6,),))
                self.assertEqual(db.execute("SELECT units FROM stock").rows, ((6,),))
                with self.assertRaises(SQLError), db.transaction():
                    db.execute("UPDATE stock SET units = 2 WHERE id = 1")
                    with self.assertRaises(SQLError):
                        db.execute("INSERT INTO stock VALUES (1, 99)")
                    with self.assertRaises(SQLError):
                        db.execute("UPDATE stock SET units = 3 WHERE id = 1")
                self.assertEqual(db.execute("SELECT units FROM stock").rows, ((6,),))
                with self.assertRaises(TypeError), db.transaction():
                    db.execute("UPDATE stock SET units = 4 WHERE id = 1")
                    db.execute("INSERT INTO stock VALUES (?, ?)", (2, True))
                self.assertEqual(db.execute("SELECT units FROM stock").rows, ((6,),))
                with db.transaction():
                    pass

    def test_grouped_join_matches_sqlite(self):
        import sqlite3

        from refpot.sql import Database

        for mode in ("overlay", "modular"):
            with Database(mode=mode) as db:
                control = sqlite3.connect(":memory:")
                self.addCleanup(control.close)
                for sql in (
                    "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer INTEGER NOT NULL, product INTEGER NOT NULL)",
                    "CREATE TABLE prices (id INTEGER PRIMARY KEY, amount INTEGER NOT NULL)",
                ):
                    db.execute(sql)
                    control.execute(sql)
                for table, rows in (
                    ("orders", ((1, 8, 1), (2, 8, 2), (3, 9, 1))),
                    ("prices", ((1, 7), (2, 11))),
                ):
                    for row in rows:
                        sql = f"INSERT INTO {table} VALUES ({','.join('?' for _ in row)})"
                        db.execute(sql, row)
                        control.execute(sql, row)
                query = "SELECT o.customer, COUNT(*) AS n, SUM(p.amount) AS total FROM orders AS o JOIN prices AS p ON o.product = p.id WHERE p.amount >= ? AND o.id > ? GROUP BY o.customer ORDER BY total DESC LIMIT ?"
                expected = tuple(control.execute(query, (7, 0, 5)).fetchall())
                result = db.execute(query, (7, 0, 5))
                self.assertEqual(result.rows, expected)
                self.assertEqual(result.columns, ("customer", "n", "total"))
                self.assertEqual(db.execute(query, (7, 0, 5), explain=True).rows, ())

    def test_second_table_preserves_first_table_rows(self):
        from refpot.sql import Database

        with Database() as db:
            db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)")
            db.execute("INSERT INTO items VALUES (?, ?)", (1, 7))
            db.execute("CREATE TABLE prices (id INTEGER PRIMARY KEY, amount INTEGER NOT NULL)")
            self.assertEqual(db.execute("SELECT * FROM items").rows, ((1, 7),))

    def test_seeded_queries_and_mutations_against_sqlite(self):
        import random
        import sqlite3

        from refpot.sql import Database

        comparisons = 0
        for mode in ("overlay", "modular"):
            for seed in range(3):
                rng = random.Random(seed)
                with Database(mode=mode) as db:
                    control = sqlite3.connect(":memory:")
                    self.addCleanup(control.close)
                    ddl = "CREATE TABLE data (id INTEGER PRIMARY KEY, dept INTEGER NOT NULL, value INTEGER NOT NULL)"
                    db.execute(ddl)
                    control.execute(ddl)
                    for key in range(30):
                        row = (key, rng.randrange(4), rng.randrange(-20, 21))
                        db.execute("INSERT INTO data VALUES (?, ?, ?)", row)
                        control.execute("INSERT INTO data VALUES (?, ?, ?)", row)
                    control.commit()
                    queries = [
                        ("SELECT * FROM data ORDER BY id", ()),
                        (
                            "SELECT dept, value FROM data WHERE value >= ? AND id < ? ORDER BY dept, value",
                            (-3, 20),
                        ),
                        (
                            "SELECT dept, COUNT(*) AS n, SUM(value) AS total FROM data GROUP BY dept ORDER BY dept",
                            (),
                        ),
                        ("SELECT COUNT(*), SUM(value) FROM data WHERE id < ?", (-1,)),
                        ("SELECT COUNT(*), SUM(value) FROM data", ()),
                        ("SELECT value FROM data ORDER BY value DESC LIMIT ?", (5,)),
                        (
                            "SELECT a.id, b.id FROM data AS a JOIN data AS b ON a.dept = b.dept WHERE a.value > ? ORDER BY a.id, b.id LIMIT ?",
                            (10, 30),
                        ),
                    ]
                    for _ in range(40):
                        value, key = rng.randrange(-100, 101), rng.randrange(35)
                        sql = "UPDATE data SET value = ? WHERE id = ?"
                        with db.transaction(), control:
                            got = db.execute(sql, (value, key))
                            expected = control.execute(sql, (value, key))
                            self.assertEqual(got.affected, expected.rowcount)
                            self.assertEqual(
                                db.execute("SELECT * FROM data ORDER BY id").rows,
                                tuple(control.execute("SELECT * FROM data ORDER BY id")),
                            )
                        for query, params in queries:
                            self.assertEqual(
                                db.execute(query, params).rows,
                                tuple(control.execute(query, params)),
                                (mode, seed, query),
                            )
                            comparisons += 1
                    deleted = db.execute("DELETE FROM data WHERE value < ?", (0,)).affected
                    self.assertEqual(
                        deleted, control.execute("DELETE FROM data WHERE value < ?", (0,)).rowcount
                    )
                    self.assertEqual(
                        db.execute("SELECT * FROM data ORDER BY id").rows,
                        tuple(control.execute("SELECT * FROM data ORDER BY id")),
                    )
        print("Independent SQLite query comparisons:", comparisons)

    def test_rejection_binding_and_explain_preserve_state(self):
        from refpot.sql import Database, SQLError

        with Database() as db:
            db.execute("CREATE TABLE empty (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)")
            for query, params in (
                ("SELECT absent FROM empty", ()),
                ("SELECT id FROM empty WHERE absent = ?", (2,)),
                ("SELECT id FROM empty ORDER BY absent", ()),
                ("SELECT id FROM empty WHERE id = ?", ()),
                ("SELECT id FROM empty", (1,)),
                ("SELECT id FROM empty AS a JOIN empty AS b ON a.id = b.id", ()),
                ("SELECT id, SUM(value) FROM empty", ()),
                ("SELECT * FROM empty; DELETE FROM empty", ()),
                ("CREATE TABLE bad (id INTEGER PRIMARY KEY, value INTEGER)", ()),
                ("CREATE TABLE bad (id INTEGER PRIMARY KEY, id INTEGER NOT NULL)", ()),
                ("UPDATE empty SET id = 2", ()),
                ("SELECT * FROM empty LIMIT -1", ()),
            ):
                with self.subTest(query=query), self.assertRaises(SQLError):
                    db.execute(query, params)
            self.assertEqual(
                db.execute("SELECT COUNT(*), SUM(value) FROM empty").rows, ((0, None),)
            )
            db.execute("INSERT INTO empty VALUES (1, 7)", explain=True)
            self.assertEqual(db.execute("SELECT * FROM empty").rows, ())
            with db.transaction():
                db.execute("INSERT INTO empty VALUES (1, 7)")
                db.execute("COMMIT", explain=True)
                with self.assertRaises(SQLError):
                    db.execute("SELECT absent FROM empty", explain=True)
                self.assertEqual(db.execute("SELECT value FROM empty").rows, ((7,),))
            with self.assertRaises(SQLError), db.transaction():
                db.execute("UPDATE empty SET value = 9")
                db.execute("COMMIT")
            self.assertEqual(db.execute("SELECT value FROM empty").rows, ((7,),))
            for value in (True, 1.5, "1", None, 1 << 63):
                with self.assertRaises((TypeError, OverflowError)):
                    db.execute("INSERT INTO empty VALUES (?, ?)", (2, value))  # pyright: ignore[reportArgumentType]
            for query in ("", "SELECT\0* FROM empty", "x" * 65537):
                with self.assertRaises(ValueError):
                    db.execute(query)

    def test_overflow_ownership_and_detached_results(self):
        import threading

        from refpot.sql import Database, SQLError

        with Database() as db:
            db.execute("CREATE TABLE numbers (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)")
            db.execute("INSERT INTO numbers VALUES (?, ?)", (1, (1 << 63) - 1))
            db.execute("INSERT INTO numbers VALUES (2, 1)")
            with self.assertRaises(SQLError):
                db.execute("SELECT SUM(value) FROM numbers")
            db.execute("INSERT INTO numbers VALUES (?, ?)", (3, -1))
            saved = db.execute("SELECT SUM(value) FROM numbers")
            self.assertEqual(saved.rows, (((1 << 63) - 1,),))
            errors = []

            def wrong_thread():
                try:
                    db.execute("SELECT * FROM numbers")
                except RuntimeError as error:
                    errors.append(str(error))

            thread = threading.Thread(target=wrong_thread)
            thread.start()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(len(errors), 1)
            self.assertTrue(errors[0])
            if hasattr(os, "fork"):
                child = os.fork()
                if child == 0:
                    try:
                        db.execute("SELECT * FROM numbers")
                    except RuntimeError:
                        os._exit(0)
                    os._exit(2)
                _, status = os.waitpid(child, 0)
                self.assertEqual(os.waitstatus_to_exitcode(status), 0)
        self.assertEqual(saved.rows, (((1 << 63) - 1,),))
        with self.assertRaises(RuntimeError):
            db.execute("SELECT * FROM numbers")
        db.close()

    def test_explicit_transaction_failure_aborts_all_prior_writes(self):
        from refpot.sql import Database, SQLError

        for mode in ("overlay", "modular"):
            with Database(mode=mode) as db:
                db.execute("CREATE TABLE stock (id INTEGER PRIMARY KEY, units INTEGER NOT NULL)")
                db.execute("INSERT INTO stock VALUES (1, 10)")
                failures = (
                    ("SELECT missing FROM stock", ()),
                    ("INSERT INTO stock VALUES (1, 2)", ()),
                    ("INSERT INTO stock VALUES (?, ?)", (2,)),
                    ("UPDATE stock SET id = 9", ()),
                    ("DROP TABLE stock", ()),
                )
                for query, parameters in failures:
                    with self.subTest(mode=mode, query=query):
                        db.execute("BEGIN")
                        db.execute("UPDATE stock SET units = 20")
                        with self.assertRaises(SQLError):
                            db.execute(query, parameters)
                        self.assertEqual(db.execute("SELECT * FROM stock").rows, ((1, 10),))
                        with self.assertRaises(SQLError):
                            db.execute("COMMIT")
                db.execute("BEGIN")
                db.execute("UPDATE stock SET units = 30")
                with self.assertRaises(SQLError):
                    db.execute("SELECT absent FROM stock", explain=True)
                self.assertEqual(db.execute("SELECT units FROM stock").rows, ((30,),))
                db.execute("COMMIT")
                self.assertEqual(db.execute("SELECT units FROM stock").rows, ((30,),))

    def test_cancelled_keys_empty_tables_and_detached_immutable_result(self):
        from dataclasses import FrozenInstanceError

        from refpot.sql import Database

        for mode in ("overlay", "modular"):
            with Database(mode=mode) as db:
                db.execute("CREATE TABLE data (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)")
                with db.transaction():
                    for value in range(20):
                        db.execute("INSERT INTO data VALUES (1, ?)", (value,))
                        self.assertEqual(db.execute("DELETE FROM data WHERE id = 1").affected, 1)
                    self.assertEqual(db.execute("SELECT * FROM data").rows, ())
                    db.execute("INSERT INTO data VALUES (1, 7)")
                saved = db.execute("SELECT * FROM data")
                db.execute("DELETE FROM data")
                self.assertEqual(saved.rows, ((1, 7),))
                with self.assertRaises((FrozenInstanceError, AttributeError)):
                    saved.rows = ()  # type: ignore[misc]  # runtime frozen-result regression
                self.assertEqual(
                    db.execute("SELECT COUNT(*), SUM(value) FROM data").rows, ((0, None),)
                )
            self.assertEqual(saved.rows, ((1, 7),))

    def test_invalid_truthy_explain_aborts_explicit_transaction(self):
        from refpot.sql import Database

        with Database() as db:
            db.execute("CREATE TABLE data (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)")
            db.execute("INSERT INTO data VALUES (1, 10)")
            db.execute("BEGIN")
            db.execute("UPDATE data SET value = 20")
            with self.assertRaises(TypeError):
                db.execute("SELECT * FROM data", explain="yes")  # pyright: ignore[reportArgumentType]
            self.assertEqual(db.execute("SELECT value FROM data").rows, ((10,),))

    def test_parameter_iteration_cannot_commit_an_active_transaction(self):
        from refpot.sql import Database

        with Database() as db:
            db.execute("CREATE TABLE data (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)")
            db.execute("INSERT INTO data VALUES (1, 10)")
            db.execute("BEGIN")
            db.execute("UPDATE data SET value = 20")

            def reentrant_parameters():
                db.execute("COMMIT")
                yield 1

            with self.assertRaises((RuntimeError, TypeError)):
                db.execute("SELECT absent FROM data WHERE id = ?", reentrant_parameters())  # pyright: ignore[reportArgumentType]
            self.assertEqual(db.execute("SELECT value FROM data").rows, ((10,),))

    def test_native_binding_rejects_implicit_boolean_coercion(self):
        from refpot import _sql

        db = _sql._Database("overlay")
        try:
            db.execute(
                "CREATE TABLE data (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)", [], False
            )
            for parameters in ([1, True], [True, 1]):
                with self.assertRaises(TypeError):
                    db.execute("INSERT INTO data VALUES (?, ?)", parameters, False)
            with self.assertRaises(TypeError):
                db.execute("SELECT * FROM data", [], 1)  # pyright: ignore[reportArgumentType]
            self.assertEqual(db.execute("SELECT * FROM data", [], False).rows, [])
        finally:
            db.close()

    def test_python_result_allocation_failure_closes_owner(self):
        from refpot import sql as native_sql

        with native_sql.Database() as db:
            db.execute("CREATE TABLE stock (id INTEGER PRIMARY KEY, units INTEGER NOT NULL)")

            def fail_result(*args):
                raise MemoryError("injected detached-result allocation failure")

            with (
                mock.patch.object(native_sql, "Result", fail_result),
                self.assertRaises(MemoryError),
            ):
                db.execute("INSERT INTO stock VALUES (1, 10)")
            with self.assertRaisesRegex(RuntimeError, "closed"):
                db.execute("SELECT * FROM stock")


if __name__ == "__main__":
    unittest.main()
