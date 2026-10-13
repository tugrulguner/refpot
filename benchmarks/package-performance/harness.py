#!/usr/bin/env python3
"""Paired public-package RefPot/SQLite screening harness.

This measures the installed/ref-imported public API, not a fixed-schema reimplementation.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import platform
import random
import shutil
import sqlite3
import statistics
import subprocess
import sys
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import refpot
from refpot import Database, Row

CORE_MODULE = importlib.import_module("refpot._core")

SCHEMA = """CREATE TABLE items (
    key INTEGER PRIMARY KEY,
    value INTEGER NOT NULL,
    text TEXT NOT NULL CHECK(length(CAST(text AS BLOB)) <= 31)
) STRICT"""
SELECT = "SELECT key,value,text FROM items WHERE key=?"
UPDATE = "UPDATE items SET value=? WHERE key=?"
WORKLOADS = ("point_read", "update_single", "update_batch32")
CANDIDATES = ("refpot", "sqlite64_normal", "sqlite1000_normal",
              "sqlite64_exclusive", "sqlite1000_exclusive")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_trace(rows: int, operations: int, seed: int, writes: bool) -> list[tuple[str, int, int | None]]:
    if rows < 1 or operations < 1:
        raise ValueError("rows and operations must be positive")
    rng = random.Random(seed)
    values = [i % 17 for i in range(rows)]
    trace = []
    for _sequence in range(operations):
        key = rng.randrange(rows)
        if writes:
            values[key] += 1
            if not -(1 << 63) <= values[key] < (1 << 63):
                raise OverflowError("trace generated a value outside signed 64-bit range")
            trace.append(("update", key, values[key]))
        else:
            trace.append(("get", key, None))
    return trace


def connect_sql(path: Path, checkpoint_threshold: int, locking: str = "normal"):
    db = sqlite3.connect(path, isolation_level=None, cached_statements=64)
    try:
        if db.execute("PRAGMA journal_mode=WAL").fetchone()[0] != "wal":
            raise AssertionError("SQLite did not enter WAL mode")
        for setting in (
            "synchronous=FULL", "fullfsync=OFF", "checkpoint_fullfsync=OFF",
            "cache_size=-2000", f"wal_autocheckpoint={checkpoint_threshold}",
            "mmap_size=0", f"locking_mode={locking}",
        ):
            db.execute("PRAGMA " + setting)
        names = ("synchronous", "fullfsync", "checkpoint_fullfsync", "cache_size",
                 "wal_autocheckpoint", "mmap_size", "locking_mode")
        settings = {name: db.execute("PRAGMA " + name).fetchone()[0] for name in names}
        expected = dict(synchronous=2, fullfsync=0, checkpoint_fullfsync=0,
                        cache_size=-2000, wal_autocheckpoint=checkpoint_threshold,
                        mmap_size=0, locking_mode=locking)
        if settings != expected:
            raise AssertionError(f"SQLite PRAGMA mismatch: {settings!r} != {expected!r}")
        return db, settings
    except BaseException:
        db.close()
        raise


def sql_options(candidate: str) -> tuple[int, str]:
    if candidate == "refpot":
        raise ValueError("RefPot has no SQLite settings")
    threshold = 64 if "64" in candidate else 1000
    locking = "exclusive" if candidate.endswith("exclusive") else "normal"
    return threshold, locking


def seed_sqlite(db: sqlite3.Connection, rows: int) -> None:
    db.execute(SCHEMA)
    db.execute("BEGIN IMMEDIATE")
    db.executemany("INSERT INTO items VALUES (?,?,?)",
                   ((i, i % 17, f"row-{i}") for i in range(rows)))
    db.execute("COMMIT")


def expected_rows(rows: int, values: dict[int, int] | None = None) -> list[Row]:
    values = values or {}
    return [Row(i, values.get(i, i % 17), f"row-{i}") for i in range(rows)]


def validate_sqlite(db: sqlite3.Connection, rows: int, values: dict[int, int] | None = None) -> bool:
    actual = [Row(*row) for row in db.execute(
        "SELECT key,value,text FROM items ORDER BY key")]
    return actual == expected_rows(rows, values)


def validate_refpot(db: Database, rows: int, values: dict[int, int] | None = None) -> bool:
    if len(db) != rows:
        return False
    return all(db.get(expected.key) == expected
               for expected in expected_rows(rows, values))


def append_jsonl(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def aggregate(records: list[dict], expected_keys: set[tuple]) -> dict:
    observed = [(r["repeat"], r["rows"], r["workload"], r["candidate"]) for r in records]
    if len(observed) != len(set(observed)):
        raise ValueError("duplicate trial key")
    if set(observed) != expected_keys:
        missing, extra = expected_keys - set(observed), set(observed) - expected_keys
        raise ValueError(f"matrix mismatch: missing={sorted(missing)!r}, extra={sorted(extra)!r}")
    if any(r.get("verified") is not True for r in records):
        raise ValueError("unverified trial record")
    if not expected_keys:
        raise ValueError("expected matrix is empty")
    expected_candidates = [candidate for candidate in CANDIDATES
                           if candidate in {key[3] for key in expected_keys}]
    expected_workloads = [workload for workload in WORKLOADS
                          if workload in {key[2] for key in expected_keys}]
    expected_repeats = {key[0] for key in expected_keys}
    expected_rows = {key[1] for key in expected_keys}
    cartesian = {(repeat, rows, workload, candidate)
                 for repeat in expected_repeats for rows in expected_rows
                 for workload in expected_workloads for candidate in expected_candidates}
    if cartesian != expected_keys:
        raise ValueError("expected keys do not form a Cartesian matrix")
    summary = []
    for rows in sorted(expected_rows):
        for workload in expected_workloads:
            cell = [r for r in records if r["rows"] == rows and r["workload"] == workload]
            medians = {candidate: statistics.median(
                r["service_ns"] for r in cell if r["candidate"] == candidate)
                for candidate in expected_candidates}
            sql_candidates = [candidate for candidate in expected_candidates if candidate != "refpot"]
            if "refpot" not in medians or not sql_candidates:
                raise ValueError("matrix must include RefPot and at least one SQLite candidate")
            best_sqlite = min(sql_candidates, key=lambda candidate: medians[candidate])
            summary.append({"rows": rows, "workload": workload, "service_median_ns": medians,
                            "best_tested_sqlite": best_sqlite,
                            "refpot_speedup": medians[best_sqlite] / medians["refpot"],
                            "sqlite_relative_to_refpot": medians[best_sqlite] / medians["refpot"],
                            "regression_pct_vs_best_sqlite": max(
                                0.0, (medians["refpot"] / medians[best_sqlite] - 1.0) * 100.0)})
    return {"records": len(records), "summary": summary, "all_verified": True}


def repository_root(start: Path) -> Path | None:
    return next((parent for parent in (start.resolve(), *start.resolve().parents)
                 if (parent / ".git").exists()), None)


def source_revision(start: Path) -> str | None:
    root = repository_root(start)
    if root is None:
        return None
    try:
        return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def environment(script_path: Path) -> dict:
    package_path = Path(refpot.__file__).resolve()
    native_path = Path(str(CORE_MODULE.__file__))
    try:
        package_version = version("refpot")
    except PackageNotFoundError:
        package_version = getattr(refpot, "__version__", None)
    package_root = repository_root(package_path)
    native_source = package_root / "native" / "core.cpp" if package_root else None
    if native_source is not None and not native_source.is_file():
        native_source = None
    return {
        "harness_source_revision": source_revision(script_path),
        "package_source_revision": source_revision(package_path),
        "package_source_root": str(package_root) if package_root else None,
        "native_source_path": str(native_source) if native_source else None,
        "native_source_sha256": sha256(native_source) if native_source else None,
        "python": sys.version,
        "sqlite": sqlite3.sqlite_version, "platform": platform.platform(),
        "refpot_version": package_version,
        "refpot_import_path": str(package_path), "native_binary_path": str(native_path),
        "native_binary_sha256": sha256(native_path), "package_source_sha256": sha256(package_path),
        "harness_sha256": sha256(script_path.resolve()),
    }


def run_trial(root: Path, rows: int, workload: str, candidate: str,
              operations: int, seed: int, identity: str) -> dict:
    folder = root / identity
    folder.mkdir()
    native = candidate == "refpot"
    path = folder / ("db.rp" if native else "db.sqlite")
    settings = None
    setup_started = time.perf_counter_ns()
    if native:
        with Database(path) as db:
            with db.transaction():
                for key in range(rows):
                    db.insert(key, key % 17, f"row-{key}")
            db.checkpoint()
    else:
        threshold, locking = sql_options(candidate)
        db, settings = connect_sql(path, threshold, locking)
        seed_sqlite(db, rows)
        if db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone() != (0, 0, 0):
            raise AssertionError("seed WAL checkpoint was busy")
        db.close()

    setup_ns = time.perf_counter_ns() - setup_started
    writes = workload != "point_read"
    trace = make_trace(rows, operations, seed, writes)
    final_values: dict[int, int] = {}
    if writes:
        for _, key, value in trace:
            assert value is not None
            final_values[key] = value
    expected_checksum = sum(key + key % 17 + len(f"row-{key}") for _, key, _ in trace)
    statement: sqlite3.Cursor | None = None
    native_db: Database | None = None
    sql_db: sqlite3.Connection | None = None
    if native:
        native_db = Database(path)
        assert native_db.get(0) == Row(0, 0, "row-0")
    else:
        threshold, locking = sql_options(candidate)
        sql_db, settings = connect_sql(path, threshold, locking)
        statement = sql_db.cursor()
        assert statement.execute(SELECT, (0,)).fetchone() == (0, 0, "row-0")
    checksum = 0
    observed_rows: list[Row] = []
    started = time.perf_counter_ns()
    if workload == "point_read":
        for _, key, _ in trace:
            if native:
                assert native_db is not None
                row = native_db.get(key)
            else:
                assert statement is not None
                row = Row(*statement.execute(SELECT, (key,)).fetchone())
            observed_rows.append(row)
            checksum += row.key + row.value + len(row.text)
    elif workload == "update_single":
        for _, key, value in trace:
            if native:
                assert native_db is not None
                native_db.update(key, value=value)
            else:
                assert statement is not None
                statement.execute(UPDATE, (value, key))
    elif workload == "update_batch32":
        for offset in range(0, operations, 32):
            batch = trace[offset:offset + 32]
            if native:
                assert native_db is not None
                with native_db.transaction():
                    for _, key, value in batch:
                        native_db.update(key, value=value)
            else:
                assert sql_db is not None and statement is not None
                sql_db.execute("BEGIN IMMEDIATE")
                for _, key, value in batch:
                    statement.execute(UPDATE, (value, key))
                sql_db.execute("COMMIT")
    else:
        raise ValueError(f"unknown workload: {workload}")
    operations_ns = time.perf_counter_ns() - started
    if workload == "point_read":
        expected_reads = [Row(key, key % 17, f"row-{key}") for _, key, _ in trace]
        if checksum != expected_checksum or observed_rows != expected_reads:
            raise AssertionError("point-read returned-row mismatch")
    checkpoint_ns = 0
    if writes:
        started = time.perf_counter_ns()
        if native:
            assert native_db is not None
            native_db.checkpoint()
        else:
            assert sql_db is not None
            if sql_db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone() != (0, 0, 0):
                raise AssertionError("final SQLite WAL checkpoint was busy")
        checkpoint_ns = time.perf_counter_ns() - started
    if native:
        assert native_db is not None
        full_state_ok = validate_refpot(native_db, rows, final_values)
    else:
        assert sql_db is not None
        full_state_ok = validate_sqlite(sql_db, rows, final_values)
    if not full_state_ok:
        raise AssertionError("full-state validation failed")
    # A separate, untimed mutation deliberately leaves pending redo for the reopen probe.
    # It keeps recovery timing distinct from write-service timing, which includes a checkpoint.
    probe_value = final_values.get(0, 0) + 1
    if native:
        assert native_db is not None
        native_db.update(0, value=probe_value)
        final_values[0] = probe_value
        native_db.close()
        started = time.perf_counter_ns()
        pending = Database(path)
        pending_reopen_ns = time.perf_counter_ns() - started
        pending_ok = validate_refpot(pending, rows, final_values)
        pending.checkpoint()
        pending.close()
        started = time.perf_counter_ns()
        clean = Database(path)
        clean_reopen_ns = time.perf_counter_ns() - started
        clean_ok = validate_refpot(clean, rows, final_values)
        clean.close()
    else:
        assert statement is not None and sql_db is not None
        statement.execute(UPDATE, (probe_value, 0))
        final_values[0] = probe_value
        sql_db.close()
        threshold, locking = sql_options(candidate)
        started = time.perf_counter_ns()
        pending, _ = connect_sql(path, threshold, locking)
        pending_reopen_ns = time.perf_counter_ns() - started
        pending_ok = validate_sqlite(pending, rows, final_values)
        if pending.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone() != (0, 0, 0):
            raise AssertionError("reopen-probe SQLite checkpoint was busy")
        pending.close()
        started = time.perf_counter_ns()
        clean, _ = connect_sql(path, threshold, locking)
        clean_reopen_ns = time.perf_counter_ns() - started
        clean_ok = validate_sqlite(clean, rows, final_values)
        clean.close()
    if not pending_ok or not clean_ok:
        raise AssertionError("reopen full-state validation failed")
    result = {"repeat": None, "rows": rows, "workload": workload, "candidate": candidate,
              "operations": operations, "seed": seed, "setup_ns": setup_ns,
              "operations_ns": operations_ns, "checkpoint_ns": checkpoint_ns,
              "service_ns": operations_ns + checkpoint_ns, "pending_wal_reopen_ns": pending_reopen_ns,
              "clean_reopen_ns": clean_reopen_ns, "full_state_validated": True,
              "pending_reopen_validated": True, "clean_reopen_validated": True,
              "sqlite_settings": settings, "verified": True}
    shutil.rmtree(folder)
    return result


def create_plan(args: argparse.Namespace) -> None:
    if args.rows < 1:
        raise ValueError("rows must be positive")
    if args.operations < 32 or args.operations % 32:
        raise ValueError("operations must be a positive multiple of 32 (minimum 32)")
    if args.repeats < 1:
        raise ValueError("repeats must be positive")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    plan = {"schema_version": 1, "rows": [args.rows], "operations": args.operations,
            "seed": args.seed, "repeats": args.repeats, "workloads": list(WORKLOADS),
            "candidates": list(CANDIDATES),
            "scope": "public RefPot package versus prepared SQLite; Python API screen, not native qualification",
            "environment_at_plan": environment(Path(__file__))}
    (output / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"plan": str(output / "plan.json"), "trials": args.repeats * len(WORKLOADS) * len(CANDIDATES)}, indent=2))


def run_plan(args: argparse.Namespace) -> None:
    plan_path = args.plan.resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("schema_version") != 1 or plan.get("workloads") != list(WORKLOADS) or plan.get("candidates") != list(CANDIDATES):
        raise ValueError("unsupported or modified plan schema")
    if (not isinstance(plan.get("rows"), list) or not plan["rows"]
            or any(type(rows) is not int or rows < 1 for rows in plan["rows"])
            or type(plan.get("operations")) is not int or plan["operations"] < 32
            or plan["operations"] % 32 or type(plan.get("repeats")) is not int
            or plan["repeats"] < 1 or type(plan.get("seed")) is not int):
        raise ValueError("invalid plan dimensions")
    current_environment = environment(Path(__file__))
    planned_harness = plan.get("environment_at_plan", {}).get("harness_sha256")
    if planned_harness != current_environment["harness_sha256"]:
        raise ValueError("harness hash differs from the frozen plan")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(plan_path, out / "plan.json")
    raw_path = out / "raw.jsonl"
    run_meta = {"plan_sha256": sha256(plan_path), "environment": environment(Path(__file__))}
    (out / "run.json").write_text(json.dumps(run_meta, indent=2) + "\n", encoding="utf-8")
    records = []
    rows_values = plan["rows"]
    for repeat in range(plan["repeats"]):
        cells = [(rows, workload) for rows in rows_values for workload in plan["workloads"]]
        if repeat % 2:
            cells.reverse()
        for cell_index, (rows, workload) in enumerate(cells):
            candidates = list(plan["candidates"])
            rotate = (repeat + cell_index) % len(candidates)
            candidates = candidates[rotate:] + candidates[:rotate]
            for candidate in candidates:
                result = run_trial(out, rows, workload, candidate, plan["operations"],
                                   plan["seed"], f"r{repeat}-{rows}-{workload}-{candidate}")
                result["repeat"] = repeat
                result["candidate_order"] = candidates
                append_jsonl(raw_path, result)
                records.append(result)
    expected = {(repeat, rows, workload, candidate)
                for repeat in range(plan["repeats"]) for rows in rows_values
                for workload in plan["workloads"] for candidate in plan["candidates"]}
    summary = aggregate(records, expected)
    if args.require_speedup is not None:
        selected_workloads = args.require_workload or plan["workloads"]
        selected = [entry for entry in summary["summary"]
                    if entry["workload"] in selected_workloads]
        failures = [entry for entry in selected if entry["refpot_speedup"] < args.require_speedup]
        summary["speedup_gate"] = {"threshold": args.require_speedup,
                                    "workloads": selected_workloads,
                                    "passed": not failures,
                                    "failed_cells": failures}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(out), **summary}, indent=2))
    if args.require_speedup is not None and not summary["speedup_gate"]["passed"]:
        raise SystemExit(1)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="create a frozen workload plan in a new directory")
    plan.add_argument("--output", type=Path, required=True)
    plan.add_argument("--rows", type=int, default=128)
    plan.add_argument("--operations", type=int, default=256)
    plan.add_argument("--seed", type=int, default=918271)
    plan.add_argument("--repeats", type=int, default=3)
    plan.set_defaults(func=create_plan)
    run = commands.add_parser("run", help="execute frozen plan into a new evidence directory")
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--require-speedup", type=float)
    run.add_argument("--require-workload", action="append", choices=WORKLOADS)
    run.set_defaults(func=run_plan)
    return root


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
