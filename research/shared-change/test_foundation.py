"""Independent end-to-end tests of the experimental native transaction boundary."""

import os
import sqlite3
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research/application-model"))
from cases import DOMAINS, sequence  # noqa: E402
from models import insert, resource_spec, update  # noqa: E402
from native_model import ModelError, NativeModel, mutation_command  # noqa: E402
from oracle import Oracle  # noqa: E402
from sqlite_control import SQLiteControl  # noqa: E402

ERRORS = (ValueError, OverflowError, sqlite3.Error)


class FoundationContract(unittest.TestCase):
    def binaries(self):
        paths = os.environ.get("REFPOT_FOUNDATION_DRIVERS", "").split(os.pathsep)
        self.assertTrue(all(paths), "set REFPOT_FOUNDATION_DRIVERS to compiled native drivers")
        return paths

    def test_seeded_full_state_against_independent_controls(self):
        outcomes = {"accepted": 0, "rejected": 0}
        for domain in DOMAINS:
            for seed in range(4):
                with self.subTest(domain=domain, seed=seed), ExitStack() as stack:
                    spec, initial, batches = sequence(domain, seed)
                    oracle = Oracle(spec)
                    sql = SQLiteControl(spec)
                    stack.callback(sql.close)
                    natives = [
                        stack.enter_context(NativeModel(path, spec)) for path in self.binaries()
                    ]
                    engines = [oracle, sql, *natives]
                    for engine in engines:
                        engine.apply(initial)
                    for batch in batches:
                        accepted = []
                        for engine in engines:
                            try:
                                engine.apply(batch)
                                accepted.append(True)
                            except ERRORS:
                                accepted.append(False)
                        self.assertEqual(accepted, [accepted[0]] * len(engines), batch)
                        outcomes["accepted" if accepted[0] else "rejected"] += 1
                        expected = oracle.snapshot()
                        for engine in engines[1:]:
                            self.assertEqual(engine.snapshot(), expected, batch)
                            self.assertEqual(engine.epoch, oracle.epoch, batch)
        self.assertGreater(outcomes["accepted"], 0)
        self.assertGreater(outcomes["rejected"], 0)
        print("Seeded full-state transaction outcomes:", outcomes)

    def test_unchanged_expression_stops_downstream_work(self):
        spec = {
            "nodes": [
                {"name": "src", "op": "source", "width": 2},
                {"name": "keys", "op": "map", "input": "src", "exprs": [["c0"]]},
                {"name": "shared", "op": "union", "left": "keys", "right": "keys"},
            ]
        }
        for binary in self.binaries():
            with NativeModel(binary, spec) as model:
                model.apply([insert("src", 1, 2)])
                model.apply([update("src", 1, 3)])
                self.assertEqual(model.snapshot()["shared"], [[1, 2]])
                self.assertEqual(model.stats["derived_nodes"], 1)

    def test_existing_semantic_contract_in_both_native_modes(self):
        from test_controls import ControlContract

        for binary in self.binaries():

            class NativeContract(ControlContract):
                implementations = (lambda spec, binary=binary: NativeModel(binary, spec),)

            result = unittest.TestResult()
            unittest.defaultTestLoader.loadTestsFromTestCase(NativeContract).run(result)
            self.assertEqual(result.errors, [], result.errors)
            self.assertEqual(result.failures, [], result.failures)
            print("Inherited semantic controls:", Path(binary).name, result.testsRun)

    def test_abort_and_bad_request_cannot_publish_prepared_effects(self):
        for binary in self.binaries():
            for bad_request in ("ABORT", "PREVIEW extra", "PUBLISH extra", "BEGIN"):
                with (
                    self.subTest(binary=binary, request=bad_request),
                    NativeModel(binary, resource_spec()) as model,
                ):
                    model.apply([insert("resources", 1, 10), insert("teams", 2, 10)])
                    before, epoch = model.snapshot(), model.epoch
                    model.request("BEGIN")
                    model.request(mutation_command(insert("reservations", 3, 1, 2, 4)))
                    model.request("PREPARE")
                    if bad_request == "ABORT":
                        model.request(bad_request)
                    else:
                        with self.assertRaises(ModelError):
                            model.request(bad_request)
                    with self.assertRaises(ModelError):
                        model.request("PUBLISH")
                    self.assertEqual(model.snapshot(), before)
                    self.assertEqual(model.epoch, epoch)
                    model.apply([insert("reservations", 4, 1, 2, 2)])
                    self.assertEqual(model.snapshot()["resource_remaining"], [[1, 8, 1]])

    def test_prepared_read_is_private_until_explicit_publish(self):
        for binary in self.binaries():
            with self.subTest(binary=binary), NativeModel(binary, resource_spec()) as model:
                model.apply([insert("resources", 1, 10), insert("teams", 2, 10)])
                before, epoch = model.snapshot(), model.epoch
                model.request("BEGIN")
                model.request(mutation_command(insert("reservations", 3, 1, 2, 4)))
                error = None
                try:
                    model.request("PREPARE")
                except ModelError as exc:
                    error = str(exc)
                self.assertIsNone(error, f"native prepare must support private queries: {error}")
                preview = model.request("PREVIEW")["tables"]
                self.assertEqual(preview["resource_remaining"], [[1, 6, 1]])
                self.assertEqual(model.snapshot(), before)
                self.assertEqual(model.epoch, epoch)
                model.request("PUBLISH")
                self.assertEqual(model.snapshot(), preview)
                self.assertEqual(model.epoch, epoch + 1)


if __name__ == "__main__":
    unittest.main()
