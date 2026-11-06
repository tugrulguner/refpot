"""Public contract for atomic, offline maintained-definition replacement."""

import random

import pytest

from refpot.sql import Database, SQLError


def seed(db):
    db.execute(
        "CREATE TABLE orders (id INTEGER PRIMARY KEY, account INTEGER NOT NULL, amount INTEGER NOT NULL, status INTEGER NOT NULL)"
    )
    db.execute("CREATE TABLE capacity (account INTEGER PRIMARY KEY, maximum INTEGER NOT NULL)")
    for row in [(1, 1, 10, 1), (2, 1, 20, 2), (3, 2, 7, 2), (4, 2, 7, 2)]:
        db.execute("INSERT INTO orders VALUES (?, ?, ?, ?)", row)
    for row in [(1, 30), (2, 30)]:
        db.execute("INSERT INTO capacity VALUES (?, ?)", row)
    db.execute(
        "CREATE MATERIALIZED VIEW chosen AS SELECT account, amount FROM orders WHERE status = 1"
    )
    db.execute(
        "CREATE MATERIALIZED VIEW totals AS SELECT account, SUM(amount) AS total, COUNT(*) AS n FROM chosen GROUP BY account"
    )
    db.execute(
        "CREATE MATERIALIZED VIEW violations AS SELECT t.account FROM totals AS t JOIN capacity AS c ON t.account = c.account WHERE t.total > c.maximum"
    )
    db.execute("CREATE ASSERTION within_capacity CHECK (NOT EXISTS (SELECT * FROM violations))")
    db.execute("CREATE MATERIALIZED VIEW unrelated AS SELECT id FROM orders")


def state(db):
    return {
        name: db.execute(f"SELECT * FROM {name} ORDER BY {order}").rows
        for name, order in [
            ("orders", "id"),
            ("capacity", "account"),
            ("chosen", "account, amount"),
            ("totals", "account"),
            ("violations", "account"),
            ("unrelated", "id"),
        ]
    }


@pytest.mark.parametrize("mode", ["overlay", "modular"])
@pytest.mark.parametrize("persistent", [False, True])
def test_replace_recomputes_descendants_and_reopens(tmp_path, mode, persistent):
    path = tmp_path / "model.db" if persistent else None
    with Database(path, mode=mode) as db:
        seed(db)
        before = state(db)
        result = db.execute(
            "ALTER MATERIALIZED VIEW chosen AS SELECT account, amount FROM orders WHERE status = ?",
            (2,),
        )
        assert result.affected == 0
        assert result.rows == ()
        after = state(db)
        assert after["chosen"] == ((1, 20), (2, 7), (2, 7))
        assert after["totals"] == ((1, 20, 1), (2, 14, 2))
        for name in ("orders", "capacity", "unrelated", "violations"):
            assert after[name] == before[name]
        with pytest.raises(SQLError):
            db.execute("INSERT INTO orders VALUES (5, 1, 11, 2)")
        assert state(db) == after
        db.execute("INSERT INTO orders VALUES (5, 1, 5, 2)")
        expected = state(db)
    if persistent:
        with Database(path, mode=mode) as db:
            assert state(db) == expected
            db.checkpoint()
        with Database(path, mode=mode) as db:
            assert state(db) == expected
            db.execute("UPDATE orders SET status = 1 WHERE id = 2")
            assert db.execute("SELECT * FROM totals ORDER BY account").rows == (
                (1, 5, 1),
                (2, 14, 2),
            )


@pytest.mark.parametrize("mode", ["overlay", "modular"])
def test_rejection_preserves_catalog_results_and_disk(tmp_path, mode):
    path = tmp_path / "model.db"
    with Database(path, mode=mode) as db:
        seed(db)
        db.execute("UPDATE capacity SET maximum = 15 WHERE account = 1")
        before = state(db)
        files = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
        invalid = [
            "ALTER MATERIALIZED VIEW absent AS SELECT account, amount FROM orders",
            "ALTER MATERIALIZED VIEW orders AS SELECT id, account, amount, status FROM orders",
            "ALTER MATERIALIZED VIEW refpot_internal_2_0 AS SELECT account, amount FROM orders",
            "ALTER MATERIALIZED VIEW chosen AS SELECT amount, account FROM orders",
            "ALTER MATERIALIZED VIEW chosen AS SELECT account AS renamed, amount FROM orders",
            "ALTER MATERIALIZED VIEW chosen AS SELECT account FROM orders",
            "ALTER MATERIALIZED VIEW chosen AS SELECT account, missing AS amount FROM orders",
            "ALTER MATERIALIZED VIEW chosen AS SELECT account, amount FROM chosen",
            "ALTER MATERIALIZED VIEW chosen AS SELECT account, total AS amount FROM totals",
            "ALTER MATERIALIZED VIEW chosen AS SELECT account, amount FROM orders WHERE status = 2",
            "ALTER MATERIALIZED VIEW chosen AS SELECT account, amount * 2 AS amount FROM orders",
        ]
        for query in invalid:
            with pytest.raises(SQLError):
                db.execute(query)
            assert state(db) == before
            assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == files
        db.execute("INSERT INTO orders VALUES (5, 1, 2, 1)")
    with Database(path, mode=mode) as db:
        assert db.execute("SELECT * FROM totals").rows == ((1, 12, 2),)


@pytest.mark.parametrize("mode", ["overlay", "modular"])
def test_explain_and_explicit_transaction_boundaries(mode):
    with Database(mode=mode) as db:
        seed(db)
        db.execute("UPDATE capacity SET maximum = 15 WHERE account = 1")
        before = state(db)
        query = (
            "ALTER MATERIALIZED VIEW chosen AS SELECT account, amount FROM orders WHERE status = 2"
        )
        result = db.execute(query, explain=True)
        assert result.rows == ()
        assert "ALTER MATERIALIZED VIEW" in result.plan
        assert state(db) == before
        with pytest.raises(SQLError):
            db.execute(query)
        with db.transaction():
            db.execute("INSERT INTO orders VALUES (5, 1, 1, 1)")
            with pytest.raises(SQLError):
                db.execute(query, explain=True)
            assert db.execute("SELECT * FROM orders WHERE id = 5").rows == ((5, 1, 1, 1),)
        with pytest.raises(SQLError), db.transaction():
            db.execute("INSERT INTO orders VALUES (6, 1, 1, 1)")
            with pytest.raises(SQLError):
                db.execute(query)
        assert db.execute("SELECT * FROM orders WHERE id = 6").rows == ()
        assert db.execute("SELECT * FROM totals").rows == ((1, 11, 2),)


@pytest.mark.parametrize("mode", ["overlay", "modular"])
def test_changed_dependencies_absence_and_late_declaration(tmp_path, mode):
    path = tmp_path / "model.db"
    with Database(path, mode=mode) as db:
        seed(db)
        db.execute(
            "CREATE MATERIALIZED VIEW later AS SELECT account, amount FROM orders WHERE status = 2"
        )
        db.execute("ALTER MATERIALIZED VIEW chosen AS SELECT * FROM later")
        assert db.execute("SELECT * FROM totals ORDER BY account").rows == ((1, 20, 1), (2, 14, 2))
        db.execute("CREATE TABLE blocked (account INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO blocked VALUES (1)")
        db.execute(
            "ALTER MATERIALIZED VIEW chosen AS SELECT o.account, o.amount FROM orders AS o WHERE NOT EXISTS (SELECT * FROM blocked AS b WHERE b.account = o.account)"
        )
        assert db.execute("SELECT * FROM totals").rows == ((2, 14, 2),)
        db.execute("CREATE MATERIALIZED VIEW newest AS SELECT account, total FROM totals")
        db.checkpoint()
    with Database(path, mode=mode) as db:
        db.execute("DELETE FROM blocked WHERE account = 1")
        assert db.execute("SELECT * FROM newest ORDER BY account").rows == ((1, 30), (2, 14))
        db.execute("INSERT INTO blocked VALUES (2)")
        assert db.execute("SELECT * FROM newest").rows == ((1, 30),)
        before = db.stats()
        db.execute("ALTER MATERIALIZED VIEW chosen AS SELECT account, amount FROM later")
        after = db.stats()
        for name in (
            "source_mutation_applications",
            "full_bag_copied_entries",
            "maintenance_steps",
        ):
            assert after[name] >= before[name], name


@pytest.mark.parametrize("mode", ["overlay", "modular"])
def test_repeated_replacement_reclaims_internal_catalog(mode):
    with Database(mode=mode) as db:
        seed(db)
        for iteration in range(1050):
            value = iteration % 2 + 1
            query = "ALTER MATERIALIZED VIEW chosen AS SELECT account, amount FROM orders WHERE status = ?"
            if iteration % 3 == 0:
                query += " AND amount >= 0"
            db.execute(query, (value,))
            expected = ((1, 10, 1),) if value == 1 else ((1, 20, 1), (2, 14, 2))
            assert db.execute("SELECT * FROM totals ORDER BY account").rows == expected
        db.execute("CREATE MATERIALIZED VIEW final AS SELECT * FROM chosen")
        assert db.execute("SELECT * FROM final ORDER BY account, amount").rows == (
            (1, 20),
            (2, 7),
            (2, 7),
        )


@pytest.mark.parametrize("mode", ["overlay", "modular"])
@pytest.mark.parametrize(
    "count,same_key,error", [(320, True, "row limit"), (1001, False, "work limit")]
)
def test_migration_budget_refusal_preserves_definition(mode, count, same_key, error):
    with Database(mode=mode) as db:
        db.execute("CREATE TABLE source (id INTEGER PRIMARY KEY, k INTEGER NOT NULL)")
        with db.transaction():
            for key in range(count):
                db.execute("INSERT INTO source VALUES (?, ?)", (key, 1 if same_key else key))
        db.execute("CREATE MATERIALIZED VIEW kept AS SELECT id, k FROM source")
        before = db.execute("SELECT * FROM kept ORDER BY id").rows
        with pytest.raises(SQLError, match=error):
            db.execute(
                "ALTER MATERIALIZED VIEW kept AS SELECT a.id, b.k FROM source AS a JOIN source AS b ON a.k = b.k"
            )
        assert db.execute("SELECT * FROM kept ORDER BY id").rows == before
        db.execute("INSERT INTO source VALUES (?, ?)", (count, 9))
        assert db.execute("SELECT * FROM kept WHERE id = ?", (count,)).rows == ((count, 9),)


@pytest.mark.parametrize("mode", ["overlay", "modular"])
def test_random_migrations_writes_reopen_against_independent_oracle(tmp_path, mode):
    rng = random.Random(41051)
    path = tmp_path / "model.db"
    rows = {1: (1, 10, 1), 2: (1, 20, 2), 3: (2, 7, 2), 4: (2, 7, 2)}
    selected = 1

    def expected(candidate, status):
        chosen = sorted(
            (account, amount) for account, amount, flag in candidate.values() if flag == status
        )
        groups = {}
        for account, amount in chosen:
            total, count = groups.get(account, (0, 0))
            groups[account] = (total + amount, count + 1)
        totals = tuple((key, *value) for key, value in sorted(groups.items()))
        return tuple(chosen), totals, all(total <= 30 for total, _ in groups.values())

    with Database(path, mode=mode) as db:
        seed(db)
    for step in range(80):
        with Database(path, mode=mode) as db:
            candidate = rows.copy()
            new_status = selected
            if step % 2:
                key = rng.choice(list(rows))
                account, _, flag = rows[key]
                amount = rng.randrange(0, 41)
                candidate[key] = (account, amount, flag)
                query, parameters = "UPDATE orders SET amount = ? WHERE id = ?", (amount, key)
            else:
                new_status = rng.randrange(1, 4)
                query = "ALTER MATERIALIZED VIEW chosen AS SELECT account, amount FROM orders WHERE status = ?"
                parameters = (new_status,)
            chosen, totals, valid = expected(candidate, new_status)
            if valid:
                db.execute(query, parameters)
                rows, selected = candidate, new_status
            else:
                with pytest.raises(SQLError):
                    db.execute(query, parameters)
                chosen, totals, _ = expected(rows, selected)
            assert db.execute("SELECT * FROM chosen ORDER BY account, amount").rows == chosen
            assert db.execute("SELECT * FROM totals ORDER BY account").rows == totals
            assert db.execute("SELECT * FROM orders ORDER BY id").rows == tuple(
                (key, *value) for key, value in sorted(rows.items())
            )
            assert db.execute("SELECT * FROM violations").rows == ()
            if step % 10 == 0:
                db.checkpoint()
