"""End-to-end native/SQLite/recompute qualification, without installing a package."""

import os
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/application-model"))

from models import delete, insert, pricing_spec, resource_spec, update  # noqa: E402
from native_model import ModelError, NativeModel, build_driver  # noqa: E402
from oracle import Oracle  # noqa: E402
from sqlite_control import SQLiteControl  # noqa: E402


class ApplicationModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix="refpot-model-tests-")
        cls.binary = os.environ.get("REFPOT_MODEL_DRIVER") or build_driver(
            Path(cls.workspace.name) / "model-driver"
        )

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def start(self, spec):
        engines = [Oracle(spec), SQLiteControl(spec), NativeModel(self.binary, spec)]
        for engine in engines:
            if hasattr(engine, "close"):
                self.addCleanup(engine.close)
        self.assertEqual(engines[0].snapshot(), engines[1].snapshot())
        self.assertEqual(engines[0].snapshot(), engines[2].snapshot())
        return engines

    def apply_all(self, engines, ops, *, accepted=None):
        old = [(engine.epoch, engine.snapshot()) for engine in engines]
        outcomes = []
        for engine in engines:
            try:
                engine.apply(ops)
                outcomes.append(True)
            except (ValueError, OverflowError, sqlite3.Error):
                outcomes.append(False)
        self.assertEqual(outcomes, [outcomes[0]] * len(engines), (ops, outcomes))
        if accepted is not None:
            self.assertEqual(outcomes[0], accepted, ops)
        current = [(engine.epoch, engine.snapshot()) for engine in engines]
        self.assertEqual(current, [current[0]] * len(engines), ops)
        if not outcomes[0]:
            self.assertEqual(current, old, ops)
        return current[0][1]

    def test_control_and_transport_suites(self):
        subprocess.run(
            [sys.executable, "-m", "unittest", "-v", "test_controls", "test_transport"],
            cwd=ROOT / "research/application-model",
            check=True,
            timeout=90,
        )

    def test_native_unit_and_allocation_suite(self):
        compiler = os.environ.get("CXX") or shutil.which("clang++") or shutil.which("c++")
        self.assertIsNotNone(compiler)
        binary = Path(self.workspace.name) / "native-tests"
        subprocess.run(
            [
                str(compiler),
                "-std=c++17",
                "-O1",
                "-g",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(ROOT / "tests/native/test_model.cpp"),
                "-o",
                str(binary),
            ],
            check=True,
            timeout=120,
        )
        subprocess.run([str(binary)], check=True, timeout=90)

    def test_resource_model_updates_deletes_and_final_state_repair(self):
        engines = self.start(resource_spec())
        self.apply_all(engines, [insert("resources", 1, 10), insert("teams", 1, 12)], accepted=True)
        state = self.apply_all(engines, [insert("reservations", 1, 1, 1, 6)], accepted=True)
        self.assertEqual(state["resource_remaining"], [[1, 4, 1]])
        self.assertEqual(state["team_remaining"], [[1, 6, 1]])
        self.apply_all(engines, [insert("reservations", 2, 1, 1, 5)], accepted=False)
        # Statement one temporarily overbooks; final combined state is valid.
        state = self.apply_all(
            engines,
            [insert("reservations", 2, 1, 1, 5), update("reservations", 1, 1, 1, 4)],
            accepted=True,
        )
        self.assertEqual(state["resource_remaining"], [[1, 1, 1]])
        self.apply_all(engines, [delete("resources", 1)], accepted=False)
        self.apply_all(engines, [insert("reservations", 9, 999, 1, 1)], accepted=False)
        state = self.apply_all(
            engines, [delete("reservations", 1), delete("reservations", 2)], accepted=True
        )
        self.assertEqual(state["resource_remaining"], [[1, 10, 1]])
        self.assertEqual(state["reservations"], [])

    def test_pricing_model_reprices_both_sides_and_rejects_entire_batch(self):
        engines = self.start(pricing_spec())
        state = self.apply_all(
            engines,
            [insert("customers", 1, 100), insert("products", 1, 7), insert("orders", 1, 1, 1, 3)],
            accepted=True,
        )
        self.assertEqual(state["line_totals"], [[1, 1, 21, 1]])
        state = self.apply_all(
            engines, [update("products", 1, 9), update("orders", 1, 1, 1, 4)], accepted=True
        )
        self.assertEqual(state["customer_remaining"], [[1, 64, 1]])
        self.apply_all(
            engines, [insert("products", 2, 1), update("products", 1, 30)], accepted=False
        )
        self.apply_all(engines, [update("products", 1, (1 << 63) - 1)], accepted=False)
        self.apply_all(engines, [delete("orders", 1), delete("products", 1)], accepted=True)

    def test_self_join_bag_multiplicities_and_absence(self):
        spec = {
            "nodes": [
                {"name": "src", "op": "source", "width": 2},
                {"name": "keys", "op": "map", "input": "src", "exprs": [["c1"]]},
                {
                    "name": "pairs",
                    "op": "join",
                    "left": "keys",
                    "right": "keys",
                    "left_key": 0,
                    "right_key": 0,
                },
                {
                    "name": "absent",
                    "op": "anti",
                    "left": "src",
                    "right": "keys",
                    "left_key": 0,
                    "right_key": 0,
                },
                {"name": "total", "op": "group", "input": "src", "key": 1, "value": 0},
            ]
        }
        engines = self.start(spec)
        state = self.apply_all(engines, [insert("src", 1, 7), insert("src", 2, 7)], accepted=True)
        self.assertEqual(state["pairs"], [[7, 7, 4]])
        state = self.apply_all(engines, [update("src", 1, 9), delete("src", 2)], accepted=True)
        self.assertEqual(state["pairs"], [[9, 9, 1]])
        state = self.apply_all(engines, [delete("src", 1)], accepted=True)
        self.assertEqual(state["pairs"], [])
        self.assertEqual(state["total"], [])

    def test_group_final_fit_and_map_operation_overflow(self):
        spec = {
            "nodes": [
                {"name": "src", "op": "source", "width": 3},
                {"name": "total", "op": "group", "input": "src", "key": 1, "value": 2},
            ]
        }
        engines = self.start(spec)
        maximum = (1 << 63) - 1
        state = self.apply_all(
            engines,
            [
                insert("src", 1, 0, maximum),
                insert("src", 2, 0, maximum),
                insert("src", 3, 0, -maximum),
            ],
            accepted=True,
        )
        self.assertEqual(state["total"], [[0, maximum, 3, 1]])
        self.apply_all(engines, [delete("src", 3)], accepted=False)
        self.apply_all(
            engines, [update("src", 1, 0, -maximum), update("src", 3, 0, maximum)], accepted=True
        )

    def test_definition_ownership_and_canonical_column_tokens(self):
        spec = {
            "nodes": [
                {"name": "src", "op": "source", "width": 2},
                {"name": "copy", "op": "map", "input": "src", "exprs": [["c00"]]},
            ]
        }
        engines = self.start(spec)
        self.apply_all(engines, [insert("src", 1, 10)], accepted=True)
        spec["nodes"][1]["exprs"][0][0] = "c1"
        state = self.apply_all(engines, [insert("src", 2, 20)], accepted=True)
        self.assertEqual(state["copy"], [[1, 1], [2, 1]])

    def test_unchanged_result_stops_downstream_execution(self):
        spec = {
            "nodes": [
                {"name": "src", "op": "source", "width": 2},
                {"name": "key_only", "op": "map", "input": "src", "exprs": [["c0"]]},
                {"name": "shared", "op": "union", "left": "key_only", "right": "key_only"},
            ]
        }
        with NativeModel(self.binary, spec) as model:
            model.apply([insert("src", 1, 2)])
            model.apply([update("src", 1, 3)])
            self.assertEqual(model.snapshot()["shared"], [[1, 2]])
            self.assertEqual(model.stats["derived_nodes"], 1)
            self.assertGreater(model.stats["copied_rows"], 0)

    def test_context_exception_and_malformed_requests_preserve_committed_state(self):
        with NativeModel(self.binary, resource_spec()) as model:
            with model.transaction() as tx:
                tx.insert("resources", 1, 10)
                tx.insert("teams", 1, 20)
            before = model.snapshot()
            with self.assertRaisesRegex(RuntimeError, "cancel"), model.transaction() as tx:
                tx.insert("reservations", 1, 1, 1, 3)
                raise RuntimeError("cancel")
            self.assertEqual(model.snapshot(), before)
            for command in ["BEGIN extra", "SNAPSHOT trailing", "DEF source x 1", "unknown"]:
                with self.assertRaises(ModelError):
                    model.request(command)
                self.assertEqual(model.snapshot(), before)
            with self.assertRaises(ValueError):
                model.apply([insert("resources", 2, True)])
            self.assertEqual(model.snapshot(), before)
            with model.transaction() as tx:
                tx.insert("reservations", 1, 1, 1, 3)
            self.assertEqual(model.snapshot()["resource_remaining"], [[1, 7, 1]])

    def test_protocol_errors_abort_the_whole_active_batch(self):
        spec = {"nodes": [{"name": "s", "op": "source", "width": 1}]}
        with NativeModel(self.binary, spec) as model:
            for malformed in [
                "INSERT s 1 8 trailing",
                "INSERT s 1",
                "DELETE s nope",
                "COMMIT trailing",
                "SNAPSHOT trailing",
                "BEGIN",
                "unknown",
            ]:
                with self.subTest(command=malformed):
                    before = model.snapshot()
                    epoch = model.epoch
                    model.request("BEGIN")
                    model.request("INSERT s 1 7")
                    with self.assertRaises(ModelError):
                        model.request(malformed)
                    with self.assertRaises(ModelError):
                        model.request("COMMIT")
                    self.assertEqual(model.snapshot(), before)
                    self.assertEqual(model.epoch, epoch)
            model.apply([insert("s", 9)])
            self.assertEqual(model.snapshot()["s"], [[9, 1]])

    def test_seeded_mutations_match_every_relation_after_every_batch(self):
        for domain, make_spec in [("resource", resource_spec), ("pricing", pricing_spec)]:
            for seed in range(4):
                with self.subTest(domain=domain, seed=seed):
                    engines = self.start(make_spec())
                    rng = random.Random(seed)
                    if domain == "resource":
                        parents, children = ("resources", "teams"), "reservations"
                        setup = [insert(p, k, 40) for p in parents for k in range(3)]
                    else:
                        parents, children = ("customers", "products"), "orders"
                        setup = [
                            insert(p, k, 40 if p == "customers" else 3)
                            for p in parents
                            for k in range(3)
                        ]
                    self.apply_all(engines, setup, accepted=True)
                    for _ in range(80):
                        batch = []
                        for _ in range(rng.randint(1, 3)):
                            if rng.randrange(4) == 0:
                                table = rng.choice(parents)
                                kind = rng.choice(["insert", "update", "delete"])
                                key = rng.randrange(4)
                                batch.append(
                                    delete(table, key)
                                    if kind == "delete"
                                    else {
                                        "op": kind,
                                        "table": table,
                                        "row": [key, rng.randrange(-1, 50)],
                                    }
                                )
                            else:
                                kind = rng.choice(["insert", "insert", "update", "delete"])
                                key = rng.randrange(12)
                                batch.append(
                                    delete(children, key)
                                    if kind == "delete"
                                    else {
                                        "op": kind,
                                        "table": children,
                                        "row": [
                                            key,
                                            rng.randrange(4),
                                            rng.randrange(4),
                                            rng.randrange(-1, 15),
                                        ],
                                    }
                                )
                        self.apply_all(engines, batch)
                    for engine in engines:
                        if hasattr(engine, "close"):
                            engine.close()


if __name__ == "__main__":
    unittest.main()
