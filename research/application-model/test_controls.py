import sqlite3
import unittest

from oracle import Oracle
from sqlite_control import SQLiteControl

LIMIT = (1 << 63) - 1


def resource_spec():
    return {
        "nodes": [
            {"name": "teams", "op": "source", "width": 1},
            {"name": "resources", "op": "source", "width": 2},
            {"name": "reservations", "op": "source", "width": 3},
            {
                "name": "reservation_team",
                "op": "map",
                "input": "reservations",
                "exprs": [["c0"], ["c2"], ["c1"]],
            },
            {
                "name": "valid",
                "op": "join",
                "left": "reservation_team",
                "right": "teams",
                "left_key": 2,
                "right_key": 0,
            },
            {
                "name": "missing",
                "op": "anti",
                "left": "reservation_team",
                "right": "teams",
                "left_key": 2,
                "right_key": 0,
            },
            {"name": "usage", "op": "group", "input": "valid", "key": 0, "value": 1},
            {
                "name": "over",
                "op": "filter",
                "input": "usage",
                "column": 1,
                "cmp": "gt",
                "value": 10,
            },
            {"name": "all_resources", "op": "union", "left": "resources", "right": "resources"},
        ],
        "required_empty": ["missing", "over"],
    }


def pricing_spec():
    return {
        "nodes": [
            {"name": "orders", "op": "source", "width": 2},
            {"name": "prices", "op": "source", "width": 2},
            {
                "name": "lines",
                "op": "join",
                "left": "orders",
                "right": "prices",
                "left_key": 1,
                "right_key": 0,
            },
            {
                "name": "extended",
                "op": "map",
                "input": "lines",
                "exprs": [["c0"], ["c2", 2, "*"], ["c3"]],
            },
            {"name": "totals", "op": "group", "input": "extended", "key": 0, "value": 1},
            {
                "name": "positive",
                "op": "filter",
                "input": "totals",
                "column": 1,
                "cmp": "gt",
                "value": 0,
            },
        ],
        "required_empty": [],
    }


class ControlContract(unittest.TestCase):
    implementations = (Oracle, SQLiteControl)

    def test_resource_constraints_allow_final_state_repairs_and_rollback(self):
        for cls in self.implementations:
            with self.subTest(control=cls.__name__):
                db = cls(resource_spec())
                db.apply(
                    [
                        {"op": "insert", "table": "reservations", "row": [1, 7, 6]},
                        {"op": "insert", "table": "teams", "row": [7]},
                    ]
                )
                self.assertEqual(db.snapshot()["usage"], [[1, 6, 1, 1]])
                before = db.snapshot()
                epoch = db.epoch
                with self.assertRaises((ValueError, OverflowError, sqlite3.Error)):
                    db.apply([{"op": "insert", "table": "reservations", "row": [2, 8, 1]}])
                self.assertEqual(db.snapshot(), before)
                self.assertEqual(db.epoch, epoch)
                db.apply(
                    [
                        {"op": "insert", "table": "reservations", "row": [2, 7, 5]},
                        {"op": "delete", "table": "reservations", "key": 1},
                    ]
                )
                self.assertEqual(db.snapshot()["usage"], [[2, 5, 1, 1]])
                db.apply([])
                self.assertEqual(db.epoch, epoch + 2)
                db.close()

    def test_duplicate_join_rows_and_group_disappearance(self):
        for cls in self.implementations:
            db = cls(pricing_spec())
            db.apply(
                [
                    {"op": "insert", "table": "prices", "row": [9, 3]},
                    {"op": "insert", "table": "orders", "row": [1, 9]},
                    {"op": "insert", "table": "orders", "row": [2, 9]},
                ]
            )
            self.assertEqual(db.snapshot()["lines"], [[1, 9, 9, 3, 1], [2, 9, 9, 3, 1]])
            self.assertEqual(db.snapshot()["totals"], [[1, 18, 1, 1], [2, 18, 1, 1]])
            db.apply(
                [
                    {"op": "delete", "table": "orders", "key": 1},
                    {"op": "delete", "table": "orders", "key": 2},
                ]
            )
            self.assertEqual(db.snapshot()["totals"], [])
            db.close()

    def test_strict_int64_and_atomic_arithmetic_overflow(self):
        for cls in self.implementations:
            db = cls(
                {
                    "nodes": [
                        {"name": "src", "op": "source", "width": 1},
                        {"name": "mapped", "op": "map", "input": "src", "exprs": [["c0", 2, "*"]]},
                    ],
                    "required_empty": [],
                }
            )
            for invalid in (True, 1.0, "1", 1 << 63, -(1 << 63) - 1):
                with self.assertRaises((ValueError, OverflowError, sqlite3.Error)):
                    db.apply([{"op": "insert", "table": "src", "row": [invalid]}])
                self.assertEqual(db.snapshot()["src"], [])
                self.assertEqual(db.epoch, 0)
            with self.assertRaises((ValueError, OverflowError, sqlite3.Error)):
                db.apply([{"op": "insert", "table": "src", "row": [LIMIT]}])
            self.assertEqual(db.snapshot()["src"], [])
            self.assertEqual(db.epoch, 0)
            db.close()

    def test_empty_group_and_unreferenced_overflow_are_evaluated(self):
        spec = {
            "nodes": [
                {"name": "src", "op": "source", "width": 1},
                {"name": "groups", "op": "group", "input": "src", "key": 0, "value": 0},
                {"name": "latent", "op": "map", "input": "src", "exprs": [["c0", 2, "*"]]},
            ],
            "required_empty": [],
        }
        for cls in self.implementations:
            db = cls(spec)
            self.assertEqual(db.snapshot()["groups"], [])
            with self.assertRaises((ValueError, OverflowError, sqlite3.Error)):
                db.apply([{"op": "insert", "table": "src", "row": [LIMIT]}])
            self.assertEqual(db.epoch, 0)
            db.close()

    def test_self_join_and_update_delete(self):
        spec = {
            "nodes": [
                {"name": "edges", "op": "source", "width": 2},
                {
                    "name": "walks",
                    "op": "join",
                    "left": "edges",
                    "right": "edges",
                    "left_key": 1,
                    "right_key": 0,
                },
            ],
            "required_empty": [],
        }
        for cls in self.implementations:
            db = cls(spec)
            db.apply(
                [
                    {"op": "insert", "table": "edges", "row": [1, 2]},
                    {"op": "insert", "table": "edges", "row": [2, 3]},
                ]
            )
            self.assertEqual(db.snapshot()["walks"], [[1, 2, 2, 3, 1]])
            db.apply([{"op": "update", "table": "edges", "row": [2, 4]}])
            self.assertEqual(db.snapshot()["walks"], [[1, 2, 2, 4, 1]])
            db.apply([{"op": "delete", "table": "edges", "key": 2}])
            self.assertEqual(db.snapshot()["edges"], [[1, 2, 1]])
            db.close()

    def test_construction_rejects_bad_graphs(self):
        bad = [
            {
                "nodes": [
                    {"name": "x", "op": "source", "width": 1},
                    {"name": "x", "op": "source", "width": 1},
                ],
                "required_empty": [],
            },
            {
                "nodes": [
                    {"name": "x", "op": "source", "width": 1},
                    {"name": "y", "op": "map", "input": "x", "exprs": [["c2"]]},
                ],
                "required_empty": [],
            },
            {
                "nodes": [
                    {"name": "x", "op": "source", "width": 1},
                    {
                        "name": "y",
                        "op": "join",
                        "left": "x",
                        "right": "missing",
                        "left_key": 0,
                        "right_key": 0,
                    },
                ],
                "required_empty": [],
            },
        ]
        for cls in self.implementations:
            for spec in bad:
                with self.assertRaises((ValueError, OverflowError, sqlite3.Error)):
                    cls(spec)

    def test_single_column_update_and_wide_group_overflow_rollback(self):
        spec = {
            "nodes": [
                {"name": "values", "op": "source", "width": 3},
                {"name": "sum", "op": "group", "input": "values", "key": 1, "value": 2},
            ],
            "required_empty": [],
        }
        for cls in self.implementations:
            db = cls(spec)
            db.apply([{"op": "insert", "table": "values", "row": [1, 7, LIMIT]}])
            epoch, before = db.epoch, db.snapshot()
            with self.assertRaises((ValueError, OverflowError, sqlite3.Error)):
                db.apply([{"op": "insert", "table": "values", "row": [2, 7, 1]}])
            self.assertEqual(db.snapshot(), before)
            self.assertEqual(db.epoch, epoch)
            one_column = cls(
                {"nodes": [{"name": "keys", "op": "source", "width": 1}], "required_empty": []}
            )
            one_column.apply([{"op": "insert", "table": "keys", "row": [4]}])
            one_column.apply([{"op": "update", "table": "keys", "row": [4]}])
            self.assertEqual(one_column.snapshot()["keys"], [[4, 1]])
            db.close()
            one_column.close()

    def test_sql_view_bags_coalesce_duplicate_rows(self):
        spec = {
            "nodes": [
                {"name": "src", "op": "source", "width": 2},
                {"name": "twice", "op": "union", "left": "src", "right": "src"},
                {"name": "collapsed", "op": "map", "input": "twice", "exprs": [["c0"], ["c1"]]},
            ],
            "required_empty": [],
        }
        for cls in self.implementations:
            db = cls(spec)
            db.apply([{"op": "insert", "table": "src", "row": [1, 8]}])
            self.assertEqual(db.snapshot()["twice"], [[1, 8, 2]])
            self.assertEqual(db.snapshot()["collapsed"], [[1, 8, 2]])
            db.close()


if __name__ == "__main__":
    unittest.main()
