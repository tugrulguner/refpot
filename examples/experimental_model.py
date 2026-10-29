"""Run the volatile native model slice; requires Python 3.11+ and a C++17 compiler.

Run from any directory: python /path/to/refpot/examples/experimental_model.py
No installed refpot package, model provider, service or third-party Python dependency.
This is not the shipped Database API and does not persist data across runs.
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/application-model"))

from models import pricing_spec, resource_spec  # noqa: E402
from native_model import ModelError, NativeModel, build_driver  # noqa: E402


def main():
    with tempfile.TemporaryDirectory(prefix="refpot-model-demo-") as directory:
        binary = build_driver(Path(directory) / "model-driver")
        with NativeModel(binary, resource_spec()) as db:
            with db.transaction() as tx:
                tx.insert("resources", 1, 10)
                tx.insert("teams", 1, 12)
                tx.insert("reservations", 101, 1, 1, 6)
            print("Reserved 6 of 10; available:", db.snapshot()["resource_remaining"])
            assert db.snapshot()["resource_remaining"] == [[1, 4, 1]]
            before = db.snapshot()
            epoch = db.epoch
            try:
                with db.transaction() as tx:
                    tx.insert("reservations", 102, 1, 1, 5)
            except ModelError as error:
                print("Overbooking rejected:", error)
            else:
                raise AssertionError("overbooking unexpectedly committed")
            assert db.snapshot() == before and db.epoch == epoch
            with db.transaction() as tx:
                tx.insert("reservations", 102, 1, 1, 5)
                tx.update("reservations", 101, 1, 1, 4)
            assert db.snapshot()["resource_remaining"] == [[1, 1, 1]]
            print("Final-state batch accepted; available:", db.snapshot()["resource_remaining"])
            with db.transaction() as tx:
                tx.delete("reservations", 101)
                tx.delete("reservations", 102)
            assert db.snapshot()["resource_remaining"] == [[1, 10, 1]]
            print("Deleted reservations; capacity restored:", db.snapshot()["resource_remaining"])
            print("Last native maintenance counters:", db.stats)
        with NativeModel(binary, pricing_spec()) as db:
            with db.transaction() as tx:
                tx.insert("customers", 1, 100)
                tx.insert("products", 7, 8)
                tx.insert("orders", 20, 1, 7, 3)
            assert db.snapshot()["line_totals"] == [[20, 1, 24, 1]]
            with db.transaction() as tx:
                tx.update("products", 7, 10)
            assert db.snapshot()["line_totals"] == [[20, 1, 30, 1]]
            print("Same operators, pricing model; repriced line:", db.snapshot()["line_totals"])
        print(
            "Verified: native maintenance, atomic rejection, final-state repair, deletion and repricing."
        )
        print(
            "Experimental only: volatile, single-threaded, whole-state candidate copies; no agents yet."
        )


if __name__ == "__main__":
    main()
