"""Public SQL regressions for shared maintained-view catalog lifecycles."""

import pytest

from refpot.sql import Database, SQLError


def _seed(db):
    db.execute(
        "CREATE TABLE events (id INTEGER PRIMARY KEY, bucket INTEGER NOT NULL, amount INTEGER NOT NULL, active INTEGER NOT NULL)"
    )
    db.execute("INSERT INTO events VALUES (1, 1, 3, 1)")
    db.execute("INSERT INTO events VALUES (2, 1, 5, 1)")
    db.execute("INSERT INTO events VALUES (3, 2, 7, 1)")
    db.execute("INSERT INTO events VALUES (4, 2, 11, 0)")


def test_equivalent_shared_views_distinct_aggregates_and_populated_addition():
    with Database() as db:
        _seed(db)
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
        assert db.execute("SELECT bucket, amount FROM active_a ORDER BY bucket, amount").rows == (
            (1, 3),
            (1, 5),
            (2, 7),
        )
        assert db.execute("SELECT bucket, amount FROM active_b ORDER BY bucket, amount").rows == (
            (1, 3),
            (1, 5),
            (2, 7),
        )
        assert db.execute("SELECT bucket, total FROM totals ORDER BY bucket").rows == (
            (1, 8),
            (2, 7),
        )
        assert db.execute("SELECT bucket, n FROM counts ORDER BY bucket").rows == ((1, 2), (2, 1))

        # Adding a shared definition after data exists initializes its result.
        db.execute(
            "CREATE MATERIALIZED VIEW large AS SELECT bucket, amount FROM events WHERE amount >= 5"
        )
        assert db.execute("SELECT bucket, amount FROM large ORDER BY bucket, amount").rows == (
            (1, 5),
            (2, 7),
            (2, 11),
        )
        db.execute("INSERT INTO events VALUES (5, 1, 9, 1)")
        assert db.execute("SELECT bucket, total FROM totals ORDER BY bucket").rows == (
            (1, 17),
            (2, 7),
        )
        assert db.execute("SELECT bucket, n FROM counts ORDER BY bucket").rows == ((1, 3), (2, 1))


def test_replacing_one_shared_view_preserves_peer_and_dependents():
    with Database() as db:
        _seed(db)
        db.execute(
            "CREATE MATERIALIZED VIEW left_view AS SELECT bucket, amount FROM events WHERE active = 1"
        )
        db.execute(
            "CREATE MATERIALIZED VIEW right_view AS SELECT bucket, amount FROM events WHERE active = 1"
        )
        db.execute(
            "CREATE MATERIALIZED VIEW left_sum AS SELECT bucket, SUM(amount) AS total FROM left_view GROUP BY bucket"
        )
        db.execute(
            "CREATE MATERIALIZED VIEW right_count AS SELECT bucket, COUNT(*) AS n FROM right_view GROUP BY bucket"
        )
        before_right = db.execute(
            "SELECT bucket, amount FROM right_view ORDER BY bucket, amount"
        ).rows

        db.execute(
            "ALTER MATERIALIZED VIEW left_view AS SELECT bucket, amount FROM events WHERE active >= 0"
        )
        assert db.execute("SELECT bucket, amount FROM left_view ORDER BY bucket, amount").rows == (
            (1, 3),
            (1, 5),
            (2, 7),
            (2, 11),
        )
        assert (
            db.execute("SELECT bucket, amount FROM right_view ORDER BY bucket, amount").rows
            == before_right
        )
        assert db.execute("SELECT bucket, total FROM left_sum ORDER BY bucket").rows == (
            (1, 8),
            (2, 18),
        )
        assert db.execute("SELECT bucket, n FROM right_count ORDER BY bucket").rows == (
            (1, 2),
            (2, 1),
        )
        db.execute("UPDATE events SET amount = 13 WHERE id = 3")
        assert db.execute("SELECT bucket, total FROM left_sum ORDER BY bucket").rows == (
            (1, 8),
            (2, 24),
        )
        assert db.execute("SELECT bucket, n FROM right_count ORDER BY bucket").rows == (
            (1, 2),
            (2, 1),
        )


def test_shared_view_replacement_errors_and_assertion_rollback():
    with Database() as db:
        _seed(db)
        db.execute(
            "CREATE MATERIALIZED VIEW selected AS SELECT bucket, amount FROM events WHERE active = 1"
        )
        db.execute(
            "CREATE MATERIALIZED VIEW peer AS SELECT bucket, amount FROM events WHERE active = 1"
        )
        db.execute(
            "CREATE MATERIALIZED VIEW sums AS SELECT bucket, SUM(amount) AS total FROM selected GROUP BY bucket"
        )
        db.execute("CREATE MATERIALIZED VIEW too_large AS SELECT bucket FROM sums WHERE total > 10")
        db.execute("CREATE ASSERTION no_large CHECK (NOT EXISTS (SELECT * FROM too_large))")
        original = db.execute("SELECT bucket, amount FROM selected ORDER BY bucket, amount").rows
        # The otherwise-valid logical replacement is rejected by a dependent assertion.
        with pytest.raises(SQLError):
            db.execute(
                "ALTER MATERIALIZED VIEW selected AS SELECT bucket, amount FROM events WHERE active >= 0"
            )
        assert (
            db.execute("SELECT bucket, amount FROM selected ORDER BY bucket, amount").rows
            == original
        )
        assert (
            db.execute("SELECT bucket, amount FROM peer ORDER BY bucket, amount").rows == original
        )
        assert db.execute("SELECT bucket, total FROM sums ORDER BY bucket").rows == ((1, 8), (2, 7))
        # Invalid output shape and dependency cycle also leave the old catalog usable.
        with pytest.raises(SQLError):
            db.execute(
                "ALTER MATERIALIZED VIEW selected AS SELECT amount, bucket FROM events WHERE active = 1"
            )
        with pytest.raises(SQLError):
            db.execute(
                "ALTER MATERIALIZED VIEW selected AS SELECT bucket, amount FROM sums WHERE total > 0"
            )
        assert (
            db.execute("SELECT bucket, amount FROM selected ORDER BY bucket, amount").rows
            == original
        )


def test_shared_catalog_wal_reopen_checkpoint_reopen_and_continue(tmp_path):
    path = tmp_path / "shared.db"
    with Database(path) as db:
        _seed(db)
        db.execute(
            "CREATE MATERIALIZED VIEW a AS SELECT bucket, amount FROM events WHERE active = 1"
        )
        db.execute(
            "CREATE MATERIALIZED VIEW b AS SELECT bucket, amount FROM events WHERE active = 1"
        )
        db.execute(
            "CREATE MATERIALIZED VIEW totals AS SELECT bucket, SUM(amount) AS total FROM a GROUP BY bucket"
        )
        db.execute(
            "CREATE MATERIALIZED VIEW counts AS SELECT bucket, COUNT(*) AS n FROM b GROUP BY bucket"
        )
        db.execute(
            "ALTER MATERIALIZED VIEW a AS SELECT bucket, amount FROM events WHERE active >= 0"
        )
        db.execute("INSERT INTO events VALUES (5, 1, 2, 1)")

    # Close does not checkpoint: this first reopen exercises WAL-only recovery.
    with Database(path, mode="modular") as db:
        assert db.execute("SELECT bucket, total FROM totals ORDER BY bucket").rows == (
            (1, 10),
            (2, 18),
        )
        assert db.execute("SELECT bucket, n FROM counts ORDER BY bucket").rows == ((1, 3), (2, 1))
        assert db.execute("SELECT bucket, amount FROM a ORDER BY bucket, amount").rows == (
            (1, 2),
            (1, 3),
            (1, 5),
            (2, 7),
            (2, 11),
        )
        assert db.execute("SELECT bucket, amount FROM b ORDER BY bucket, amount").rows == (
            (1, 2),
            (1, 3),
            (1, 5),
            (2, 7),
        )
        db.checkpoint()

    with Database(path) as db:
        assert db.execute("SELECT bucket, total FROM totals ORDER BY bucket").rows == (
            (1, 10),
            (2, 18),
        )
        assert db.execute("SELECT bucket, n FROM counts ORDER BY bucket").rows == ((1, 3), (2, 1))
        db.execute("INSERT INTO events VALUES (6, 2, 4, 1)")

    with Database(path, mode="modular") as db:
        assert db.execute("SELECT bucket, total FROM totals ORDER BY bucket").rows == (
            (1, 10),
            (2, 22),
        )
        assert db.execute("SELECT bucket, n FROM counts ORDER BY bucket").rows == ((1, 3), (2, 2))
        assert db.execute("SELECT bucket, amount FROM b ORDER BY bucket, amount").rows == (
            (1, 2),
            (1, 3),
            (1, 5),
            (2, 4),
            (2, 7),
        )
