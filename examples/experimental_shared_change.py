"""Inspect, publish or discard a native reservation change in an isolated research process.

Build the drivers with research/shared-change/run.py first. This is not the installed
refpot API and creates no durable database. No model provider or package installation.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/application-model"))
from models import insert, resource_spec  # noqa: E402
from native_model import ModelError, NativeModel, mutation_command  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--driver", type=Path, required=True)
    parser.add_argument("--units", type=int, default=4)
    parser.add_argument("--publish", action="store_true", help="otherwise discard the candidate")
    args = parser.parse_args()
    with NativeModel(args.driver.resolve(), resource_spec()) as db:
        db.apply([insert("resources", 1, 10), insert("teams", 2, 10)])
        before, epoch = db.snapshot(), db.epoch
        print("Committed capacity:", before["resource_remaining"])
        db.request("BEGIN")
        db.request(mutation_command(insert("reservations", 3, 1, 2, args.units)))
        try:
            db.request("PREPARE")
        except ModelError as error:
            assert db.snapshot() == before and db.epoch == epoch
            print("Rejected without committed changes:", error)
            return 1
        candidate = db.request("PREVIEW")["tables"]
        print("Candidate capacity:", candidate["resource_remaining"])
        assert db.snapshot() == before and db.epoch == epoch
        print("Ordinary committed reads remain unchanged before publication.")
        db.request("PUBLISH" if args.publish else "ABORT")
        assert db.snapshot() == (candidate if args.publish else before)
        assert db.epoch == epoch + int(args.publish)
        print("Published." if args.publish else "Discarded.")
        print("Final capacity:", db.snapshot()["resource_remaining"])
        if args.publish:
            print("Native transaction work counters:", json.dumps(db.stats, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
