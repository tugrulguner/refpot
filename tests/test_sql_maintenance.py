"""Installed public API checks for maintained SQL relations."""

import unittest

from refpot.sql import Database, SQLError


class MaintainedSQLTests(unittest.TestCase):
    def test_declared_group_tracks_candidate_changes_and_rollback(self):
        for mode in ("overlay", "modular"):
            with self.subTest(mode=mode), Database(mode=mode) as db:
                db.execute(
                    "CREATE TABLE reservations (id INTEGER PRIMARY KEY, "
                    "resource INTEGER NOT NULL, units INTEGER NOT NULL)"
                )
                db.execute("INSERT INTO reservations VALUES (1, 7, 3)")
                db.execute(
                    "CREATE MATERIALIZED VIEW usage AS SELECT resource, "
                    "SUM(units) AS total, COUNT(*) AS reservations "
                    "FROM reservations GROUP BY resource"
                )
                self.assertEqual(db.execute("SELECT * FROM usage").rows, ((7, 3, 1),))
                db.execute("BEGIN")
                db.execute("INSERT INTO reservations VALUES (2, 7, 4)")
                self.assertEqual(db.execute("SELECT * FROM usage").rows, ((7, 7, 2),))
                db.execute("ROLLBACK")
                self.assertEqual(db.execute("SELECT * FROM usage").rows, ((7, 3, 1),))
                with db.transaction():
                    db.execute("UPDATE reservations SET units = 8 WHERE id = 1")
                self.assertEqual(db.execute("SELECT * FROM usage").rows, ((7, 8, 1),))
                db.execute("DELETE FROM reservations WHERE id = 1")
                self.assertEqual(db.execute("SELECT * FROM usage").rows, ())

    def test_seeded_transactions_match_independent_full_state_oracle(self):
        import random
        from collections import Counter

        for mode in ("overlay", "modular"):
            with self.subTest(mode=mode), Database(mode=mode) as db:
                rng = random.Random(731904)
                db.execute(
                    "CREATE TABLE reservations (id INTEGER PRIMARY KEY, resource INTEGER NOT NULL, units INTEGER NOT NULL, active INTEGER NOT NULL)"
                )
                db.execute(
                    "CREATE TABLE limits (resource INTEGER PRIMARY KEY, capacity INTEGER NOT NULL)"
                )
                db.execute(
                    "CREATE MATERIALIZED VIEW reservation_bag AS SELECT resource, units FROM reservations"
                )
                db.execute(
                    "CREATE MATERIALIZED VIEW usage AS SELECT r.resource, SUM(r.units) AS units, COUNT(*) AS n FROM reservations AS r JOIN limits AS l ON r.resource = l.resource WHERE r.active = 1 GROUP BY r.resource"
                )
                db.execute(
                    "CREATE MATERIALIZED VIEW violations AS SELECT r.resource, r.units FROM reservations AS r JOIN limits AS l ON r.resource = l.resource WHERE r.active = 1 AND r.units > l.capacity"
                )
                db.execute(
                    "CREATE ASSERTION capacity_ok CHECK (NOT EXISTS (SELECT * FROM violations))"
                )

                reservations = {}
                limits = {1: 12, 2: 15, 3: 18}
                for resource, capacity in limits.items():
                    db.execute("INSERT INTO limits VALUES (?, ?)", (resource, capacity))

                def oracle(reservations=reservations, limits=limits, db=db):
                    source_rows = tuple(sorted(reservations.values()))
                    limit_rows = tuple(sorted(limits.items()))
                    self.assertEqual(
                        tuple(
                            sorted(
                                db.execute(
                                    "SELECT id, resource, units, active FROM reservations"
                                ).rows
                            )
                        ),
                        source_rows,
                    )
                    bag = Counter((resource, units) for _, resource, units, _ in source_rows)
                    observed_bag = Counter(
                        db.execute("SELECT resource, units FROM reservation_bag").rows
                    )
                    assert observed_bag == bag
                    totals = {}
                    for _, resource, units, active in source_rows:
                        if active and resource in limits:
                            total, count = totals.get(resource, (0, 0))
                            totals[resource] = (total + units, count + 1)
                    expected_usage = tuple(
                        sorted(
                            (resource, total, count) for resource, (total, count) in totals.items()
                        )
                    )
                    observed_usage = tuple(
                        sorted(db.execute("SELECT resource, units, n FROM usage").rows)
                    )
                    assert observed_usage == expected_usage
                    expected_violations = Counter(
                        (resource, units)
                        for _, resource, units, active in source_rows
                        if active and resource in limits and units > limits[resource]
                    )
                    assert (
                        Counter(db.execute("SELECT resource, units FROM violations").rows)
                        == expected_violations
                    )
                    assert (
                        tuple(sorted(db.execute("SELECT resource, capacity FROM limits").rows))
                        == limit_rows
                    )

                def mutate_reservations(reservations=reservations, limits=limits, rng=rng, db=db):
                    existing = list(reservations)
                    if not existing or rng.random() < 0.42:
                        row_id = max(existing, default=0) + 1
                        row = (
                            row_id,
                            rng.choice(tuple(limits)),
                            rng.randint(1, 5),
                            rng.randint(0, 1),
                        )
                        reservations[row_id] = row
                        db.execute("INSERT INTO reservations VALUES (?, ?, ?, ?)", row)
                    elif rng.random() < 0.52:
                        row_id = rng.choice(existing)
                        reservations.pop(row_id)
                        db.execute("DELETE FROM reservations WHERE id = ?", (row_id,))
                    else:
                        row_id = rng.choice(existing)
                        row = (
                            row_id,
                            rng.choice(tuple(limits)),
                            rng.randint(1, 5),
                            rng.randint(0, 1),
                        )
                        reservations[row_id] = row
                        db.execute(
                            "UPDATE reservations SET resource = ?, units = ?, active = ? WHERE id = ?",
                            (row[1], row[2], row[3], row_id),
                        )

                def mutate_limits(limits=limits, rng=rng, db=db):
                    keys = list(limits)
                    if len(keys) > 1 and rng.random() < 0.35:
                        key = rng.choice(keys)
                        del limits[key]
                        db.execute("DELETE FROM limits WHERE resource = ?", (key,))
                    else:
                        key = rng.choice(keys)
                        capacity = rng.randint(14, 24)
                        limits[key] = capacity
                        db.execute(
                            "UPDATE limits SET capacity = ? WHERE resource = ?", (capacity, key)
                        )

                for step in range(45):
                    with db.transaction():
                        (mutate_reservations if rng.random() < 0.68 else mutate_limits)()
                        oracle()
                        if step % 9 == 0:
                            # Force a violation; random low-valued writes cannot reach it.
                            row_id = max(reservations, default=0) + 1
                            resource = next(iter(limits))
                            row = (row_id, resource, limits[resource] + 1, 1)
                            db.execute("INSERT INTO reservations VALUES (?, ?, ?, ?)", row)
                            reservations[row_id] = row
                            oracle()
                            self.assertTrue(db.execute("SELECT * FROM violations").rows)
                            reservations[row_id] = (row_id, resource, 1, 1)
                            db.execute("UPDATE reservations SET units = 1 WHERE id = ?", (row_id,))
                            oracle()
                            self.assertFalse(db.execute("SELECT * FROM violations").rows)
                    oracle()

                # Rejected COMMIT must discard both source and maintained rows.
                rid = max(reservations, default=0) + 1
                bad_resource = next(iter(limits))
                with self.assertRaises(SQLError):
                    db.execute("BEGIN")
                    db.execute("INSERT INTO reservations VALUES (?, ?, 99, 1)", (rid, bad_resource))
                    reservations[rid] = (rid, bad_resource, 99, 1)
                    db.execute("COMMIT")
                reservations.pop(rid)
                oracle()
                # An ordinary execution error aborts the whole explicit transaction.
                prior = dict(reservations)
                with self.assertRaises(SQLError):
                    db.execute("BEGIN")
                    db.execute("INSERT INTO reservations VALUES (?, 2, 1, 1)", (rid,))
                    db.execute("INSERT INTO absent_table VALUES (1)")
                self.assertEqual(reservations, prior)
                oracle()

    def test_unsupported_declarations_and_explain_are_nonmutating(self):
        with Database(mode="overlay") as db:
            db.execute("CREATE TABLE source (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)")
            db.execute("INSERT INTO source VALUES (1, 7)")
            with self.assertRaises(SQLError):
                db.execute(
                    "CREATE MATERIALIZED VIEW ordered AS SELECT value FROM source ORDER BY value"
                )
            self.assertEqual(db.execute("SELECT * FROM source").rows, ((1, 7),))
            with self.assertRaises(SQLError):
                db.execute("SELECT * FROM ordered")
            explained = db.execute("INSERT INTO source VALUES (2, 9)", explain=True)
            self.assertTrue(explained.plan)
            self.assertEqual(db.execute("SELECT * FROM source").rows, ((1, 7),))
            db.execute("BEGIN")
            db.execute("INSERT INTO source VALUES (2, 9)")
            with self.assertRaises(SQLError):
                db.execute("INSERT INTO absent_table VALUES (1)")
            # An ordinary execution error aborts every earlier write in the transaction.
            self.assertEqual(db.execute("SELECT * FROM source").rows, ((1, 7),))


if __name__ == "__main__":
    unittest.main()
