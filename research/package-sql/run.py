#!/usr/bin/env python3
"""Build a fixed before/after SQL allocation harness; keep generated evidence outside the repo."""

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCES = [
    HERE / "workload.cpp",
    HERE / "run.py",
    ROOT / "research/native-sql/sql.hpp",
    ROOT / "research/shared-change/native.hpp",
    ROOT / "native/relational/sql.hpp",
    ROOT / "native/relational/foundation.hpp",
    ROOT / "native/relational/operators.hpp",
    ROOT / "native/model/model.hpp",
]
MATRIX = [
    (mode, size, case)
    for mode in ("overlay", "modular")
    for size in (32, 128)
    for case in ("repeated-key", "growing-key", "create-populated")
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(argv, log_path):
    p = subprocess.run(
        argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120
    )
    log_path.write_text(p.stdout)
    if p.returncode:
        raise RuntimeError(
            f"command failed ({p.returncode}): {shlex.join(map(str, argv))}\n{p.stdout}"
        )
    return {
        "argv": list(map(str, argv)),
        "exit_code": p.returncode,
        "log": str(log_path),
        "output": p.stdout.strip(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    compiler = shlex.split(os.environ.get("CXX", "c++"))
    frozen = {str(p.relative_to(ROOT)): digest(p) for p in SOURCES}
    manifest = {
        "root": str(ROOT),
        "output": str(output),
        "compiler": compiler,
        "compile_flags": ["-std=c++17", "-O2", "-DNDEBUG"],
        "frozen_sha256": frozen,
        "matrix": [{"mode": m, "size": n, "case": c} for m, n, c in MATRIX],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    binaries = {}
    for control, macro in (("baseline", []), ("package", ["-DPACKAGE_SQL_NEW=1"])):
        binary = output / f"sql-{control}"
        cmd = [
            *compiler,
            "-std=c++17",
            "-O2",
            "-DNDEBUG",
            *macro,
            "-I",
            str(ROOT),
            str(HERE / "workload.cpp"),
            "-o",
            str(binary),
        ]
        result = run(cmd, output / f"compile-{control}.log")
        binaries[control] = str(binary)
        manifest.setdefault("compile", {})[control] = result
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    raw = output / "raw.jsonl"
    collected = []
    with raw.open("w") as f:
        for control, binary in binaries.items():
            for mode, size, case in MATRIX:
                proc = subprocess.run(
                    [binary, mode, str(size), case],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if proc.returncode:
                    (output / f"failure-{control}-{mode}-{size}-{case}.stderr").write_text(
                        proc.stderr
                    )
                    raise RuntimeError(f"run failed: {control} {mode} {size} {case}: {proc.stderr}")
                record = json.loads(proc.stdout)
                if record["control"] != control or not record["operations"]:
                    raise RuntimeError("bad record envelope/control")
                if not record["read_your_writes"]:
                    raise RuntimeError(
                        f"read-your-writes not confirmed: {control} {mode} {size} {case}"
                    )
                if case == "growing-key" and not record["rollback_verified"]:
                    raise RuntimeError(f"rollback not confirmed: {control} {mode} {size}")
                elif case != "growing-key" and record["rollback_verified"]:
                    raise RuntimeError("unexpected rollback flag")
                f.write(json.dumps(record, sort_keys=True) + "\n")
                f.flush()
                collected.append(record)
    # Re-read persisted records before validation and aggregation.
    collected = [json.loads(line) for line in raw.read_text().splitlines()]
    expected = {(control, mode, size, case) for control in binaries for mode, size, case in MATRIX}
    keys = [(r["control"], r["mode"], r["size"], r["case"]) for r in collected]
    if len(keys) != len(expected) or set(keys) != expected:
        raise RuntimeError("missing, duplicate, or unexpected matrix records")
    # Every control must return byte-for-byte equal final logical rows for the same mode/workload.
    lookup = {(r["control"], r["mode"], r["size"], r["case"]): r for r in collected}
    for mode, size, case in MATRIX:
        a, b = lookup[("baseline", mode, size, case)], lookup[("package", mode, size, case)]
        if a["final_tables"] != b["final_tables"]:
            raise RuntimeError(f"final state mismatch: {mode} {size} {case}")
        if [(x["sql"], x["affected"]) for x in a["operations"]] != [
            (x["sql"], x["affected"]) for x in b["operations"]
        ]:
            raise RuntimeError(f"executed SQL sequence mismatch: {mode} {size} {case}")
    # Pure-Python aggregation from persisted raw JSON, not hand-counted output.
    aggregates = []
    for mode, size, case in MATRIX:
        for control in ("baseline", "package"):
            r = lookup[(control, mode, size, case)]
            operations = r["operations"]
            aggregates.append(
                {
                    "control": control,
                    "mode": mode,
                    "size": size,
                    "case": case,
                    "executed_statements": len(operations),
                    "operator_new_calls": sum(x["new_calls"] for x in operations),
                    "requested_bytes": sum(x["requested_bytes"] for x in operations),
                    "zero_allocation_statements": sum(x["new_calls"] == 0 for x in operations),
                    "final_table_rows": {k: len(v) for k, v in r["final_tables"].items()},
                    "read_your_writes": r["read_your_writes"],
                    "rollback_verified": r["rollback_verified"],
                }
            )
    (output / "aggregate.json").write_text(json.dumps(aggregates, indent=2) + "\n")
    after = {str(p.relative_to(ROOT)): digest(p) for p in SOURCES}
    (output / "source-hashes-after.json").write_text(json.dumps(after, indent=2) + "\n")
    if after != frozen:
        raise RuntimeError("source hashes changed after freeze; results are not frozen evidence")
    summary = {
        "runs": len(collected),
        "aggregate_rows": len(aggregates),
        "all_final_states_equal": True,
        "all_read_your_writes": all(r["read_your_writes"] for r in collected),
        "all_rollbacks_verified": all(
            r["rollback_verified"] for r in collected if r["case"] == "growing-key"
        ),
        "source_hashes_unchanged": True,
        "raw_jsonl": str(raw),
        "aggregate_json": str(output / "aggregate.json"),
        "manifest": str(output / "manifest.json"),
        "source_hashes_after": str(output / "source-hashes-after.json"),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
