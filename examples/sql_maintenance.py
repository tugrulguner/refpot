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
        # An inner join alone hides reservations whose capacity row is absent.
        db.execute(
            "CREATE MATERIALIZED VIEW missing AS SELECT r.id, r.resource "
            "FROM reservations AS r WHERE NOT EXISTS "
            "(SELECT * FROM capacity AS c WHERE c.resource = r.resource)"
        )
        db.execute("CREATE ASSERTION resource_exists CHECK (NOT EXISTS (SELECT * FROM missing))")

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
        # Missing resources are also final-state violations, not hidden join rows.
        try:
            with db.transaction():
                db.execute("INSERT INTO reservations VALUES (6, 99, 1)")
                assert db.execute("SELECT * FROM missing").rows == ((6, 99),)
        except SQLError:
            print("Rejected missing-resource commit")
        else:
            raise AssertionError("missing-resource commit unexpectedly succeeded")
        with db.transaction():
            db.execute("DELETE FROM capacity WHERE resource = 1")
            assert db.execute("SELECT * FROM missing ORDER BY id").rows == ((1, 1), (2, 1))
            db.execute("INSERT INTO capacity VALUES (1, 10)")
            assert not db.execute("SELECT * FROM missing").rows

        assert db.execute("SELECT resource, units, bookings FROM usage ORDER BY resource").rows == (
            (1, 9, 2),
            (2, 5, 1),
        )
        assert not db.execute("SELECT * FROM violations").rows
        print("Final usage:", db.execute("SELECT resource, units, bookings FROM usage").rows)
        print("Final violations:", db.execute("SELECT * FROM violations").rows)


if __name__ == "__main__":
    main()
