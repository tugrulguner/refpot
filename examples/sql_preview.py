"""Ordinary SQL with the unreleased, volatile RefPot package preview.

Run with: python examples/sql_preview.py
The existing durable refpot.Database API is separate and unchanged.
"""

from refpot.sql import Database


def main() -> None:
    with Database() as db:
        db.execute(
            "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer INTEGER NOT NULL, product INTEGER NOT NULL)"
        )
        db.execute("CREATE TABLE prices (id INTEGER PRIMARY KEY, amount INTEGER NOT NULL)")
        with db.transaction():
            for row in ((1, 7), (2, 11)):
                db.execute("INSERT INTO prices VALUES (?, ?)", row)
            for row in ((1, 8, 1), (2, 8, 2), (3, 9, 1)):
                db.execute("INSERT INTO orders VALUES (?, ?, ?)", row)
        query = (
            "SELECT o.customer, COUNT(*) AS orders, SUM(p.amount) AS total "
            "FROM orders AS o JOIN prices AS p ON o.product = p.id "
            "GROUP BY o.customer ORDER BY total DESC LIMIT ?"
        )
        before = db.execute(query=query, parameters=(10,))
        assert before.rows == ((8, 2, 18), (9, 1, 7))
        print("Before:", before.columns, before.rows)
        print("Native plan:", db.execute(query, (10,), explain=True).plan)
        try:
            with db.transaction():
                db.execute("UPDATE prices SET amount = ? WHERE id = ?", (13, 2))
                print("Read your writes:", db.execute(query, (10,)).rows)
                raise ValueError("discard this price change")
        except ValueError:
            pass
        assert db.execute(query, (10,)).rows == before.rows
        print("After rollback:", db.execute(query, (10,)).rows)
        with db.transaction():
            db.execute("UPDATE prices SET amount = ? WHERE id = ?", (13, 2))
        after = db.execute(query, (10,))
        assert after.rows == ((8, 2, 20), (9, 1, 7))
        print("After commit:", after.rows)
        print("Native work counters:", db.stats())
    print("Closed. SQL state was volatile; no database file or provider was used.")


if __name__ == "__main__":
    main()
