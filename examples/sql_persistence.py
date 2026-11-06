"""Unreleased SQL persistence preview: commit, reopen and keep enforcing constraints.

Run against a source-built candidate that includes the SQL persistence extension.
The published fixed-schema refpot.Database format is separate and unchanged.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from refpot.sql import Database, SQLError


def main() -> None:
    with TemporaryDirectory(prefix="refpot-sql-model-") as directory:
        path = Path(directory) / "reservations.rpsql"
        with Database(path) as db:
            db.execute(
                "CREATE TABLE capacity (resource INTEGER PRIMARY KEY, units INTEGER NOT NULL)"
            )
            db.execute(
                "CREATE TABLE reservations (id INTEGER PRIMARY KEY, resource INTEGER NOT NULL, units INTEGER NOT NULL)"
            )
            db.execute(
                "CREATE MATERIALIZED VIEW usage AS SELECT resource, SUM(units) AS units, COUNT(*) AS bookings FROM reservations GROUP BY resource"
            )
            db.execute(
                "CREATE MATERIALIZED VIEW over_capacity AS SELECT u.resource FROM usage AS u JOIN capacity AS c ON u.resource = c.resource WHERE u.units > c.units"
            )
            db.execute(
                "CREATE MATERIALIZED VIEW missing AS SELECT r.id, r.resource FROM reservations AS r WHERE NOT EXISTS (SELECT * FROM capacity AS c WHERE c.resource = r.resource)"
            )
            db.execute(
                "CREATE ASSERTION capacity_ok CHECK (NOT EXISTS (SELECT * FROM over_capacity))"
            )
            db.execute(
                "CREATE ASSERTION resource_exists CHECK (NOT EXISTS (SELECT * FROM missing))"
            )
            with db.transaction():
                db.execute("INSERT INTO reservations VALUES (1, 7, 4)")
                db.execute("INSERT INTO reservations VALUES (2, 7, 3)")
                db.execute("INSERT INTO capacity VALUES (7, 10)")

        # No schema redeclaration, application callback or model/provider on reopen.
        with Database(path) as db:
            assert db.execute("SELECT * FROM usage").rows == ((7, 7, 2),)
            print("Recovered usage:", db.execute("SELECT * FROM usage").rows)
            for statement in (
                "INSERT INTO reservations VALUES (3, 7, 4)",
                "INSERT INTO reservations VALUES (3, 99, 1)",
            ):
                try:
                    with db.transaction():
                        db.execute(statement)
                except SQLError:
                    print("Recovered constraint rejected transaction")
                else:
                    raise AssertionError("invalid reservation was accepted")
            assert db.execute("SELECT * FROM reservations").rows == ((1, 7, 4), (2, 7, 3))
            with db.transaction():
                db.execute("DELETE FROM capacity WHERE resource = 7")
                assert db.execute("SELECT * FROM missing").rows == ((1, 7), (2, 7))
                db.execute("INSERT INTO capacity VALUES (7, 12)")
                db.execute("UPDATE reservations SET units = 5 WHERE id = 1")
            db.checkpoint()

        with Database(path, mode="modular") as db:
            assert db.execute("SELECT * FROM usage").rows == ((7, 8, 2),)
            assert not db.execute("SELECT * FROM missing").rows
            assert not db.execute("SELECT * FROM over_capacity").rows
            print("After checkpoint and second reopen:", db.execute("SELECT * FROM usage").rows)
        print("Temporary example files removed on exit; this is not a power-loss qualification.")


if __name__ == "__main__":
    main()
