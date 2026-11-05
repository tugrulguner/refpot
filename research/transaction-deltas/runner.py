#!/usr/bin/env python3
"""Independent full-state transaction replay with an absence-aware SQLite control.

Correctness is checked after each source statement and transaction boundary against
an oracle that replays operations from its own source dictionaries. Performance is
optional and separate; setup and validation are outside the service timer.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import resource
import sqlite3
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PLAN = {
    "format": "transaction-deltas-absence-v1",
    "fixture": {
        "dimension": [[1, 20, 2], [2, 30, 3], [3, 40, 5]],
        "fact": [[1, 1, 4], [2, 1, 4], [3, 2, 7], [4, 3, 2]],
    },
    "transactions": [
        {
            "id": "update-fact-and-group",
            "ops": [{"op": "update_fact", "id": 3, "dimension": 1, "amount": 9}],
        },
        {
            "id": "delete-and-reinsert-both-sides",
            "ops": [
                {"op": "delete_fact", "id": 4},
                {"op": "insert_fact", "id": 4, "dimension": 2, "amount": 2},
                {"op": "delete_dimension", "id": 3},
                {"op": "insert_dimension", "id": 3, "ceiling": 40, "rate": 5},
            ],
        },
        {
            "id": "dimension-delete-temporary-missing",
            "ops": [
                {"op": "delete_dimension", "id": 1},
                {"op": "insert_dimension", "id": 1, "ceiling": 20, "rate": 2},
            ],
        },
        {
            "id": "dimension-reinsert-repair",
            "ops": [{"op": "update_dimension", "id": 1, "ceiling": 25, "rate": 2}],
        },
        {
            "id": "missing-commit-rejected",
            "outcome": "reject",
            "ops": [{"op": "delete_dimension", "id": 2}],
        },
        {
            "id": "valid-row-rollback",
            "outcome": "rollback",
            "ops": [
                {"op": "update_fact", "id": 1, "dimension": 2, "amount": 5},
            ],
        },
        {
            "id": "missing-row-rollback",
            "outcome": "rollback",
            "ops": [
                {"op": "delete_dimension", "id": 2},
            ],
        },
        {
            "id": "new-resource-repair",
            "ops": [
                {"op": "insert_fact", "id": 20, "dimension": 9, "amount": 3},
                {"op": "insert_dimension", "id": 9, "ceiling": 10, "rate": 1},
                {"op": "update_fact", "id": 999, "dimension": 9, "amount": 3},
            ],
        },
        {
            "id": "duplicate-projection-and-derived-rhs",
            "ops": [
                {"op": "insert_fact", "id": 10, "dimension": 3, "amount": 6},
                {"op": "insert_fact", "id": 11, "dimension": 3, "amount": 6},
            ],
        },
        {
            "id": "ordinary-duplicate-error",
            "outcome": "reject",
            "ops": [
                {"op": "insert_fact", "id": 12, "dimension": 2, "amount": 1},
                {"op": "insert_fact", "id": 1, "dimension": 2, "amount": 1},
            ],
        },
        {
            "id": "delete-last-member-from-group",
            "ops": [
                {"op": "delete_fact", "id": 4},
                {"op": "delete_fact", "id": 3},
            ],
        },
    ],
}
TABLES = ("dimension", "fact", "maintained", "projected", "missing", "derived_rhs")


def _initial() -> dict[str, dict[int, list[int]]]:
    return {
        name: {row[0]: list(row) for row in PLAN["fixture"][name]} for name in ("dimension", "fact")
    }


def _oracle(sources: dict[str, dict[int, list[int]]]) -> dict[str, list[list[int]]]:
    dimensions, facts = sources["dimension"], sources["fact"]
    groups: dict[int, list[int]] = {}
    for _, dimension_id, amount in facts.values():
        aggregate = groups.setdefault(dimension_id, [0, 0])
        aggregate[0] += amount
        aggregate[1] += 1
    return {
        "dimension": sorted(dimensions.values()),
        "fact": sorted(facts.values()),
        "maintained": sorted([[key, *value] for key, value in groups.items()]),
        "projected": sorted([[row[1], row[2]] for row in facts.values()]),
        "missing": sorted([[row[0], row[1]] for row in facts.values() if row[1] not in dimensions]),
        "derived_rhs": sorted(
            [fact[0], fact[1], fact[2], groups[fact[1]][0], groups[fact[1]][1]]
            for fact in facts.values()
        ),
    }


def _apply(sources: dict[str, dict[int, list[int]]], op: dict[str, Any]) -> str | None:
    kind = op["op"]
    table = "dimension" if kind.endswith("dimension") else "fact"
    rows = sources[table]
    key = op["id"]
    action = kind.removesuffix("_dimension").removesuffix("_fact")
    if action == "delete":
        rows.pop(key, None)
        return None
    if action == "insert" and key in rows:
        return "duplicate"
    if action == "update" and key not in rows:
        return None
    if action == "insert" or action == "update":
        rows[key] = (
            [key, op["dimension"], op["amount"]]
            if table == "fact"
            else [key, op["ceiling"], op["rate"]]
        )
        return None
    raise AssertionError(f"unknown operation: {kind}")


def _sql(op: dict[str, Any]) -> tuple[str, tuple[int, ...]]:
    kind = op["op"]
    table = "dimension" if kind.endswith("dimension") else "fact"
    action = kind.removesuffix("_dimension").removesuffix("_fact")
    if action == "delete":
        return f"DELETE FROM {table} WHERE id=?", (op["id"],)
    if table == "fact":
        vals = (op["dimension"], op["amount"])
        columns = "dimension_id=?, amount=?"
    else:
        vals = (op["ceiling"], op["rate"])
        columns = "ceiling=?, rate=?"
    if action == "insert":
        return f"INSERT INTO {table} VALUES (?,?,?)", (op["id"], *vals)
    return f"UPDATE {table} SET {columns} WHERE id=?", (*vals, op["id"])


class SQLiteControl:
    def __init__(self, fixture: dict[str, dict[int, list[int]]] | None = None):
        initial = fixture or _initial()
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        self.identity = {"sqlite": sqlite3.sqlite_version, "python": sys.version}
        self.db.execute(
            "CREATE TABLE dimension (id INTEGER PRIMARY KEY, ceiling INTEGER NOT NULL, rate INTEGER NOT NULL)"
        )
        self.db.execute(
            "CREATE TABLE fact (id INTEGER PRIMARY KEY, dimension_id INTEGER NOT NULL, amount INTEGER NOT NULL)"
        )
        self.db.execute("CREATE INDEX fact_dimension_idx ON fact(dimension_id)")
        self.db.executemany("INSERT INTO dimension VALUES (?,?,?)", initial["dimension"].values())
        self.db.executemany("INSERT INTO fact VALUES (?,?,?)", initial["fact"].values())
        self.db.executescript("""
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
            CREATE VIEW projected AS SELECT dimension_id, amount FROM fact;
            CREATE VIEW missing AS
              SELECT f.id AS id, f.dimension_id AS dimension_id FROM fact AS f
              WHERE NOT EXISTS (SELECT * FROM dimension AS d WHERE d.id = f.dimension_id);
        """)

    def read(self) -> dict[str, list[list[int]]]:
        result = {
            name: sorted([list(row) for row in self.db.execute(f"SELECT * FROM {name}")])
            for name in TABLES
            if name != "derived_rhs"
        }
        result["derived_rhs"] = sorted(
            [
                list(row)
                for row in self.db.execute(
                    "SELECT f.id, f.dimension_id, f.amount, m.total, m.n "
                    "FROM fact AS f JOIN maintained AS m ON f.dimension_id = m.dimension_id"
                )
            ]
        )
        return result

    def execute(self, sql: str, params: tuple[int, ...] = ()) -> None:
        self.db.execute(sql, params)

    def commit(self) -> None:
        if self.db.execute("SELECT 1 FROM missing LIMIT 1").fetchone():
            self.db.rollback()
            raise ValueError("required-empty absence assertion violated")
        self.db.execute("COMMIT")

    def rollback(self) -> None:
        self.db.rollback()

    def close(self) -> None:
        self.db.close()


def _expected_history() -> tuple[list[dict[str, Any]], dict[str, dict[int, list[int]]]]:
    state = _initial()
    history = []
    for txn in PLAN["transactions"]:
        before = copy.deepcopy(state)
        working = copy.deepcopy(state)
        steps = []
        failed = False
        for operation in txn["ops"]:
            candidate = copy.deepcopy(working)
            err = _apply(candidate, operation)
            if err:
                failed = True
                steps.append({"error": err, "state": _oracle(before)})
                break
            working = candidate
            steps.append({"error": None, "state": _oracle(working)})
        outcome = txn.get("outcome", "accept")
        rejected = failed or (outcome != "rollback" and bool(_oracle(working)["missing"]))
        if rejected != (outcome == "reject"):
            raise AssertionError(f"invalid workload outcome {txn['id']}: expected={outcome}")
        if outcome == "accept":
            state = working
        history.append(
            {"id": txn["id"], "outcome": outcome, "steps": steps, "state": _oracle(state)}
        )
    return history, state


class NativeControl:
    """Adapter for the unreleased native SQL preview, when installed/importable."""

    def __init__(
        self, fixture: dict[str, dict[int, list[int]]] | None = None, mode: str = "overlay"
    ):
        from refpot.sql import Database

        initial = fixture or _initial()
        self.db = Database(mode=mode)
        import refpot
        import refpot._sql

        extension_file = refpot._sql.__file__
        assert extension_file is not None
        extension = Path(extension_file).resolve()
        self.identity = {
            "package": str(Path(refpot.__file__).resolve()),
            "extension": str(extension),
            "extension_sha256": hashlib.sha256(extension.read_bytes()).hexdigest(),
            "mode": mode,
        }
        self.execute(
            "CREATE TABLE dimension (id INTEGER PRIMARY KEY, ceiling INTEGER NOT NULL, rate INTEGER NOT NULL)"
        )
        self.execute(
            "CREATE TABLE fact (id INTEGER PRIMARY KEY, dimension_id INTEGER NOT NULL, amount INTEGER NOT NULL)"
        )
        for table in ("dimension", "fact"):
            for row in initial[table].values():
                self.execute(f"INSERT INTO {table} VALUES (?,?,?)", tuple(row))
        self.execute(
            "CREATE MATERIALIZED VIEW maintained AS SELECT dimension_id, SUM(amount) AS total, COUNT(*) AS n FROM fact GROUP BY dimension_id"
        )
        self.execute("CREATE MATERIALIZED VIEW projected AS SELECT dimension_id, amount FROM fact")
        self.execute(
            "CREATE MATERIALIZED VIEW missing AS SELECT f.id AS id, f.dimension_id AS dimension_id FROM fact AS f WHERE NOT EXISTS (SELECT * FROM dimension AS d WHERE d.id = f.dimension_id)"
        )
        self.execute("CREATE ASSERTION missing_empty CHECK (NOT EXISTS (SELECT * FROM missing))")

    def execute(self, sql: str, params: tuple[int, ...] = ()) -> Any:
        return self.db.execute(sql, params)

    def read(self) -> dict[str, list[list[int]]]:
        result = {
            name: sorted([list(row) for row in self.execute(f"SELECT * FROM {name}").rows])
            for name in TABLES
            if name != "derived_rhs"
        }
        result["derived_rhs"] = sorted(
            [
                list(row)
                for row in self.execute(
                    "SELECT f.id, f.dimension_id, f.amount, m.total, m.n "
                    "FROM fact AS f JOIN maintained AS m ON f.dimension_id = m.dimension_id"
                ).rows
            ]
        )
        return result

    def commit(self) -> None:
        self.execute("COMMIT")

    def rollback(self) -> None:
        self.execute("ROLLBACK")

    def close(self) -> None:
        self.db.close()


def _backend(engine: str, fixture: dict[str, dict[int, list[int]]] | None = None) -> Any:
    if engine == "sqlite":
        return SQLiteControl(fixture)
    if engine in ("native-overlay", "native-modular"):
        mode = engine.removeprefix("native-")
        return NativeControl(fixture, mode=mode)
    raise ValueError(engine)


def run_control(engine: str = "sqlite", mutant: str | None = None) -> dict[str, Any]:
    expected, _ = _expected_history()
    backend = _backend(engine)
    actual_history = []
    try:
        initial_state = _initial()
        assert backend.read() == _oracle(initial_state), "construction full-state mismatch"
        for txn, want in zip(PLAN["transactions"], expected, strict=True):
            before = copy.deepcopy(initial_state)
            backend.execute("BEGIN")
            working = copy.deepcopy(initial_state)
            steps = []
            failed = False
            for index, (op, expected_step) in enumerate(
                zip(txn["ops"], want["steps"], strict=True)
            ):
                try:
                    if not (
                        mutant == "drop-operation"
                        and txn["id"] == "duplicate-projection-and-derived-rhs"
                        and index == 0
                    ):
                        backend.execute(*_sql(op))
                except Exception as exc:
                    failed = True
                    if engine == "sqlite":
                        backend.rollback()
                    message = str(exc).lower()
                    error = (
                        "duplicate"
                        if "unique" in message or "duplicate" in message
                        else "ordinary-error"
                    )
                    observed = backend.read()
                    assert error == expected_step["error"] and observed == _oracle(before), (
                        txn["id"],
                        "statement error/rollback mismatch",
                        error,
                        observed,
                        _oracle(before),
                    )
                    steps.append({"error": error, "state": observed})
                    break
                _apply(working, op)
                observed = backend.read()
                assert observed == expected_step["state"], (
                    txn["id"],
                    "statement full-state mismatch",
                    index,
                    observed,
                    expected_step["state"],
                )
                steps.append({"error": None, "state": observed})
            if failed:
                assert txn.get("outcome") == "reject", (txn["id"], "unexpected statement error")
            elif txn.get("outcome") == "rollback" and mutant != "commit-rollback":
                backend.rollback()
            else:
                try:
                    backend.commit()
                except Exception as exc:
                    assert txn.get("outcome") == "reject" and (
                        "required-empty" in str(exc).lower() or "assertion" in str(exc).lower()
                    ), (txn["id"], "unexpected commit rejection", str(exc))
                else:
                    assert txn.get("outcome") != "reject", (
                        txn["id"],
                        "rejected commit was accepted",
                    )
            actual = backend.read()
            assert actual == want["state"], (
                txn["id"],
                "transaction full-state mismatch",
                actual,
                want["state"],
            )
            actual_history.append(
                {"id": txn["id"], "outcome": want["outcome"], "steps": steps, "state": actual}
            )
            # Advance only after an accepted commit; rejected and rolled-back work
            # leaves the independent committed source dictionaries untouched.
            if txn.get("outcome", "accept") == "accept":
                replay = copy.deepcopy(initial_state)
                for op in txn["ops"]:
                    assert _apply(replay, op) is None
                initial_state = replay
        assert actual_history == expected, "history differs from independent source replay"
    finally:
        backend.close()
    data = {
        "format": PLAN["format"],
        "semantics": "absence-aware full-state replay",
        "engine": engine,
        "plan_sha256": hashlib.sha256(json.dumps(PLAN, sort_keys=True).encode()).hexdigest(),
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "identity": backend.identity,
        "transaction_count": len(PLAN["transactions"]),
        "records": [{"fixture": "absence", "history": actual_history}],
    }
    return data


def validate(data: dict[str, Any]) -> int:
    assert (
        data["plan_sha256"] == hashlib.sha256(json.dumps(PLAN, sort_keys=True).encode()).hexdigest()
    )
    assert data["harness_sha256"] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    assert data["transaction_count"] == len(PLAN["transactions"])
    expected, _ = _expected_history()
    assert len(data["records"]) == 1 and data["records"][0]["fixture"] == "absence"
    assert data["records"][0]["history"] == expected
    return len(expected)


def verify_installed() -> None:
    import refpot
    from refpot import _sql, sql

    prefix = Path(sys.prefix).resolve()
    origins = [Path(module.__file__).resolve() for module in (refpot, _sql, sql)]
    assert all(path.is_relative_to(prefix) for path in origins), (
        "candidate must be installed outside the checkout",
        origins,
        prefix,
    )


def _rss_bytes() -> tuple[int, str]:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return int(value), "bytes"
    return int(value * 1024), "bytes"


def _service_case(engine: str, rows: int, density: str) -> dict[str, Any]:
    # Workload setup is intentionally complete before timer and validation follows it.
    state = {
        "dimension": {i: [i, 10**9, 1] for i in range(rows)},
        "fact": {
            i: [
                i,
                i if density == "sparse" else i % max(1, rows // 10),
                1 if density == "sparse" else (-1 if i % 2 else 1),
            ]
            for i in range(rows)
        },
    }
    setup_start = time.perf_counter_ns()
    backend = _backend(engine, state)
    setup_ns = time.perf_counter_ns() - setup_start
    baseline_rss, unit = _rss_bytes()
    start = time.perf_counter_ns()
    backend.execute("BEGIN")
    if density == "sparse":
        backend.execute("UPDATE fact SET amount=? WHERE id=?", (2, rows // 2))
    else:
        # Same prepared point updates in SQLite and native: a dense cancellation
        # wave touches half the facts twice and leaves the original bag unchanged.
        for fact_id in range(0, rows, 2):
            backend.execute("UPDATE fact SET amount=? WHERE id=?", (2, fact_id))
        for fact_id in range(0, rows, 2):
            backend.execute("UPDATE fact SET amount=? WHERE id=?", (1, fact_id))
    backend.commit()
    service_ns = time.perf_counter_ns() - start
    peak_rss, _ = _rss_bytes()
    validation_start = time.perf_counter_ns()
    actual = backend.read()
    # Independent expected result from full source replay, outside timed service.
    expected_sources = copy.deepcopy(state)
    if density == "sparse":
        _apply(
            expected_sources,
            {"op": "update_fact", "id": rows // 2, "dimension": rows // 2, "amount": 2},
        )
    else:
        # The two dense updates cancel exactly for the source bag and aggregate.
        pass
    assert actual == _oracle(expected_sources), (density, "performance-case final state mismatch")
    validation_ns = time.perf_counter_ns() - validation_start
    close_start = time.perf_counter_ns()
    backend.close()
    close_ns = time.perf_counter_ns() - close_start
    return {
        "setup_ns": setup_ns,
        "validation_ns": validation_ns,
        "close_ns": close_ns,
        "engine": engine,
        "workload": density,
        "rows": rows,
        "service_ns": service_ns,
        "peak_process_rss_bytes": peak_rss,
        "baseline_peak_process_rss_bytes": baseline_rss,
        "peak_rss_delta_bytes": max(0, peak_rss - baseline_rss),
        "rss_unit": unit,
        "platform": platform.platform(),
        "python": sys.version,
        "sqlite": sqlite3.sqlite_version,
        "backend_identity": backend.identity,
        "setup_and_validation_timed": False,
    }


def _run_service_isolated(
    engine: str, rows: int, density: str, require_installed: bool = False
) -> dict[str, Any]:
    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--service-worker",
            engine,
            str(rows),
            density,
        ]
        + (["--require-installed"] if require_installed and engine != "sqlite" else []),
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    return json.loads(proc.stdout)


def run_performance(
    engines: tuple[str, ...] = ("sqlite",),
    repeats: int = 3,
    output_dir: Path | None = None,
    rows: int = 256,
    require_installed: bool = False,
) -> dict[str, Any]:
    if repeats < 1 or rows < 2:
        raise ValueError("repeats must be >=1 and rows >=2")
    supported = ("sqlite", "native-overlay", "native-modular")
    if any(engine not in supported for engine in engines):
        raise ValueError(f"unsupported engine set: {engines}")
    output_dir = output_dir or HERE / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    # Alternate the sparse/dense order each repetition; separate fixtures per run.
    for repeat in range(repeats):
        shapes = ("sparse", "dense") if repeat % 2 == 0 else ("dense", "sparse")
        for shape in shapes:
            for engine in engines if repeat % 2 == 0 else tuple(reversed(engines)):
                record = _run_service_isolated(engine, rows, shape, require_installed)
                raw_path = output_dir / f"{engine}-{shape}-repeat-{repeat}.json"
                record.update(
                    repeat=repeat,
                    seed=0,
                    memory_method="resource.getrusage(RUSAGE_SELF).ru_maxrss",
                    plan_sha256=hashlib.sha256(
                        json.dumps(PLAN, sort_keys=True).encode()
                    ).hexdigest(),
                    harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    raw_path=str(raw_path.resolve()),
                )
                assert not raw_path.exists(), "refuse to overwrite retained trial"
                raw_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
                records.append(json.loads(raw_path.read_text()))
    medians = {
        f"{engine}-{shape}": int(
            statistics.median(
                r["service_ns"] for r in records if r["engine"] == engine and r["workload"] == shape
            )
        )
        for engine in engines
        for shape in ("sparse", "dense")
    }
    return {
        "format": "transaction-deltas-service-v1",
        "records": records,
        "summary": {"median_service_ns_by_workload": medians},
        "note": "Screening measurements only; RSS is process high-water mark, not total allocation/copy cost.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engine", choices=("sqlite", "native-overlay", "native-modular", "all"), default="sqlite"
    )
    parser.add_argument("--mutant", choices=("drop-operation", "commit-rollback"))
    parser.add_argument("--performance", action="store_true")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--rows", type=int, default=256)
    parser.add_argument("--require-installed", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--service-worker", nargs=3, metavar=("ENGINE", "ROWS", "WORKLOAD"), help=argparse.SUPPRESS
    )
    args = parser.parse_args()
    if args.require_installed:
        verify_installed()
    if args.service_worker:
        engine, rows, density = args.service_worker
        print(json.dumps(_service_case(engine, int(rows), density), sort_keys=True))
        return
    if args.performance:
        engines = (
            ("sqlite", "native-overlay", "native-modular")
            if args.engine == "all"
            else (args.engine,)
        )
        result = run_performance(
            engines, args.repeats, args.output, args.rows, args.require_installed
        )
    else:
        if args.engine == "all":
            parser.error("--engine all is only valid with --performance")
        result = run_control(args.engine, args.mutant)
        validate(result)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output and not args.performance:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
