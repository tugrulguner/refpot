#!/usr/bin/env python3
"""Explicit candidate adapter; parent supplies an installed candidate Python."""
import argparse
import json
import sys
from pathlib import Path
from refpot.sql import Database

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from control import FIXTURES, expected_state, apply_op


def execute(db, sql, params=()):
    return db.execute(sql, params)


def fetch(db, sql):
    return [list(row) for row in execute(db, sql).rows]


def run_fixture(fixture, txns):
    records = []
    dims, facts = FIXTURES[fixture]["dimensions"], FIXTURES[fixture]["facts"]
    with Database() as db:
        execute(db, "CREATE TABLE dimension (id INTEGER PRIMARY KEY, ceiling INTEGER NOT NULL, rate INTEGER NOT NULL)")
        execute(db, "CREATE TABLE fact (id INTEGER PRIMARY KEY, dimension_id INTEGER NOT NULL REFERENCES dimension(id), amount INTEGER NOT NULL)")
        for row in dims: execute(db, "INSERT INTO dimension VALUES (?,?,?)", row)
        for row in facts: execute(db, "INSERT INTO fact VALUES (?,?,?)", row)
        execute(db, "CREATE MATERIALIZED VIEW maintained AS SELECT dimension_id AS dimension_id, SUM(amount*rate) AS total, COUNT(*) AS n FROM fact JOIN dimension ON dimension.id=fact.dimension_id GROUP BY dimension_id")
        execute(db, "CREATE MATERIALIZED VIEW joined_result AS SELECT fact.id AS fact_id, fact.dimension_id AS dimension_id, fact.amount AS amount, dimension.rate AS rate, fact.amount*dimension.rate AS extended FROM fact JOIN dimension ON dimension.id=fact.dimension_id")
        execute(db, "CREATE MATERIALIZED VIEW violations AS SELECT maintained.dimension_id AS dimension_id, maintained.total AS total, dimension.ceiling AS ceiling FROM maintained JOIN dimension ON dimension.id=maintained.dimension_id WHERE maintained.total>dimension.ceiling")
        execute(db, "CREATE ASSERTION capacity_or_price CHECK (NOT EXISTS (SELECT * FROM violations))")

        def verify(label):
            src = {"dimension": fetch(db, "SELECT id,ceiling,rate FROM dimension ORDER BY id"),
                   "fact": fetch(db, "SELECT id,dimension_id,amount FROM fact ORDER BY id")}
            expected = expected_state(src)
            # GROUP BY omits empty groups; normalize only this representation.
            expected["maintained"] = [row for row in expected["maintained"] if row[2] != 0]
            actual = {"maintained": fetch(db, "SELECT dimension_id,total,n FROM maintained ORDER BY dimension_id"),
                      "joined_result": fetch(db, "SELECT fact_id,dimension_id,amount,rate,extended FROM joined_result ORDER BY fact_id"),
                      "violations": fetch(db, "SELECT dimension_id,total,ceiling FROM violations ORDER BY dimension_id")}
            if actual != expected:
                raise AssertionError(f"candidate oracle mismatch {fixture} {label}: {actual!r} != {expected!r}")
            return src, actual

        verify("construction")
        counts = {"accepted": 0, "rejected": 0, "oracle_checks": 0}
        for i, txn in enumerate(txns):
            error = None
            try:
                if txn.get("outcome") == "rollback":
                    try:
                        with db.transaction():
                            for op in txn["ops"]: apply_op(db, op)
                            raise RuntimeError("planned rollback")
                    except RuntimeError as exc:
                        if str(exc) != "planned rollback": raise
                else:
                    with db.transaction():
                        for op in txn["ops"]: apply_op(db, op)
            except Exception as exc:
                error = str(exc)
            expected_reject = txn.get("outcome", "accept") == "reject"
            if bool(error) != expected_reject:
                raise AssertionError(f"{fixture} txn {i}: expected reject={expected_reject}, got {error!r}")
            counts["rejected" if error else "accepted"] += 1
            src, derived = verify(f"txn-{i}")
            counts["oracle_checks"] += 1
        src, derived = verify("final")
        records.append({"fixture": fixture, "stats": counts, "source_rows": src, "derived_rows": derived})
    return records[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text())
    records = [run_fixture(fixture, plan["workloads"][fixture]) for fixture in plan["fixtures"]]
    print(json.dumps({"format": "maintained-sql-candidate-functional-v1", "python": sys.executable,
                      "records": records}, indent=2, sort_keys=True))


if __name__ == "__main__": main()
