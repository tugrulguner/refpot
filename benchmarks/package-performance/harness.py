#!/usr/bin/env python3
"""Paired public-package RefPot/SQLite screening harness.

This measures the installed/ref-imported public API, not a fixed-schema reimplementation.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
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
CANDIDATES = (
    "refpot",
    "sqlite64_normal",
    "sqlite1000_normal",
    "sqlite64_exclusive",
    "sqlite1000_exclusive",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_trace(
    rows: int, operations: int, seed: int, writes: bool
) -> list[tuple[str, int, int | None]]:
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
            "synchronous=FULL",
            "fullfsync=OFF",
            "checkpoint_fullfsync=OFF",
            "cache_size=-2000",
            f"wal_autocheckpoint={checkpoint_threshold}",
            "mmap_size=0",
            f"locking_mode={locking}",
        ):
            db.execute("PRAGMA " + setting)
        names = (
            "synchronous",
            "fullfsync",
            "checkpoint_fullfsync",
            "cache_size",
            "wal_autocheckpoint",
            "mmap_size",
            "locking_mode",
        )
        settings = {name: db.execute("PRAGMA " + name).fetchone()[0] for name in names}
        expected = dict(
            synchronous=2,
            fullfsync=0,
            checkpoint_fullfsync=0,
            cache_size=-2000,
            wal_autocheckpoint=checkpoint_threshold,
            mmap_size=0,
            locking_mode=locking,
        )
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
    db.executemany(
        "INSERT INTO items VALUES (?,?,?)", ((i, i % 17, f"row-{i}") for i in range(rows))
    )
    db.execute("COMMIT")


def expected_rows(rows: int, values: dict[int, int] | None = None) -> list[Row]:
    values = values or {}
    return [Row(i, values.get(i, i % 17), f"row-{i}") for i in range(rows)]


def validate_sqlite(
    db: sqlite3.Connection, rows: int, values: dict[int, int] | None = None
) -> bool:
    actual = [Row(*row) for row in db.execute("SELECT key,value,text FROM items ORDER BY key")]
    return actual == expected_rows(rows, values)


def validate_refpot(db: Database, rows: int, values: dict[int, int] | None = None) -> bool:
    if len(db) != rows:
        return False
    return all(db.get(expected.key) == expected for expected in expected_rows(rows, values))


def append_jsonl(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def aggregate(
    records: list[dict],
    expected_keys: set[tuple],
    *,
    operations_by_cell: dict,
    seed: int,
    min_duration_ns: int,
) -> dict:
    required_ints = (
        "repeat",
        "rows",
        "operations",
        "seed",
        "setup_ns",
        "operations_ns",
        "checkpoint_ns",
        "service_ns",
        "clean_reopen_ns",
        "wal_bytes",
    )
    observed = [
        (r.get("repeat"), r.get("rows"), r.get("workload"), r.get("candidate")) for r in records
    ]
    if len(observed) != len(set(observed)):
        raise ValueError("duplicate trial key")
    if set(observed) != expected_keys:
        missing, extra = expected_keys - set(observed), set(observed) - expected_keys
        raise ValueError(f"matrix mismatch: missing={sorted(missing)!r}, extra={sorted(extra)!r}")
    if not expected_keys:
        raise ValueError("expected matrix is empty")
    for record in records:
        if any(type(record.get(field)) is not int or record[field] < 0 for field in required_ints):
            raise ValueError("invalid or negative trial integer")
        cell = (record["rows"], record["workload"])
        if record["operations"] != operations_by_cell.get(cell) or record["seed"] != seed:
            raise ValueError("trial operations or seed differ from frozen plan")
        for field in ("operations_ns", "service_ns", "clean_reopen_ns"):
            value = record.get(field)
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"invalid {field}")
        if record["service_ns"] != record["operations_ns"] + record["checkpoint_ns"]:
            raise ValueError("service time does not equal operations plus checkpoint")
        if record["operations_ns"] < min_duration_ns:
            raise ValueError("trial shorter than minimum duration; qualification failed")
        if (
            record.get("full_state_validated") is not True
            or record.get("recovery_validated") is not True
            or record.get("clean_reopen_validated") is not True
        ):
            raise ValueError("unverified state validation")
        order = record.get("candidate_order")
        if (
            not isinstance(order, list)
            or any(not isinstance(candidate, str) for candidate in order)
            or len(order) != len(CANDIDATES)
            or set(order) != set(CANDIDATES)
            or record["candidate"] not in order
        ):
            raise ValueError("invalid candidate order")
        if record["candidate"] == "refpot":
            if record.get("sqlite_settings") is not None:
                raise ValueError("unexpected SQLite settings for RefPot")
        else:
            threshold, locking = sql_options(record["candidate"])
            expected_settings = dict(
                synchronous=2,
                fullfsync=0,
                checkpoint_fullfsync=0,
                cache_size=-2000,
                wal_autocheckpoint=threshold,
                mmap_size=0,
                locking_mode=locking,
            )
            if record.get("sqlite_settings") != expected_settings:
                raise ValueError("unverified SQLite settings")
        expected_recovery = (
            "pending_wal_replay" if record["candidate"] == "refpot" else "ordinary_close_reopen"
        )
        if record.get("recovery_mode") != expected_recovery:
            raise ValueError("recovery mode does not match candidate")
        if expected_recovery == "pending_wal_replay":
            pending_ns = record.get("pending_wal_reopen_ns")
            if (
                not isinstance(pending_ns, (int, float))
                or isinstance(pending_ns, bool)
                or not math.isfinite(pending_ns)
                or pending_ns <= 0
                or record.get("pending_reopen_validated") is not True
            ):
                raise ValueError("invalid pending-WAL recovery evidence")
        else:
            if (
                record.get("pending_wal_reopen_ns") is not None
                or record.get("pending_reopen_validated") is not None
            ):
                raise ValueError("SQLite close/reopen must not claim pending-WAL replay")
        if record.get("verified") is not True:
            raise ValueError("unverified trial record")
    if not expected_keys:
        raise ValueError("expected matrix is empty")
    expected_candidates = [
        candidate for candidate in CANDIDATES if candidate in {key[3] for key in expected_keys}
    ]
    expected_workloads = [
        workload for workload in WORKLOADS if workload in {key[2] for key in expected_keys}
    ]
    expected_repeats = {key[0] for key in expected_keys}
    expected_rows = {key[1] for key in expected_keys}
    cartesian = {
        (repeat, rows, workload, candidate)
        for repeat in expected_repeats
        for rows in expected_rows
        for workload in expected_workloads
        for candidate in expected_candidates
    }
    if cartesian != expected_keys:
        raise ValueError("expected keys do not form a Cartesian matrix")
    summary = []
    for rows in sorted(expected_rows):
        for workload in expected_workloads:
            cell = [r for r in records if r["rows"] == rows and r["workload"] == workload]
            medians = {
                candidate: statistics.median(
                    r["service_ns"] for r in cell if r["candidate"] == candidate
                )
                for candidate in expected_candidates
            }
            sql_candidates = [
                candidate for candidate in expected_candidates if candidate != "refpot"
            ]
            if "refpot" not in medians or not sql_candidates:
                raise ValueError("matrix must include RefPot and at least one SQLite candidate")
            best_sqlite = min(sql_candidates, key=lambda candidate: medians[candidate])
            summary.append(
                {
                    "rows": rows,
                    "workload": workload,
                    "service_median_ns": medians,
                    "best_tested_sqlite": best_sqlite,
                    "refpot_speedup": medians[best_sqlite] / medians["refpot"],
                    "sqlite_relative_to_refpot": medians[best_sqlite] / medians["refpot"],
                    "regression_pct_vs_best_sqlite": max(
                        0.0, (medians["refpot"] / medians[best_sqlite] - 1.0) * 100.0
                    ),
                }
            )
    return {"records": len(records), "summary": summary, "all_verified": True}


def repository_root(start: Path) -> Path | None:
    return next(
        (
            parent
            for parent in (start.resolve(), *start.resolve().parents)
            if (parent / ".git").exists()
        ),
        None,
    )


def source_revision(start: Path) -> str | None:
    root = repository_root(start)
    if root is None:
        return None
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
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
    source_checkout = bool(
        package_root and (package_root / "src" / "refpot" / "__init__.py").resolve() == package_path
    )
    native_source = (
        package_root / "native" / "core.cpp" if source_checkout and package_root else None
    )
    if native_source is not None and not native_source.is_file():
        native_source = None
    source_revision_value = os.environ.get("REFPOT_SOURCE_REVISION")
    package_dirty = None
    if source_checkout and package_root:
        try:
            package_dirty = bool(
                subprocess.check_output(
                    ["git", "-C", str(package_root), "status", "--porcelain"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
            )
        except (OSError, subprocess.CalledProcessError):
            package_dirty = None
    return {
        "harness_source_revision": source_revision(script_path),
        "package_source_revision": source_revision_value,
        "package_source_revision_source": "REFPOT_SOURCE_REVISION"
        if source_revision_value
        else "unknown",
        "package_source_dirty": package_dirty,
        "package_source_root": str(package_root) if source_checkout else None,
        "native_source_path": str(native_source) if native_source else None,
        "source_hashes": {
            "refpot_init_py": sha256(package_path),
            "native_core_cpp": sha256(native_source) if native_source else None,
        },
        "python": sys.version,
        "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(),
        "refpot_version": package_version,
        "refpot_import_path": str(package_path),
        "native_binary_path": str(native_path),
        "native_binary_sha256": sha256(native_path),
        "harness_sha256": sha256(script_path.resolve()),
    }


def run_trial(
    root: Path, rows: int, workload: str, candidate: str, operations: int, seed: int, identity: str
) -> dict:
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
    if writes:
        warm_key = trace[0][1]
        if native:
            assert native_db is not None
            try:
                with native_db.transaction():
                    native_db.update(warm_key, value=-(1 << 63))
                    raise RuntimeError("warmup rollback")
            except RuntimeError as exc:
                if str(exc) != "warmup rollback":
                    raise
        else:
            assert sql_db is not None and statement is not None
            sql_db.execute("BEGIN IMMEDIATE")
            statement.execute(UPDATE, (-(1 << 63), warm_key))
            sql_db.execute("ROLLBACK")
            if sql_db.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()[0] != 0:
                raise AssertionError("warmup rollback checkpoint was busy")
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
            batch = trace[offset : offset + 32]
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
    wal_bytes = 0
    if native:
        assert native_db is not None
        native_db.update(0, value=probe_value)
        final_values[0] = probe_value
        wal_path = Path(str(path) + ".wal")
        wal_bytes = wal_path.stat().st_size if wal_path.exists() else 0
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
        recovery_mode = "pending_wal_replay"
        pending_reopen_validated = True
    else:
        assert statement is not None and sql_db is not None
        statement.execute(UPDATE, (probe_value, 0))
        final_values[0] = probe_value
        wal_path = Path(str(path) + "-wal")
        wal_bytes = wal_path.stat().st_size if wal_path.exists() else 0
        sql_db.close()
        threshold, locking = sql_options(candidate)
        started = time.perf_counter_ns()
        ordinary, _ = connect_sql(path, threshold, locking)
        pending_reopen_ns = None
        pending_ok = validate_sqlite(ordinary, rows, final_values)
        if ordinary.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone() != (0, 0, 0):
            raise AssertionError("close/reopen SQLite checkpoint was busy")
        ordinary.close()
        started = time.perf_counter_ns()
        clean, _ = connect_sql(path, threshold, locking)
        clean_reopen_ns = time.perf_counter_ns() - started
        clean_ok = validate_sqlite(clean, rows, final_values)
        clean.close()
        recovery_mode = "ordinary_close_reopen"
        pending_reopen_validated = None

    if not pending_ok or not clean_ok:
        raise AssertionError("reopen full-state validation failed")
    result = {
        "repeat": None,
        "rows": rows,
        "workload": workload,
        "candidate": candidate,
        "operations": operations,
        "seed": seed,
        "setup_ns": setup_ns,
        "operations_ns": operations_ns,
        "checkpoint_ns": checkpoint_ns,
        "service_ns": operations_ns + checkpoint_ns,
        "pending_wal_reopen_ns": pending_reopen_ns,
        "clean_reopen_ns": clean_reopen_ns,
        "recovery_mode": recovery_mode,
        "wal_bytes": wal_bytes,
        "full_state_validated": True,
        "pending_reopen_validated": pending_reopen_validated,
        "recovery_validated": True,
        "clean_reopen_validated": True,
        "sqlite_settings": settings,
        "verified": True,
    }
    shutil.rmtree(folder)
    return result


def create_plan(args: argparse.Namespace) -> None:
    if args.rows < 1:
        raise ValueError("rows must be positive")
    if args.operations < 32 or args.operations % 32:
        raise ValueError("operations cap must be a positive multiple of 32 (minimum 32)")
    if args.repeats < 1 or not math.isfinite(args.min_duration_ms) or args.min_duration_ms <= 0:
        raise ValueError("repeats and minimum duration must be positive")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    target_ns = int(args.min_duration_ms * 1_000_000)
    operations_by_cell = {}
    pilot_path = output / "pilot.jsonl"
    for rows in [args.rows]:
        for workload in WORKLOADS:
            count = 32
            while True:
                pilot_results = []
                for candidate in CANDIDATES:
                    result = run_trial(
                        output,
                        rows,
                        workload,
                        candidate,
                        count,
                        args.seed,
                        f"pilot-{rows}-{workload}-{count}-{candidate}",
                    )
                    result["pilot"] = True
                    append_jsonl(pilot_path, result)
                    pilot_results.append(result)
                if min(result["operations_ns"] for result in pilot_results) >= target_ns:
                    break
                if count >= args.operations:
                    raise ValueError(
                        f"pilot cap {args.operations} did not meet {args.min_duration_ms}ms for {rows}/{workload}"
                    )
                count = min(count * 2, args.operations)
            operations_by_cell[f"{rows}:{workload}"] = count
    plan = {
        "schema_version": 1,
        "rows": [args.rows],
        "operations_cap": args.operations,
        "operations_by_cell": operations_by_cell,
        "minimum_duration_ns": target_ns,
        "seed": args.seed,
        "repeats": args.repeats,
        "workloads": list(WORKLOADS),
        "candidates": list(CANDIDATES),
        "scope": "public RefPot package versus prepared SQLite; Python API screen, not native qualification",
        "environment_at_plan": environment(Path(__file__)),
    }
    plan_path = output / "plan.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "plan.sha256").write_text(sha256(plan_path) + "  plan.json\n", encoding="ascii")
    print(
        json.dumps(
            {
                "plan": str(plan_path),
                "pilot": str(pilot_path),
                "operations_by_cell": operations_by_cell,
                "trials": args.repeats * len(WORKLOADS) * len(CANDIDATES),
            },
            indent=2,
        )
    )


def read_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                record = json.loads(
                    line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value))
                )
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"invalid JSONL record at line {line_number}: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"JSONL record at line {line_number} is not an object")
            records.append(record)
    return records


def run_plan(args: argparse.Namespace) -> None:
    if args.require_speedup is not None and (
        not math.isfinite(args.require_speedup) or args.require_speedup <= 0
    ):
        raise ValueError("required speedup must be finite and positive")
    plan_path = args.plan.resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    sidecar = plan_path.with_name("plan.sha256")
    expected_hash = sidecar.read_text(encoding="ascii").split()[0]
    if sha256(plan_path) != expected_hash:
        raise ValueError("plan hash differs from plan.sha256")
    if not isinstance(plan, dict):
        raise ValueError("invalid plan dimensions")
    if (
        plan.get("schema_version") != 1
        or plan.get("workloads") != list(WORKLOADS)
        or plan.get("candidates") != list(CANDIDATES)
    ):
        raise ValueError("unsupported or modified plan schema")
    if (
        not isinstance(plan.get("rows"), list)
        or not plan["rows"]
        or any(type(rows) is not int or rows < 1 for rows in plan["rows"])
        or len(plan["rows"]) != len(set(plan["rows"]))
        or type(plan.get("operations_cap")) is not int
        or plan["operations_cap"] < 32
        or plan["operations_cap"] % 32
        or type(plan.get("repeats")) is not int
        or plan["repeats"] < 1
        or type(plan.get("seed")) is not int
        or type(plan.get("minimum_duration_ns")) is not int
        or plan["minimum_duration_ns"] < 1
    ):
        raise ValueError("invalid plan dimensions")
    expected_cells = {f"{rows}:{workload}" for rows in plan["rows"] for workload in WORKLOADS}
    operation_counts = plan.get("operations_by_cell")
    if not isinstance(operation_counts, dict) or set(operation_counts) != expected_cells:
        raise ValueError("invalid frozen operation-count dimensions")
    if any(
        type(count) is not int or count < 32 or count > plan["operations_cap"] or count % 32
        for count in operation_counts.values()
    ):
        raise ValueError("invalid frozen operation count")
    current_environment = environment(Path(__file__))
    planned_harness = plan.get("environment_at_plan", {}).get("harness_sha256")
    if planned_harness != current_environment["harness_sha256"]:
        raise ValueError("harness hash differs from the frozen plan")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(plan_path, out / "plan.json")
    shutil.copy2(sidecar, out / "plan.sha256")
    raw_path = out / "raw.jsonl"
    run_meta = {"plan_sha256": sha256(plan_path), "environment": current_environment}
    (out / "run.json").write_text(json.dumps(run_meta, indent=2) + "\n", encoding="utf-8")
    rows_values = plan["rows"]
    for repeat in range(plan["repeats"]):
        cells = [(rows, workload) for rows in rows_values for workload in plan["workloads"]]
        if repeat % 2:
            cells.reverse()
        for cell_index, (rows, workload) in enumerate(cells):
            candidates = list(plan["candidates"])
            rotate = (repeat + cell_index) % len(candidates)
            candidates = candidates[rotate:] + candidates[:rotate]
            operations = operation_counts[f"{rows}:{workload}"]
            for candidate in candidates:
                result = run_trial(
                    out,
                    rows,
                    workload,
                    candidate,
                    operations,
                    plan["seed"],
                    f"r{repeat}-{rows}-{workload}-{candidate}",
                )
                result["repeat"] = repeat
                result["candidate_order"] = candidates
                append_jsonl(raw_path, result)
    expected = {
        (repeat, rows, workload, candidate)
        for repeat in range(plan["repeats"])
        for rows in rows_values
        for workload in plan["workloads"]
        for candidate in plan["candidates"]
    }
    records = read_jsonl(raw_path)
    normalized_operations = {
        (int(key.split(":", 1)[0]), key.split(":", 1)[1]): value
        for key, value in operation_counts.items()
    }
    summary = aggregate(
        records,
        expected,
        operations_by_cell=normalized_operations,
        seed=plan["seed"],
        min_duration_ns=plan["minimum_duration_ns"],
    )
    if args.require_speedup is not None:
        selected_workloads = args.require_workload or plan["workloads"]
        selected = [
            entry for entry in summary["summary"] if entry["workload"] in selected_workloads
        ]
        failures = [entry for entry in selected if entry["refpot_speedup"] < args.require_speedup]
        summary["speedup_gate"] = {
            "threshold": args.require_speedup,
            "workloads": selected_workloads,
            "passed": not failures,
            "failed_cells": failures,
        }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(out), **summary}, indent=2))
    if args.require_speedup is not None and not summary["speedup_gate"]["passed"]:
        raise SystemExit(1)


def positive_finite_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a finite positive number") from exc
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite positive number")
    return number


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="create a frozen workload plan in a new directory")
    plan.add_argument("--output", type=Path, required=True)
    plan.add_argument("--rows", type=int, default=128)
    plan.add_argument("--operations", type=int, default=131072)
    plan.add_argument("--seed", type=int, default=918271)
    plan.add_argument("--repeats", type=int, default=3)
    plan.add_argument(
        "--min-duration-ms",
        type=float,
        default=50.0,
        help="minimum timed operation duration per candidate/cell",
    )
    plan.set_defaults(func=create_plan)
    run = commands.add_parser("run", help="execute frozen plan into a new evidence directory")
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--require-speedup", type=positive_finite_float)
    run.add_argument("--require-workload", action="append", choices=WORKLOADS)
    run.set_defaults(func=run_plan)
    return root


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
