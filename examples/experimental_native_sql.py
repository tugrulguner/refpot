"""Run ordinary SQL against the local in-process, volatile native preview."""

import argparse
import sys
from pathlib import Path

# A copied standalone consumer finds native_sql.py beside this file. The source
# example locates the research adapter; neither path imports installed refpot.
if not (Path(__file__).resolve().parent / "native_sql.py").exists():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/native-sql"))
from native_sql import Database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--mode", choices=("overlay", "modular"), default="overlay")
    args = parser.parse_args()
    with Database(library=args.library, mode=args.mode) as db:
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
    print("Closed. State was volatile; no database file or provider was used.")


if __name__ == "__main__":
    main()
