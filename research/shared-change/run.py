"""Reproduce native correctness and work-counter comparison without installing packages."""

import argparse
import hashlib
import itertools
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from cases import DOMAINS, ROOT, SCENARIOS, SIZES, scenario
from native_model import NativeModel
from oracle import Oracle
from sqlite_control import SQLiteControl

HERE = Path(__file__).resolve().parent


def build(destination, sanitize=False):
    compiler = os.environ.get("CXX") or shutil.which("clang++") or shutil.which("c++")
    if not compiler:
        raise RuntimeError("C++17 compiler required; no automatic installation")
    flags = ["-std=c++17", "-O1", "-g", "-Wall", "-Wextra", "-Werror"]
    if sanitize:
        flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    binaries = {}
    for mode in ("modular", "overlay"):
        path = destination / mode
        command = [compiler, *flags]
        if mode == "modular":
            command.append("-DREFPOT_MODULAR")
        subprocess.run([*command, str(HERE / "driver.cpp"), "-o", str(path)], check=True)
        binaries[mode] = path
    unit = destination / "native-tests"
    subprocess.run([compiler, *flags, str(HERE / "test_native.cpp"), "-o", str(unit)], check=True)
    return binaries, unit, compiler, flags


def qualify(binaries, unit, destination):
    env = os.environ.copy()
    env["TMPDIR"] = str(destination)
    env["REFPOT_FOUNDATION_DRIVERS"] = os.pathsep.join(map(str, binaries.values()))
    env.setdefault("ASAN_OPTIONS", "detect_leaks=0")
    env.setdefault("UBSAN_OPTIONS", "halt_on_error=1")
    commands = [[str(unit)], [sys.executable, str(HERE / "test_foundation.py"), "-v"]]
    for number, command in enumerate(commands):
        result = subprocess.run(command, env=env, text=True, capture_output=True, timeout=180)
        (destination / f"qualification-{number}.log").write_text(result.stdout + result.stderr)
        print(result.stdout + result.stderr, end="")
        result.check_returncode()


def compare(binaries, destination):
    raw_path = destination / "records.jsonl"
    with raw_path.open("x") as raw:
        for domain, size, name in itertools.product(DOMAINS, SIZES, SCENARIOS):
            spec, initial, batch = scenario(domain, size, name)
            oracle = Oracle(spec)
            sql = SQLiteControl(spec)
            try:
                for control in (oracle, sql):
                    control.apply(initial)
                    if batch is not None:
                        control.apply(batch)
                expected = oracle.snapshot()
                assert sql.snapshot() == expected
                for mode, binary in binaries.items():
                    with NativeModel(binary, spec) as native:
                        native.apply(initial)
                        initial_report = native.request("SNAPSHOT")
                        initial_stats = initial_report["stats"]
                        if batch is not None:
                            native.apply(batch)
                        report = native.request("SNAPSHOT")
                        actual = report["tables"]
                        assert actual == expected, (domain, size, name, mode)
                        assert report["epoch"] == oracle.epoch
                        record = {
                            "domain": domain,
                            "population": size,
                            "scenario": name,
                            "mode": mode,
                            "initial_stats": initial_stats,
                            "transaction_stats": report["stats"] if batch is not None else None,
                            "snapshot_exports": 2,
                            "exported_distinct_rows": sum(len(rows) for rows in actual.values()),
                            "total_exported_rows": sum(
                                len(rows)
                                for tables in (initial_report["tables"], actual)
                                for rows in tables.values()
                            ),
                            "state_sha256": hashlib.sha256(
                                json.dumps(actual, sort_keys=True).encode()
                            ).hexdigest(),
                            "epoch": report["epoch"],
                            "oracle_equal": True,
                            "sqlite_equal": True,
                        }
                        raw.write(json.dumps(record, sort_keys=True) + "\n")
                        raw.flush()
            finally:
                sql.close()
    records = [json.loads(line) for line in raw_path.read_text().splitlines()]
    expected_keys = set(itertools.product(DOMAINS, SIZES, SCENARIOS, binaries))
    keys = [(r["domain"], r["population"], r["scenario"], r["mode"]) for r in records]
    assert len(keys) == len(set(keys)) and set(keys) == expected_keys
    comparisons = []
    for domain, size, name in itertools.product(DOMAINS, SIZES, SCENARIOS):
        pair = {
            r["mode"]: r
            for r in records
            if (r["domain"], r["population"], r["scenario"]) == (domain, size, name)
        }
        assert pair["modular"]["state_sha256"] == pair["overlay"]["state_sha256"]
        row = {"domain": domain, "population": size, "scenario": name}
        row.update({mode: value["transaction_stats"] for mode, value in pair.items()})
        comparisons.append(row)
    (destination / "comparison.json").write_text(json.dumps(comparisons, indent=2) + "\n")
    print(f"Verified {len(records)} unique native matrix records against both controls")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new evidence directory")
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    os.environ["TMPDIR"] = str(output)
    # Set on the parent too: comparative driver processes must use the same sanitizer policy.
    os.environ.setdefault("ASAN_OPTIONS", "detect_leaks=0")
    os.environ.setdefault("UBSAN_OPTIONS", "halt_on_error=1")
    source_paths = sorted(HERE.glob("*.py")) + sorted(HERE.glob("*.cpp"))
    source_paths += sorted(HERE.glob("*.hpp"))
    source_paths += [
        HERE / "CONTRACT.md",
        ROOT / "native/model/model.hpp",
        ROOT / "examples/experimental_shared_change.py",
        ROOT / "tests/test_shared_change.py",
    ]
    source_paths += sorted((ROOT / "research/application-model").glob("*.py"))
    hashes = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths
    }
    binaries, unit, compiler, flags = build(output, args.sanitize)
    manifest = {
        "base_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_hashes": hashes,
        "platform": platform.platform(),
        "python": sys.version,
        "compiler": subprocess.check_output([compiler, "--version"], text=True),
        "flags": flags,
        "sanitized": args.sanitize,
        "binary_hashes": {
            name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in binaries.items()
        },
        "scope": "volatile native component work counters, not speed or database superiority",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    qualify(binaries, unit, output)
    compare(binaries, output)
    assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h for p, h in hashes.items())
    print("Sources unchanged throughout campaign; evidence:", output)


if __name__ == "__main__":
    main()
