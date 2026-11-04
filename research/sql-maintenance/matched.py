#!/usr/bin/env python3
"""Exact-state comparison against SQLite trigger maintenance, not a speed test."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAN = HERE / "workload-v2.json"
TABLES = ("dimension", "fact", "maintained", "joined_result", "violations", "projected")
VIEWS = {
    "joined_result": "SELECT f.id AS fact_id, f.dimension_id AS dimension_id, f.amount AS amount, d.rate AS rate, d.ceiling AS ceiling FROM fact AS f JOIN dimension AS d ON f.dimension_id = d.id",
    "violations": "SELECT m.dimension_id AS dimension_id, m.total AS total, d.ceiling AS ceiling FROM maintained AS m JOIN dimension AS d ON m.dimension_id = d.id WHERE m.total > d.ceiling",
    "projected": "SELECT dimension_id, amount FROM fact",
}


def initial(fixture):
    return {name: {row[0]: list(row) for row in fixture[name]} for name in ("dimension", "fact")}


def oracle(state):
    """Derive everything from independently replayed source operations."""
    dims, facts = state["dimension"], state["fact"]
    groups = {}
    for _, key, amount in facts.values():
        group = groups.setdefault(key, [0, 0])
        group[0] += amount
        group[1] += 1
    return {
        "dimension": sorted(dims.values()),
        "fact": sorted(facts.values()),
        "maintained": sorted([key, *value] for key, value in groups.items()),
        "joined_result": sorted(
            [fid, key, amount, dims[key][2], dims[key][1]]
            for fid, key, amount in facts.values()
            if key in dims
        ),
        "violations": sorted(
            [key, value[0], dims[key][1]]
            for key, value in groups.items()
            if key in dims and value[0] > dims[key][1]
        ),
        "projected": sorted([key, amount] for _, key, amount in facts.values()),
    }


def replay_operation(state, op):
    action, table = op["op"].split("_", 1)
    rows, key = state[table], op["id"]
    if action == "delete":
        rows.pop(key, None)
        return False
    if action == "insert" and key in rows:
        return True
    if action == "update" and key not in rows:
        return False
    rows[key] = (
        [key, op["dimension"], op["amount"]]
        if table == "fact"
        else [key, op["ceiling"], op["rate"]]
    )
    return False


def sql_operation(op):
    action, table = op["op"].split("_", 1)
    if action == "delete":
        return f"DELETE FROM {table} WHERE id = ?", (op["id"],)
    values = (op["dimension"], op["amount"]) if table == "fact" else (op["ceiling"], op["rate"])
    if action == "insert":
        return f"INSERT INTO {table} VALUES (?, ?, ?)", (op["id"], *values)
    columns = "dimension_id = ?, amount = ?" if table == "fact" else "ceiling = ?, rate = ?"
    return f"UPDATE {table} SET {columns} WHERE id = ?", (*values, op["id"])


class Backend:
    def __init__(self, engine, mode, fixture, require_installed=False):
        self.engine = engine
        if engine == "sqlite":
            self.db = sqlite3.connect(":memory:", isolation_level=None)
            self.identity = {"sqlite": sqlite3.sqlite_version}
        else:
            import refpot
            import refpot._sql
            from refpot.sql import Database

            self.db = Database(mode=mode)
            extension = Path(refpot._sql.__file__).resolve()
            if require_installed:
                assert not extension.is_relative_to(HERE.parents[1]), (
                    "candidate must be installed outside the checkout"
                )
                assert not Path(refpot.__file__).resolve().is_relative_to(HERE.parents[1]), (
                    "source-tree Python package is not a qualified consumer"
                )
            self.identity = {
                "package": str(Path(refpot.__file__).resolve()),
                "extension": str(extension),
                "extension_sha256": hashlib.sha256(extension.read_bytes()).hexdigest(),
            }
        self.execute(
            "CREATE TABLE dimension (id INTEGER PRIMARY KEY, ceiling INTEGER NOT NULL, rate INTEGER NOT NULL)"
        )
        self.execute(
            "CREATE TABLE fact (id INTEGER PRIMARY KEY, dimension_id INTEGER NOT NULL, amount INTEGER NOT NULL)"
        )
        for name in ("dimension", "fact"):
            for row in fixture[name]:
                self.execute(f"INSERT INTO {name} VALUES (?, ?, ?)", row)
        if engine == "sqlite":
            self.db.executescript("""
                CREATE INDEX fact_dimension_idx ON fact(dimension_id);
                CREATE TABLE maintained (dimension_id INTEGER PRIMARY KEY, total INTEGER NOT NULL, n INTEGER NOT NULL);
                INSERT INTO maintained SELECT dimension_id, SUM(amount), COUNT(*) FROM fact GROUP BY dimension_id;
                CREATE TRIGGER fact_ai AFTER INSERT ON fact BEGIN
                    INSERT INTO maintained VALUES (NEW.dimension_id, NEW.amount, 1)
                    ON CONFLICT(dimension_id) DO UPDATE SET total=total+NEW.amount, n=n+1;
                END;
                CREATE TRIGGER fact_ad AFTER DELETE ON fact BEGIN
                    UPDATE maintained SET total=total-OLD.amount, n=n-1 WHERE dimension_id=OLD.dimension_id;
                    DELETE FROM maintained WHERE dimension_id=OLD.dimension_id AND n=0;
                END;
                CREATE TRIGGER fact_au AFTER UPDATE ON fact BEGIN
                    UPDATE maintained SET total=total-OLD.amount, n=n-1 WHERE dimension_id=OLD.dimension_id;
                    DELETE FROM maintained WHERE dimension_id=OLD.dimension_id AND n=0;
                    INSERT INTO maintained VALUES (NEW.dimension_id, NEW.amount, 1)
                    ON CONFLICT(dimension_id) DO UPDATE SET total=total+NEW.amount, n=n+1;
                END;
            """)
        else:
            self.execute(
                "CREATE MATERIALIZED VIEW maintained AS SELECT dimension_id, SUM(amount) AS total, COUNT(*) AS n FROM fact GROUP BY dimension_id"
            )
        for name, query in VIEWS.items():
            self.execute(
                f"CREATE {'MATERIALIZED ' if engine == 'native' else ''}VIEW {name} AS {query}"
            )
        if engine == "native":
            self.execute(
                "CREATE ASSERTION final_state CHECK (NOT EXISTS (SELECT * FROM violations))"
            )

    def execute(self, sql, params=()):
        try:
            return self.db.execute(sql, params)
        except sqlite3.Error:
            self.db.rollback()
            raise

    def read(self):
        result = {}
        for name in TABLES:
            rows = self.execute(f"SELECT * FROM {name}")
            result[name] = sorted(
                [list(row) for row in (rows.fetchall() if self.engine == "sqlite" else rows.rows)]
            )
        return result

    def commit(self):
        if self.engine == "sqlite" and self.execute("SELECT * FROM violations LIMIT 1").fetchone():
            self.db.rollback()
            raise ValueError("required-empty assertion violated")
        self.execute("COMMIT")

    def rollback(self):
        if self.engine == "sqlite":
            self.db.rollback()
        else:
            self.execute("ROLLBACK")

    def close(self):
        self.db.close()


def expected_history(fixture, transactions):
    state = initial(fixture)
    history = []
    for txn in transactions:
        working = copy.deepcopy(state)
        steps = []
        failed = False
        for op in txn["ops"]:
            failed = replay_operation(working, op)
            steps.append({"error": failed, "state": oracle(state if failed else working)})
            if failed:
                break
        outcome = txn.get("outcome", "accept")
        rejected = failed or (outcome != "rollback" and bool(oracle(working)["violations"]))
        if rejected != (outcome == "reject"):
            raise AssertionError(f"invalid frozen outcome: {txn['id']}")
        if not rejected and outcome != "rollback":
            state = working
        history.append(
            {"id": txn["id"], "outcome": outcome, "steps": steps, "state": oracle(state)}
        )
    return history


def run(engine, mode="overlay", mutant=None, require_installed=False):
    plan = json.loads(PLAN.read_text())
    records = []
    identity = None
    for name, fixture in plan["fixtures"].items():
        transactions = plan["workloads"][name]
        expected = expected_history(fixture, transactions)
        backend = Backend(engine, mode, fixture, require_installed)
        try:
            identity = backend.identity
            assert backend.read() == oracle(initial(fixture)), f"{name}: construction"
            history = []
            for txn, want in zip(transactions, expected, strict=True):
                backend.execute("BEGIN")
                steps = []
                ordinary_error = False
                for index, (op, expected_step) in enumerate(
                    zip(txn["ops"], want["steps"], strict=False)
                ):
                    error = None
                    try:
                        if not (mutant == "drop-operation" and index == 0):
                            backend.execute(*sql_operation(op))
                    except Exception as exc:
                        error = str(exc)
                    assert bool(error) == expected_step["error"], (
                        name,
                        txn["id"],
                        "unexpected statement outcome",
                        error,
                    )
                    if error:
                        assert "duplicate" in error.lower() or "unique" in error.lower(), error
                    actual = backend.read()
                    assert actual == expected_step["state"], (
                        name,
                        txn["id"],
                        index,
                        "statement state mismatch",
                        actual,
                        expected_step["state"],
                    )
                    steps.append({"error": bool(error), "state": actual})
                    if error:
                        ordinary_error = True
                        break
                if not ordinary_error:
                    if want["outcome"] == "rollback" and mutant != "commit-rollback":
                        backend.rollback()
                    else:
                        error = None
                        try:
                            backend.commit()
                        except Exception as exc:
                            error = str(exc)
                        assert bool(error) == (want["outcome"] == "reject"), (
                            name,
                            txn["id"],
                            "unexpected commit outcome",
                            error,
                        )
                        if error:
                            assert "required-empty" in error or "assertion" in error, error
                actual = backend.read()
                assert actual == want["state"], (
                    name,
                    txn["id"],
                    "final state mismatch",
                    actual,
                    want["state"],
                )
                history.append(
                    {"id": txn["id"], "outcome": want["outcome"], "steps": steps, "state": actual}
                )
            records.append({"fixture": name, "history": history})
        finally:
            backend.close()
    return {
        "format": "maintained-sql-matched-v2",
        "engine": engine,
        "mode": mode if engine == "native" else None,
        "plan_sha256": hashlib.sha256(PLAN.read_bytes()).hexdigest(),
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "identity": identity,
        "records": records,
    }


def validate(data):
    plan = json.loads(PLAN.read_text())
    assert data["plan_sha256"] == hashlib.sha256(PLAN.read_bytes()).hexdigest()
    assert data["harness_sha256"] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    assert [r["fixture"] for r in data["records"]] == list(plan["fixtures"])
    for record in data["records"]:
        name = record["fixture"]
        assert record["history"] == expected_history(
            plan["fixtures"][name], plan["workloads"][name]
        )
    return sum(len(r["history"]) for r in data["records"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("sqlite", "native"), default="sqlite")
    parser.add_argument("--mode", choices=("overlay", "modular"), default="overlay")
    parser.add_argument("--candidate-python")
    parser.add_argument("--require-installed", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.candidate_python:
        assert args.output is not None, "comparison requires a fresh --output directory"
        args.output.mkdir(parents=True, exist_ok=False)
        results = [run("sqlite")]
        for mode in ("overlay", "modular"):
            proc = subprocess.run(
                [
                    args.candidate_python,
                    str(Path(__file__).resolve()),
                    "--engine",
                    "native",
                    "--mode",
                    mode,
                    "--require-installed",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            results.append(json.loads(proc.stdout))
        counts = {}
        for data in results:
            name = data["engine"] + ("-" + data["mode"] if data["mode"] else "")
            target = args.output / f"{name}.json"
            target.write_text(json.dumps(data, indent=2) + "\n")
            counts[name] = validate(json.loads(target.read_text()))
        assert results[0]["records"] == results[1]["records"] == results[2]["records"]
        print(
            json.dumps(
                {
                    "verified_transactions_per_engine": counts,
                    "output": str(args.output.resolve()),
                    "comparison": "exact source/derived rows at every statement and transaction; no timing claim",
                },
                indent=2,
            )
        )
    else:
        data = run(args.engine, args.mode, require_installed=args.require_installed)
        validate(data)
        print(json.dumps(data))


if __name__ == "__main__":
    main()
