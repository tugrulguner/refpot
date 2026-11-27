"""Installed public API checks for maintained SQL relations."""

import tempfile
import unittest
from pathlib import Path

from refpot.sql import Database, SQLError


class MaintainedSQLTests(unittest.TestCase):
    def test_capacity_join_does_not_scan_unrelated_rooms(self):
        for mode in ("overlay", "modular"):
            with self.subTest(mode=mode):
                work = []
                for rooms in (1, 128):
                    with Database(mode=mode) as db:
                        room_rows = tuple((room, 10) for room in range(1, rooms + 1))
                        db.execute(
                            "CREATE TABLE rooms (id INTEGER PRIMARY KEY, cap INTEGER NOT NULL)"
                        )
                        db.execute(
                            "CREATE TABLE bookings (id INTEGER PRIMARY KEY, "
                            "room INTEGER NOT NULL, seats INTEGER NOT NULL)"
                        )
                        with db.transaction():
                            for row in room_rows:
                                db.execute("INSERT INTO rooms VALUES (?, ?)", row)
                            db.execute("INSERT INTO bookings VALUES (1, 1, 6)")
                        db.execute(
                            "CREATE MATERIALIZED VIEW usage AS SELECT room, SUM(seats) AS total "
                            "FROM bookings GROUP BY room"
                        )
                        db.execute(
                            "CREATE MATERIALIZED VIEW over_capacity AS SELECT u.room, u.total, r.cap "
                            "FROM usage AS u JOIN rooms AS r ON u.room = r.id WHERE u.total > r.cap"
                        )
                        db.execute(
                            "CREATE ASSERTION capacity_ok CHECK (NOT EXISTS (SELECT * FROM over_capacity))"
                        )

                        def check_state(expected_bookings, total, db=db, room_rows=room_rows):
                            self.assertEqual(
                                db.execute("SELECT * FROM rooms ORDER BY id").rows, room_rows
                            )
                            self.assertEqual(
                                db.execute("SELECT * FROM bookings ORDER BY id").rows,
                                expected_bookings,
                            )
                            self.assertEqual(db.execute("SELECT * FROM usage").rows, ((1, total),))
                            self.assertEqual(
                                db.execute("SELECT * FROM over_capacity").rows,
                                ((1, total, 10),) if total > 10 else (),
                            )

                        db.execute("BEGIN")
                        before = db.stats()["maintenance_steps"]
                        db.execute("INSERT INTO bookings VALUES (2, 1, 1)")
                        initial_work = db.stats()["maintenance_steps"] - before
                        check_state(((1, 1, 6), (2, 1, 1)), 7)
                        before = db.stats()["maintenance_steps"]
                        db.execute("INSERT INTO bookings VALUES (3, 1, 4)")
                        work.append((initial_work, db.stats()["maintenance_steps"] - before))
                        check_state(((1, 1, 6), (2, 1, 1), (3, 1, 4)), 11)
                        with self.assertRaisesRegex(SQLError, "required-empty"):
                            db.execute("COMMIT")
                        check_state(((1, 1, 6),), 6)
                self.assertTrue(all(value > 0 for value in work[0]))
                self.assertEqual(
                    work[0], work[1], f"initial and appended work at 1 vs 128 rooms: {work}"
                )

    def test_keyed_join_reads_staged_right_rows_without_collapsing_fallback_bags(self):
        for mode in ("overlay", "modular"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "joins"
                with Database(path, mode=mode) as db:
                    db.execute("CREATE TABLE rooms (id INTEGER PRIMARY KEY, cap INTEGER NOT NULL)")
                    db.execute(
                        "CREATE TABLE bookings (id INTEGER PRIMARY KEY, room INTEGER NOT NULL)"
                    )
                    db.execute("INSERT INTO rooms VALUES (1, 10)")
                    db.execute("INSERT INTO rooms VALUES (2, 10)")
                    db.execute("CREATE MATERIALIZED VIEW caps AS SELECT cap FROM rooms")
                    db.execute(
                        "CREATE MATERIALIZED VIEW matched AS SELECT b.id, r.cap "
                        "FROM bookings AS b JOIN rooms AS r ON b.room = r.id"
                    )
                    db.execute(
                        "CREATE MATERIALIZED VIEW by_value AS SELECT b.id, r.id AS room "
                        "FROM bookings AS b JOIN rooms AS r ON b.room = r.cap"
                    )
                    db.execute(
                        "CREATE MATERIALIZED VIEW by_bag AS SELECT b.id, c.cap "
                        "FROM bookings AS b JOIN caps AS c ON b.room = c.cap"
                    )
                    db.execute("BEGIN")
                    db.execute("INSERT INTO bookings VALUES (5, -1)")
                    db.execute("INSERT INTO bookings VALUES (1, 10)")
                    self.assertEqual(db.execute("SELECT * FROM matched").rows, ())
                    self.assertEqual(
                        db.execute("SELECT * FROM by_value ORDER BY room").rows, ((1, 1), (1, 2))
                    )
                    self.assertEqual(db.execute("SELECT * FROM by_bag").rows, ((1, 10), (1, 10)))
                    db.execute("ROLLBACK")
                    self.assertEqual(db.execute("SELECT * FROM bookings").rows, ())
                    self.assertEqual(db.execute("SELECT * FROM by_bag").rows, ())
                    with db.transaction():
                        db.execute("UPDATE rooms SET cap = 11 WHERE id = 1")
                        db.execute("DELETE FROM rooms WHERE id = 2")
                        db.execute("INSERT INTO bookings VALUES (2, 1)")
                        db.execute("INSERT INTO bookings VALUES (3, 2)")
                        self.assertEqual(db.execute("SELECT * FROM matched").rows, ((2, 11),))
                        db.execute("INSERT INTO rooms VALUES (2, 22)")
                        self.assertEqual(
                            db.execute("SELECT * FROM matched ORDER BY id").rows, ((2, 11), (3, 22))
                        )
                with Database(path, mode=mode) as db:
                    self.assertEqual(
                        db.execute("SELECT * FROM matched ORDER BY id").rows, ((2, 11), (3, 22))
                    )
                    db.checkpoint()
                with Database(path, mode=mode) as db:
                    self.assertEqual(
                        db.execute("SELECT * FROM matched ORDER BY id").rows, ((2, 11), (3, 22))
                    )
                    db.execute("INSERT INTO bookings VALUES (4, 2)")
                    self.assertEqual(
                        db.execute("SELECT * FROM matched ORDER BY id").rows,
                        ((2, 11), (3, 22), (4, 22)),
                    )

    def test_first_group_update_does_not_rescan_unaffected_input(self):
        for mode in ("overlay", "modular"):
            with self.subTest(mode=mode):
                steps = []
                for groups in (1, 128):
                    with Database(mode=mode) as db:
                        db.execute(
                            "CREATE TABLE lines (id INTEGER PRIMARY KEY, basket INTEGER NOT NULL, units INTEGER NOT NULL)"
                        )
                        with db.transaction():
                            for i in range(groups):
                                db.execute("INSERT INTO lines VALUES (?, ?, 3)", (i, i))
                        db.execute(
                            "CREATE MATERIALIZED VIEW totals AS SELECT basket, SUM(units) AS total, COUNT(*) AS n FROM lines GROUP BY basket"
                        )
                        db.execute("BEGIN")
                        before = db.stats()["maintenance_steps"]
                        db.execute("UPDATE lines SET units = 5 WHERE id = 0")
                        steps.append(db.stats()["maintenance_steps"] - before)
                        self.assertEqual(
                            db.execute("SELECT * FROM totals ORDER BY basket").rows,
                            tuple((i, 5 if i == 0 else 3, 1) for i in range(groups)),
                        )
                        db.execute("ROLLBACK")
                        self.assertEqual(
                            db.execute("SELECT * FROM totals ORDER BY basket").rows,
                            tuple((i, 3, 1) for i in range(groups)),
                        )
                # Source staging still scans once. The group stage must not
                # add further full-population passes on top of that work.
                if mode == "overlay":
                    self.assertLessEqual(steps[1] - steps[0], 127, steps)

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
