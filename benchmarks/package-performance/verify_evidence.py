#!/usr/bin/env python3
"""Offline integrity and semantic verifier for the published package screen."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence"
EXPECTED_COMMITS = {
    "baseline": "6cc633fac687dbdbfab211507b3d87caa5ffcd82",
    "candidate": "e784db03cf797518ec852a19e73202311eabce7f",
    "harness": "88626e10db9190b77ac0e46c1a3f05dfa5613ace",
}
WORKLOADS = ["point_read", "update_single", "update_batch32"]
CANDIDATES = [
    "refpot", "sqlite64_normal", "sqlite1000_normal",
    "sqlite64_exclusive", "sqlite1000_exclusive",
]


def fail(message: str) -> None:
    raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda x: fail(f"invalid JSON constant {x}"))


def read_jsonl(path: Path) -> list[dict]:
    records = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            value = json.loads(line, parse_constant=lambda x: fail(f"invalid JSON constant {x}"))
        except (json.JSONDecodeError, ValueError) as exc:
            fail(f"{path.name}:{number}: invalid JSONL: {exc}")
        if not isinstance(value, dict):
            fail(f"{path.name}:{number}: expected object")
        records.append(value)
    return records


def verify_manifest() -> dict:
    manifest_path = EVIDENCE / "manifest.json"
    manifest = read_json(manifest_path)
    if manifest.get("schema_version") != 1:
        fail("unsupported manifest schema")
    expected = manifest.get("files")
    if not isinstance(expected, dict) or not expected:
        fail("manifest files map missing")
    actual_paths = {
        path.relative_to(EVIDENCE).as_posix()
        for path in EVIDENCE.rglob("*") if path.is_file() and path != manifest_path
    }
    if actual_paths != set(expected):
        fail(f"manifest file set mismatch: missing={sorted(set(expected)-actual_paths)}, extra={sorted(actual_paths-set(expected))}")
    for name, checksum in expected.items():
        path = EVIDENCE / name
        if not isinstance(checksum, str) or digest(path) != checksum:
            fail(f"SHA-256 mismatch: {name}")
    if manifest.get("source_commits") != EXPECTED_COMMITS:
        fail("source commit identities mismatch")
    if manifest.get("measured_package_version") != "0.1.1":
        fail("evidence must remain labeled as pre-release 0.1.1 measurements")
    if digest(EVIDENCE / "frozen-harness.py") != manifest.get("frozen_harness_sha256"):
        fail("frozen harness does not match recorded hash")
    return manifest


def validate_trial(record: dict, *, label: str, rows: int, workload: str,
                   repeat: int, plan: dict, order: list[str]) -> None:
    key = (repeat, rows, workload, label)
    for field in ("repeat", "rows", "operations", "seed", "setup_ns", "operations_ns", "checkpoint_ns", "service_ns", "clean_reopen_ns", "wal_bytes"):
        value = record.get(field)
        if type(value) is not int or value < 0:
            fail(f"{key}: invalid {field}")
    if (record["repeat"], record["rows"], record["workload"]) != (repeat, rows, workload) or record.get("candidate") not in CANDIDATES:
        fail(f"{key}: trial identity mismatch")
    backend = record["candidate"]
    count = plan["operations_by_cell"][f"{rows}:{workload}"]
    if record["operations"] != count or record["seed"] != plan["seed"]:
        fail(f"{key}: plan operation count/seed mismatch")
    for field in ("operations_ns", "service_ns", "clean_reopen_ns"):
        value = record[field]
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            fail(f"{key}: invalid {field}")
    if record["operations_ns"] < plan["minimum_duration_ns"]:
        fail(f"{key}: below frozen timing floor")
    if record["service_ns"] != record["operations_ns"] + record["checkpoint_ns"]:
        fail(f"{key}: service time arithmetic mismatch")
    if record.get("candidate_order") != order or backend not in order:
        fail(f"{key}: candidate order mismatch")
    if any(record.get(flag) is not True for flag in (
        "verified", "full_state_validated", "recovery_validated", "clean_reopen_validated"
    )):
        fail(f"{key}: validation flag false/missing")
    if backend == "refpot":
        if record.get("sqlite_settings") is not None:
            fail(f"{key}: RefPot has SQLite settings")
        if record.get("recovery_mode") != "pending_wal_replay":
            fail(f"{key}: incorrect RefPot recovery mode")
        pending = record.get("pending_wal_reopen_ns")
        if type(pending) not in (int, float) or not math.isfinite(pending) or pending <= 0 or record.get("pending_reopen_validated") is not True:
            fail(f"{key}: invalid pending WAL validation")
    else:
        threshold = 64 if "64" in backend else 1000
        locking = "exclusive" if backend.endswith("exclusive") else "normal"
        settings = dict(synchronous=2, fullfsync=0, checkpoint_fullfsync=0,
                        cache_size=-2000, wal_autocheckpoint=threshold,
                        mmap_size=0, locking_mode=locking)
        if record.get("sqlite_settings") != settings:
            fail(f"{key}: SQLite settings mismatch")
        if record.get("recovery_mode") != "ordinary_close_reopen" or record.get("pending_wal_reopen_ns") is not None or record.get("pending_reopen_validated") is not None:
            fail(f"{key}: SQLite close/reopen misrepresented as pending WAL replay")


def main() -> int:
    global EVIDENCE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, default=EVIDENCE,
                        help="evidence folder (useful for disposable-copy corruption tests)")
    args = parser.parse_args()
    EVIDENCE = args.evidence_dir.resolve()
    manifest = verify_manifest()
    plans = {}
    series: dict[str, dict[int, list[dict]]] = {"baseline": {}, "candidate": {}}
    all_raw = []
    for rows in (1000, 10000):
        plan_hashes = []
        for label in ("baseline", "candidate"):
            folder = EVIDENCE / f"{label}{rows}"
            plan_path = folder / "plan.json"
            plan = read_json(plan_path)
            sidecar = (folder / "plan.sha256").read_text(encoding="ascii").split()
            if len(sidecar) != 2 or sidecar[0] != digest(plan_path) or sidecar[1] != "plan.json":
                fail(f"{label}{rows}: frozen plan sidecar mismatch")
            if plan.get("rows") != [rows] or plan.get("workloads") != WORKLOADS or plan.get("candidates") != CANDIDATES:
                fail(f"{label}{rows}: unexpected plan dimensions")
            if plan.get("repeats") != 5 or plan.get("seed") != 918271 or plan.get("minimum_duration_ns") != 20_000_000:
                fail(f"{label}{rows}: frozen plan settings changed")
            env_plan = plan.get("environment_at_plan", {})
            if env_plan.get("harness_sha256") != manifest["frozen_harness_sha256"]:
                fail(f"{label}{rows}: harness identity mismatch")
            run = read_json(folder / "run.json")
            if run.get("plan_sha256") != digest(plan_path):
                fail(f"{label}{rows}: run plan hash mismatch")
            env = run.get("environment", {})
            if env.get("harness_sha256") != manifest["frozen_harness_sha256"] or env.get("harness_source_revision") != EXPECTED_COMMITS["harness"]:
                fail(f"{label}{rows}: run harness source identity mismatch")
            expected_package_commit = EXPECTED_COMMITS[label]
            if env.get("package_source_revision") != expected_package_commit or env.get("package_source_revision_source") != "REFPOT_SOURCE_REVISION":
                fail(f"{label}{rows}: package source revision mismatch")
            if env.get("refpot_version") != "0.1.1":
                fail(f"{label}{rows}: not a 0.1.1 measurement")
            if not env.get("native_binary_sha256") or not env.get("source_hashes", {}).get("refpot_init_py"):
                fail(f"{label}{rows}: missing installed artifact/source hashes")
            plan_hashes.append(digest(plan_path))
            plans[(label, rows)] = plan
            raw = read_jsonl(folder / "raw.jsonl")
            if len(raw) != 75:
                fail(f"{label}{rows}: expected 75 trial records, got {len(raw)}")
            observed = set()
            for record in raw:
                repeat = record.get("repeat")
                workload = record.get("workload")
                if type(repeat) is not int or workload not in WORKLOADS:
                    fail(f"{label}{rows}: invalid trial key")
                key = (repeat, rows, workload, record.get("candidate"))
                if key in observed:
                    fail(f"{label}{rows}: duplicate trial {key}")
                observed.add(key)
                cell_index = (0 if workload == "point_read" else 1 if workload == "update_single" else 2)
                if repeat % 2:
                    cell_index = 2 - cell_index
                rotated = (repeat + cell_index) % len(CANDIDATES)
                order = CANDIDATES[rotated:] + CANDIDATES[:rotated]
                validate_trial(record, label=label, rows=rows, workload=workload,
                               repeat=repeat, plan=plan, order=order)
            expected = {(repeat, rows, workload, candidate)
                        for repeat in range(5) for workload in WORKLOADS for candidate in CANDIDATES}
            if observed != expected:
                fail(f"{label}{rows}: trial matrix mismatch")
            series[label][rows] = raw
            all_raw.extend((label, rows, record) for record in raw)
        if plan_hashes[0] != plan_hashes[1]:
            fail(f"{rows}: baseline/candidate frozen plans differ")

    table = []
    for rows in (1000, 10000):
        plan = plans[("candidate", rows)]
        for workload in WORKLOADS:
            base = [r["service_ns"] for r in series["baseline"][rows] if r["workload"] == workload and r["candidate"] == "refpot"]
            cand = [r["service_ns"] for r in series["candidate"][rows] if r["workload"] == workload and r["candidate"] == "refpot"]
            sqlite_medians = {name: statistics.median(r["service_ns"] for r in series["candidate"][rows] if r["workload"] == workload and r["candidate"] == name) for name in CANDIDATES if name != "refpot"}
            best = min(sqlite_medians, key=sqlite_medians.get)
            old_ms = statistics.median(base) / 1e6
            new_ms = statistics.median(cand) / 1e6
            best_ms = sqlite_medians[best] / 1e6
            table.append({
                "rows": rows, "workload": workload,
                "operations": plan["operations_by_cell"][f"{rows}:{workload}"],
                "baseline_ms": old_ms, "candidate_ms": new_ms,
                "improvement_over_baseline": old_ms / new_ms,
                "best_sqlite": best, "best_sqlite_ms": best_ms,
                "candidate_over_sqlite_speedup": best_ms / new_ms,
                "baseline_repeats": len(base), "candidate_repeats": len(cand),
            })

    # Pilots are retained and semantically checked as part of the frozen calibration.
    for rows in (1000, 10000):
        pilot = read_jsonl(EVIDENCE / f"plan{rows}" / "pilot.jsonl")
        final_counts = plans[("candidate", rows)]["operations_by_cell"]
        for workload in WORKLOADS:
            group = [r for r in pilot if r.get("workload") == workload]
            if not group or len(group) % len(CANDIDATES):
                fail(f"{rows}/{workload}: incomplete pilot batches")
            counts = []
            for offset in range(0, len(group), len(CANDIDATES)):
                batch = group[offset:offset + len(CANDIDATES)]
                count_values = {r.get("operations") for r in batch}
                names = {r.get("candidate") for r in batch}
                if len(count_values) != 1 or names != set(CANDIDATES):
                    fail(f"{rows}/{workload}: malformed pilot batch")
                count = next(iter(count_values))
                counts.append(count)
                for r in batch:
                    if r.get("rows") != rows or r.get("seed") != 918271 or r.get("pilot") is not True:
                        fail(f"{rows}/{workload}: pilot identity mismatch")
                    if any(r.get(flag) is not True for flag in ("verified", "full_state_validated", "recovery_validated", "clean_reopen_validated")):
                        fail(f"{rows}/{workload}: pilot validation missing")
                    if r.get("service_ns") != r.get("operations_ns") + r.get("checkpoint_ns"):
                        fail(f"{rows}/{workload}: pilot service arithmetic mismatch")
                    if r["candidate"] == "refpot":
                        if r.get("sqlite_settings") is not None or r.get("recovery_mode") != "pending_wal_replay" or r.get("pending_reopen_validated") is not True:
                            fail(f"{rows}/{workload}: pilot RefPot recovery/settings mismatch")
                    else:
                        threshold = 64 if "64" in r["candidate"] else 1000
                        locking = "exclusive" if r["candidate"].endswith("exclusive") else "normal"
                        expected_settings = dict(synchronous=2, fullfsync=0, checkpoint_fullfsync=0, cache_size=-2000, wal_autocheckpoint=threshold, mmap_size=0, locking_mode=locking)
                        if r.get("sqlite_settings") != expected_settings or r.get("recovery_mode") != "ordinary_close_reopen":
                            fail(f"{rows}/{workload}: pilot SQLite settings/recovery mismatch")
            if counts[-1] != final_counts[f"{rows}:{workload}"] or any(a * 2 != b for a, b in zip(counts, counts[1:])):
                fail(f"{rows}/{workload}: pilot count escalation differs from frozen plan")
            final_batch = group[-len(CANDIDATES):]
            if min(r["operations_ns"] for r in final_batch) < plans[("candidate", rows)]["minimum_duration_ns"]:
                fail(f"{rows}/{workload}: final pilot did not meet timing floor")
            if len(counts) > 1 and min(r["operations_ns"] for r in group[-2 * len(CANDIDATES):-len(CANDIDATES)]) >= plans[("candidate", rows)]["minimum_duration_ns"]:
                fail(f"{rows}/{workload}: calibration did not stop at first passing count")

    recovery = []
    for label in ("baseline", "candidate"):
        recovery += read_jsonl(EVIDENCE / f"recovery-{label}.jsonl")
    expected_recovery = {(label, repeat, tx) for label in ("baseline", "candidate") for repeat in range(3) for tx in (128, 1024)}
    observed_recovery = set()
    for row in recovery:
        key = (row.get("label"), row.get("repeat"), row.get("transactions"))
        if key in observed_recovery or key not in expected_recovery:
            fail(f"duplicate/unexpected recovery record: {key}")
        observed_recovery.add(key)
        if row.get("rows") != 10000 or row.get("verified") is not True or type(row.get("wal_bytes")) is not int or row["wal_bytes"] <= 0 or type(row.get("reopen_ns")) is not int or row["reopen_ns"] <= 0:
            fail(f"invalid recovery record: {key}")
    if observed_recovery != expected_recovery:
        fail("recovery matrix incomplete")
    recovery_table = []
    for tx in (128, 1024):
        medians = {label: statistics.median(row["reopen_ns"] for row in recovery if row["label"] == label and row["transactions"] == tx) / 1e6 for label in ("baseline", "candidate")}
        recovery_table.append({"transactions": tx, "baseline_ms": medians["baseline"], "candidate_ms": medians["candidate"], "improvement": medians["baseline"] / medians["candidate"], "records_each": 3})

    result = {
        "status": "PASS", "files_verified": len(manifest["files"]),
        "trial_records": len(all_raw), "recovery_records": len(recovery),
        "matrix": table, "recovery": recovery_table,
        "global_2x_sqlite_goal_met": all(row["candidate_over_sqlite_speedup"] >= 2 for row in table),
        "measured_package_version": manifest["measured_package_version"],
        "source_commits": EXPECTED_COMMITS,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"evidence verification FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
