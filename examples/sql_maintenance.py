"""Reservations with maintained usage and a final-state capacity assertion.

Run with: python examples/sql_maintenance.py
All SQL goes through the public Database.execute/transaction API.
"""

from refpot.sql import Database, SQLError


def main() -> None:
    with Database() as db:
        db.execute("CREATE TABLE capacity (resource INTEGER PRIMARY KEY, units INTEGER NOT NULL)")
        db.execute(
            "CREATE TABLE reservations (id INTEGER PRIMARY KEY, resource INTEGER NOT NULL, units INTEGER NOT NULL)"
        )
        db.execute("INSERT INTO capacity VALUES (1, 10)")
        db.execute("INSERT INTO capacity VALUES (2, 8)")
        db.execute(
            "CREATE MATERIALIZED VIEW usage AS SELECT resource, SUM(units) AS units, COUNT(*) AS bookings FROM reservations GROUP BY resource"
        )
        db.execute(
            "CREATE MATERIALIZED VIEW violations AS SELECT u.resource, u.units FROM usage AS u JOIN capacity AS c ON u.resource = c.resource WHERE u.units > c.units"
        )
        db.execute("CREATE ASSERTION capacity_ok CHECK (NOT EXISTS (SELECT * FROM violations))")

        with db.transaction():
            db.execute("INSERT INTO reservations VALUES (1, 1, 6)")
            db.execute("INSERT INTO reservations VALUES (2, 1, 3)")
            db.execute("INSERT INTO reservations VALUES (3, 2, 5)")
        print("Committed usage:", db.execute("SELECT resource, units, bookings FROM usage").rows)

        # Temporary violations are permitted inside a transaction if repaired by
        # its final state; maintained relations provide read-your-writes.
        with db.transaction():
            db.execute("INSERT INTO reservations VALUES (4, 1, 4)")
            print("Temporary violations:", db.execute("SELECT * FROM violations").rows)
            db.execute("DELETE FROM reservations WHERE id = 4")
            print("Repaired violations:", db.execute("SELECT * FROM violations").rows)

        # An invalid final state is rejected atomically at commit.
        try:
            with db.transaction():
                db.execute("INSERT INTO reservations VALUES (5, 2, 5)")
        except SQLError as error:
            print("Rejected over-capacity commit:", type(error).__name__)
        else:
            raise AssertionError("over-capacity commit unexpectedly succeeded")
        assert db.execute("SELECT resource, units, bookings FROM usage ORDER BY resource").rows == (
            (1, 9, 2),
            (2, 5, 1),
        )
        assert not db.execute("SELECT * FROM violations").rows
        print("Final usage:", db.execute("SELECT resource, units, bookings FROM usage").rows)
        print("Final violations:", db.execute("SELECT * FROM violations").rows)


if __name__ == "__main__":
    main()
