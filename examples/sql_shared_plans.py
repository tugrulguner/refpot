"""Runnable shared maintained-view lifecycle example for the SQL preview.

Run with: python examples/sql_shared_plans.py
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from refpot.sql import Database, SQLError


def main() -> None:
    with TemporaryDirectory(prefix="refpot-shared-plans-") as directory:
        path = Path(directory) / "catalog.db"
        with Database(path) as db:
            db.execute(
                "CREATE TABLE events (id INTEGER PRIMARY KEY, bucket INTEGER NOT NULL, amount INTEGER NOT NULL, active INTEGER NOT NULL)"
            )
            db.execute("INSERT INTO events VALUES (1, 1, 3, 1)")
            db.execute("INSERT INTO events VALUES (2, 1, 5, 1)")
            db.execute("INSERT INTO events VALUES (3, 2, 7, 1)")
            db.execute("INSERT INTO events VALUES (4, 2, 11, 0)")
            db.execute(
                "CREATE MATERIALIZED VIEW active_a AS SELECT bucket, amount FROM events WHERE active = 1"
            )
            db.execute(
                "CREATE MATERIALIZED VIEW active_b AS SELECT bucket, amount FROM events WHERE active = 1"
            )
            db.execute(
                "CREATE MATERIALIZED VIEW totals AS SELECT bucket, SUM(amount) AS total FROM active_a GROUP BY bucket"
            )
            db.execute(
                "CREATE MATERIALIZED VIEW counts AS SELECT bucket, COUNT(*) AS n FROM active_b GROUP BY bucket"
            )
            db.execute(
                "CREATE MATERIALIZED VIEW excess AS SELECT bucket FROM totals WHERE total > 15"
            )
            db.execute("CREATE ASSERTION no_excess CHECK (NOT EXISTS (SELECT * FROM excess))")
            assert db.execute("SELECT bucket, total FROM totals ORDER BY bucket").rows == (
                (1, 8),
                (2, 7),
            )
            assert db.execute("SELECT bucket, n FROM counts ORDER BY bucket").rows == (
                (1, 2),
                (2, 1),
            )

            # Adding another definition over populated data computes its own state.
            db.execute(
                "CREATE MATERIALIZED VIEW large AS SELECT bucket, amount FROM events WHERE amount >= 5"
            )
            assert db.execute("SELECT bucket, amount FROM large ORDER BY bucket, amount").rows == (
                (1, 5),
                (2, 7),
                (2, 11),
            )

            # Rejected replacement leaves the original definition and peer intact.
            migration = "ALTER MATERIALIZED VIEW active_a AS SELECT bucket, amount FROM events WHERE active >= 0"
            try:
                db.execute(migration)
            except SQLError:
                pass
            else:
                raise AssertionError("assertion-violating replacement unexpectedly succeeded")
            assert db.execute(
                "SELECT bucket, amount FROM active_a ORDER BY bucket, amount"
            ).rows == ((1, 3), (1, 5), (2, 7))
            assert db.execute(
                "SELECT bucket, amount FROM active_b ORDER BY bucket, amount"
            ).rows == ((1, 3), (1, 5), (2, 7))

            # Repair the dependent assertion, then migrate only active_a.
            db.execute("UPDATE events SET amount = 5 WHERE id = 4")
            db.execute(migration)
            assert db.execute(
                "SELECT bucket, amount FROM active_a ORDER BY bucket, amount"
            ).rows == ((1, 3), (1, 5), (2, 5), (2, 7))
            assert db.execute(
                "SELECT bucket, amount FROM active_b ORDER BY bucket, amount"
            ).rows == ((1, 3), (1, 5), (2, 7))
            assert db.execute("SELECT bucket, total FROM totals ORDER BY bucket").rows == (
                (1, 8),
                (2, 12),
            )
            # No checkpoint: close and reopen exercises the acknowledged WAL catalog.

        with Database(path, mode="modular") as db:
            assert db.execute("SELECT bucket, total FROM totals ORDER BY bucket").rows == (
                (1, 8),
                (2, 12),
            )
            assert db.execute("SELECT bucket, n FROM counts ORDER BY bucket").rows == (
                (1, 2),
                (2, 1),
            )
            db.checkpoint()

        with Database(path) as db:
            assert db.execute("SELECT bucket, total FROM totals ORDER BY bucket").rows == (
                (1, 8),
                (2, 12),
            )
            db.execute("INSERT INTO events VALUES (5, 1, 2, 1)")
            assert db.execute("SELECT bucket, total FROM totals ORDER BY bucket").rows == (
                (1, 10),
                (2, 12),
            )

        # Running this entry point again is safe: all files live in a fresh temp dir.
        print(
            "Shared views, dependent aggregates, WAL recovery, checkpoint, and continued writes verified."
        )


if __name__ == "__main__":
    main()
