"""Unreleased SQL preview: replace a maintained definition, then reopen it."""

from pathlib import Path
from tempfile import TemporaryDirectory

from refpot.sql import Database, SQLError


def main() -> None:
    with TemporaryDirectory(prefix="refpot-evolution-") as directory:
        path = Path(directory).resolve() / "reservations.db"
        with Database(path) as db:
            db.execute(
                "CREATE TABLE capacity (resource INTEGER PRIMARY KEY, units INTEGER NOT NULL)"
            )
            db.execute(
                "CREATE TABLE reservations (id INTEGER PRIMARY KEY, resource INTEGER NOT NULL, units INTEGER NOT NULL, status INTEGER NOT NULL)"
            )
            db.execute("INSERT INTO capacity VALUES (1, 5)")
            db.execute("INSERT INTO reservations VALUES (1, 1, 3, 1)")
            db.execute("INSERT INTO reservations VALUES (2, 1, 4, 2)")
            db.execute(
                "CREATE MATERIALIZED VIEW counted AS SELECT resource, units FROM reservations WHERE status = 1"
            )
            db.execute(
                "CREATE MATERIALIZED VIEW used AS SELECT resource, SUM(units) AS total FROM counted GROUP BY resource"
            )
            db.execute(
                "CREATE MATERIALIZED VIEW over_capacity AS SELECT u.resource FROM used AS u JOIN capacity AS c ON u.resource = c.resource WHERE u.total > c.units"
            )
            db.execute(
                "CREATE ASSERTION capacity_ok CHECK (NOT EXISTS (SELECT * FROM over_capacity))"
            )

            # Include provisional reservations too. This migration cannot be accepted
            # until the existing capacity assertion holds under the new definition.
            migration = "ALTER MATERIALIZED VIEW counted AS SELECT resource, units FROM reservations WHERE status >= 1"
            try:
                db.execute(migration)
            except SQLError:
                pass
            else:
                raise AssertionError("an over-capacity replacement was accepted")
            assert db.execute("SELECT * FROM used").rows == ((1, 3),)

            db.execute("UPDATE capacity SET units = 8 WHERE resource = 1")
            db.execute(migration)
            assert db.execute("SELECT * FROM used").rows == ((1, 7),)

        # No checkpoint was needed for the acknowledged migration to survive.
        with Database(path, mode="modular") as db:
            assert db.execute("SELECT * FROM used").rows == ((1, 7),)
            try:
                db.execute("INSERT INTO reservations VALUES (3, 1, 2, 2)")
            except SQLError:
                pass
            else:
                raise AssertionError("the recovered assertion stopped enforcing capacity")
            db.execute("INSERT INTO reservations VALUES (3, 1, 1, 2)")
            assert db.execute("SELECT * FROM used").rows == ((1, 8),)
            db.checkpoint()

        with Database(path) as db:
            assert db.execute("SELECT * FROM used").rows == ((1, 8),)
            assert db.execute("SELECT * FROM over_capacity").rows == ()
            print("Replacement survived WAL/checkpoint recovery; capacity remains enforced.")


if __name__ == "__main__":
    main()
