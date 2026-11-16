"""Runnable source-preview tracer for exact maintained-query reuse.

Run in a checkout with its SQL preview extension built: python examples/sql_query_reuse.py
"""

from refpot.sql import Database


def main() -> None:
    with Database() as db:
        db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, amount INTEGER NOT NULL)")
        for row in ((1, 4), (2, 4), (3, 1)):
            db.execute("INSERT INTO items VALUES (?, ?)", row)
        db.execute(
            "CREATE MATERIALIZED VIEW eligible AS SELECT amount AS value FROM items WHERE amount > 2"
        )
        query = "SELECT amount AS value FROM items WHERE amount > 2 ORDER BY value"
        result = db.execute(query)
        assert result.rows == ((4,), (4,))
        assert "MAINTAINED_REUSE eligible" in result.plan
        print("reused:", result.plan, result.rows)
        controls = (
            "SELECT amount AS value FROM items WHERE amount > 1",
            "SELECT amount AS value FROM items WHERE amount >= 2",
            "SELECT id AS value FROM items WHERE amount > 2",
        )
        for control in controls:
            result = db.execute(control)
            assert "MAINTAINED_REUSE" not in result.plan
            print("fallback:", result.plan, result.rows)
        explain = db.execute(query, explain=True)
        assert "MAINTAINED_REUSE eligible" in explain.plan
        assert db.execute(query).rows == ((4,), (4,))
        with db.transaction():
            db.execute("INSERT INTO items VALUES (?, ?)", (4, 9))
            assert db.execute("SELECT amount AS value FROM items WHERE amount > 2").rows == (
                (4,),
                (4,),
                (9,),
            )
        assert db.execute("SELECT amount AS value FROM items WHERE amount > 2").rows == (
            (4,),
            (4,),
            (9,),
        )


if __name__ == "__main__":
    main()
