"""Public installed-API absence and transaction-local maintenance contracts."""

import random
import unittest
from collections import Counter

from refpot.sql import Database, SQLError


class AbsenceSQLTests(unittest.TestCase):
    def test_appended_booking_with_existing_room_skips_unrelated_rows(self):
        for mode in ("overlay", "modular"):
            with self.subTest(mode=mode):
                work = []
                for size in (1, 128):
                    with Database(mode=mode) as db:
                        db.execute("CREATE TABLE rooms (id INTEGER PRIMARY KEY)")
                        db.execute(
                            "CREATE TABLE bookings (id INTEGER PRIMARY KEY, room INTEGER NOT NULL)"
                        )
                        with db.transaction():
                            for room in range(1, size + 1):
                                db.execute("INSERT INTO rooms VALUES (?)", (room,))
                                db.execute("INSERT INTO bookings VALUES (?, ?)", (room, room))
                        db.execute(
                            "CREATE MATERIALIZED VIEW missing AS SELECT b.id, b.room "
                            "FROM bookings AS b WHERE NOT EXISTS "
                            "(SELECT * FROM rooms AS r WHERE r.id = b.room)"
                        )
                        db.execute(
                            "CREATE ASSERTION valid_rooms CHECK (NOT EXISTS (SELECT * FROM missing))"
                        )
                        db.execute("BEGIN")
                        # The first mutation prepares the transaction; the second appends to it.
                        db.execute("INSERT INTO bookings VALUES (500, 1)")
                        before = db.stats()["maintenance_steps"]
                        db.execute("INSERT INTO bookings VALUES (501, 1)")
                        work.append(db.stats()["maintenance_steps"] - before)
                        seed = tuple((room, room) for room in range(1, size + 1))
                        self.assertEqual(
                            db.execute("SELECT * FROM bookings ORDER BY id").rows,
                            (*seed, (500, 1), (501, 1)),
                        )
                        self.assertEqual(db.execute("SELECT * FROM missing").rows, ())
                        db.execute("ROLLBACK")
                        self.assertEqual(
                            db.execute("SELECT * FROM bookings ORDER BY id").rows, seed
                        )
                        self.assertEqual(db.execute("SELECT * FROM missing").rows, ())
                self.assertGreater(work[0], 0)
                self.assertEqual(work[0], work[1], f"unrelated-room work: {work}")

    def test_missing_resource_rejects_commit_but_allows_repair(self):
        for mode in ("overlay", "modular"):
            with self.subTest(mode=mode), Database(mode=mode) as db:
                db.execute("CREATE TABLE resources (id INTEGER PRIMARY KEY)")
                db.execute(
                    "CREATE TABLE reservations (id INTEGER PRIMARY KEY, resource INTEGER NOT NULL)"
                )
                db.execute(
                    "CREATE MATERIALIZED VIEW missing AS SELECT r.id, r.resource "
                    "FROM reservations AS r WHERE NOT EXISTS "
                    "(SELECT * FROM resources AS s WHERE s.id = r.resource)"
                )
                db.execute("CREATE ASSERTION valid_refs CHECK (NOT EXISTS (SELECT * FROM missing))")
                with self.assertRaises(SQLError), db.transaction():
                    db.execute("INSERT INTO reservations VALUES (1, 7)")
                    self.assertEqual(db.execute("SELECT * FROM missing").rows, ((1, 7),))
                self.assertEqual(db.execute("SELECT * FROM reservations").rows, ())
                with db.transaction():
                    db.execute("INSERT INTO reservations VALUES (1, 7)")
                    db.execute("INSERT INTO resources VALUES (7)")
                    self.assertEqual(db.execute("SELECT * FROM missing").rows, ())
                with self.assertRaises(SQLError):
                    db.execute("DELETE FROM resources WHERE id = 7")
                self.assertEqual(db.execute("SELECT * FROM resources").rows, ((7,),))
                with db.transaction():
                    db.execute("DELETE FROM resources WHERE id = 7")
                    self.assertEqual(db.execute("SELECT * FROM missing").rows, ((1, 7),))
                    db.execute("DELETE FROM reservations WHERE id = 1")
                    db.execute("INSERT INTO resources VALUES (7)")
                    db.execute("INSERT INTO reservations VALUES (1, 7)")
                with self.assertRaises(SQLError), db.transaction():
                    db.execute("DELETE FROM resources WHERE id = 7")
                    db.execute("INSERT INTO reservations VALUES (1, 8)")
                self.assertEqual(db.execute("SELECT * FROM resources").rows, ((7,),))
                self.assertEqual(db.execute("SELECT * FROM reservations").rows, ((1, 7),))
                self.assertEqual(db.execute("SELECT * FROM missing").rows, ())

    def test_seeded_bag_absence_matches_independent_source_replay(self):
        for mode in ("overlay", "modular"):
            with self.subTest(mode=mode), Database(mode=mode) as db:
                for table in ("lhs", "rhs"):
                    db.execute(
                        f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, k INTEGER NOT NULL, v INTEGER NOT NULL)"
                    )
                    db.execute(f"CREATE MATERIALIZED VIEW {table}bag AS SELECT k, v FROM {table}")
                query = (
                    "SELECT l.k, l.v FROM lhsbag AS l WHERE NOT EXISTS "
                    "(SELECT * FROM rhsbag AS r WHERE r.k = l.k)"
                )
                db.execute("CREATE MATERIALIZED VIEW missing AS " + query)
                db.execute(
                    "CREATE MATERIALIZED VIEW totals AS SELECT k, SUM(v) AS total, COUNT(*) AS n "
                    "FROM missing GROUP BY k"
                )
                rng = random.Random(942718)
                state = {"lhs": {}, "rhs": {}}

                def verify(expected, db=db, query=query):
                    for name in ("lhs", "rhs"):
                        self.assertEqual(
                            Counter(db.execute(f"SELECT * FROM {name}").rows),
                            Counter(expected[name].values()),
                        )
                        self.assertEqual(
                            Counter(db.execute(f"SELECT * FROM {name}bag").rows),
                            Counter((k, v) for _, k, v in expected[name].values()),
                        )
                    right_keys = {k for _, k, _ in expected["rhs"].values()}
                    missing = [
                        (k, v) for _, k, v in expected["lhs"].values() if k not in right_keys
                    ]
                    self.assertEqual(
                        Counter(db.execute("SELECT * FROM missing").rows), Counter(missing)
                    )
                    self.assertEqual(Counter(db.execute(query).rows), Counter(missing))
                    groups = {}
                    for k, v in missing:
                        total, count = groups.get(k, (0, 0))
                        groups[k] = (total + v, count + 1)
                    self.assertEqual(
                        Counter(db.execute("SELECT * FROM totals").rows),
                        Counter((k, total, count) for k, (total, count) in groups.items()),
                    )

                for transaction in range(40):
                    working = {name: dict(rows) for name, rows in state.items()}
                    db.execute("BEGIN")
                    for _ in range(8):
                        name = rng.choice(("lhs", "rhs"))
                        key = rng.randrange(16)
                        rows = working[name]
                        if key not in rows:
                            row = (key, rng.randrange(4), rng.randrange(-2, 3))
                            db.execute(f"INSERT INTO {name} VALUES (?, ?, ?)", row)
                            rows[key] = row
                        elif rng.random() < 0.35:
                            db.execute(f"DELETE FROM {name} WHERE id = ?", (key,))
                            del rows[key]
                        else:
                            row = (key, rng.randrange(4), rng.randrange(-2, 3))
                            db.execute(
                                f"UPDATE {name} SET k = ?, v = ? WHERE id = ?", (*row[1:], key)
                            )
                            rows[key] = row
                        verify(working)
                    if transaction % 4 == 0:
                        db.execute("ROLLBACK")
                    else:
                        db.execute("COMMIT")
                        state = working
                    verify(state)


if __name__ == "__main__":
    unittest.main()
