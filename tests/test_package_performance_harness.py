from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

HARNESS_PATH = Path(__file__).parents[1] / "benchmarks" / "package-performance" / "harness.py"
spec = spec_from_file_location("package_performance_harness", HARNESS_PATH)
assert spec and spec.loader
harness = module_from_spec(spec)
spec.loader.exec_module(harness)


def test_trace_repeats_keys_and_values_change_deterministically() -> None:
    first = harness.make_trace(rows=40, operations=96, seed=27, writes=True)
    second = harness.make_trace(rows=40, operations=96, seed=27, writes=True)
    assert first == second
    updates = [entry for entry in first if entry[0] == "update"]
    assert len({entry[1] for entry in updates}) < len(updates)
    assert any(
        len({entry[2] for entry in updates if entry[1] == key}) > 1
        for key in {entry[1] for entry in updates}
    )
    assert all(-(1 << 63) <= entry[2] < (1 << 63) for entry in updates)


def test_sqlite_configuration_executes_prepared_sql_and_full_state(tmp_path: Path) -> None:
    path = tmp_path / "database.sqlite"
    db, settings = harness.connect_sql(path, checkpoint_threshold=64, locking="exclusive")
    assert settings["synchronous"] == 2
    assert settings["locking_mode"] == "exclusive"
    harness.seed_sqlite(db, rows=32)
    assert db.execute(harness.SELECT, (7,)).fetchone() == (7, 7, "row-7")
    db.execute(harness.UPDATE, (900, 7))
    assert db.execute(harness.SELECT, (7,)).fetchone() == (7, 900, "row-7")
    assert harness.validate_sqlite(db, rows=32, values={7: 900})
    db.close()


def test_trial_runs_public_refpot_and_includes_final_checkpoint(tmp_path: Path) -> None:
    result = harness.run_trial(
        tmp_path,
        rows=32,
        workload="update_batch32",
        candidate="refpot",
        operations=32,
        seed=13,
        identity="refpot-trial",
    )
    assert result["verified"] is True
    assert result["full_state_validated"] is True
    assert result["pending_reopen_validated"] is True
    assert result["recovery_mode"] == "pending_wal_replay"
    assert result["wal_bytes"] > 0
    assert result["clean_reopen_validated"] is True
    assert result["service_ns"] == result["operations_ns"] + result["checkpoint_ns"]
    assert result["checkpoint_ns"] > 0
    assert not (tmp_path / "refpot-trial").exists()


def test_plan_and_run_refuse_existing_output_directories(tmp_path: Path) -> None:
    existing = tmp_path / "evidence"
    existing.mkdir()
    args = type(
        "Args",
        (),
        {
            "output": existing,
            "operations": 32,
            "repeats": 1,
            "rows": 32,
            "seed": 1,
            "min_duration_ms": 0.000001,
        },
    )()
    with pytest.raises(FileExistsError):
        harness.create_plan(args)
    assert list(existing.iterdir()) == []

    fresh_plan = tmp_path / "plan"
    harness.create_plan(
        type(
            "Args",
            (),
            {
                "output": fresh_plan,
                "operations": 32,
                "repeats": 1,
                "rows": 32,
                "seed": 1,
                "min_duration_ms": 0.000001,
            },
        )()
    )
    run_output = tmp_path / "run"
    run_output.mkdir()
    run_args = type(
        "Args",
        (),
        {
            "plan": fresh_plan / "plan.json",
            "output": run_output,
            "require_speedup": None,
            "require_workload": None,
        },
    )()
    with pytest.raises(FileExistsError):
        harness.run_plan(run_args)
    assert list(run_output.iterdir()) == []


@pytest.mark.parametrize("threshold", ["nan", "inf", "-inf", "0", "-0.5"])
def test_speedup_gate_rejects_nonpositive_or_nonfinite_before_output(
    tmp_path: Path, threshold: str
) -> None:
    output = tmp_path / "must-not-exist"
    with pytest.raises(SystemExit):
        harness.parser().parse_args(
            [
                "run",
                "--plan",
                str(tmp_path / "missing-plan.json"),
                "--output",
                str(output),
                "--require-speedup",
                threshold,
            ]
        )
    assert not output.exists()
    args = type(
        "Args",
        (),
        {
            "plan": tmp_path / "missing-plan.json",
            "output": output,
            "require_speedup": float(threshold),
        },
    )()
    with pytest.raises(ValueError, match="finite and positive"):
        harness.run_plan(args)
    assert not output.exists()


def test_speedup_gate_accepts_positive_threshold_and_plan_cap_is_usable() -> None:
    args = harness.parser().parse_args(
        ["run", "--plan", "plan.json", "--output", "run", "--require-speedup", "2"]
    )
    assert args.require_speedup == 2.0
    plan_args = harness.parser().parse_args(["plan", "--output", "plan"])
    assert plan_args.operations == 131072


def test_sqlite_reopen_is_labeled_ordinary_not_pending_wal_replay(tmp_path: Path) -> None:
    result = harness.run_trial(
        tmp_path,
        rows=32,
        workload="update_single",
        candidate="sqlite64_normal",
        operations=32,
        seed=13,
        identity="sqlite-trial",
    )
    assert result["wal_bytes"] > 0
    assert result["recovery_mode"] == "ordinary_close_reopen"
    assert result["pending_wal_reopen_ns"] is None
    assert result["pending_reopen_validated"] is None
    assert result["recovery_validated"] is True


def test_plan_hash_detects_accidental_plan_edit(tmp_path: Path) -> None:
    plan_dir = tmp_path / "plan"
    harness.create_plan(
        type(
            "Args",
            (),
            {
                "output": plan_dir,
                "operations": 32,
                "repeats": 1,
                "rows": 32,
                "seed": 1,
                "min_duration_ms": 0.000001,
            },
        )()
    )
    plan_path = plan_dir / "plan.json"
    plan_path.write_text(plan_path.read_text().replace('"seed": 1', '"seed": 2'))
    run_args = type(
        "Args",
        (),
        {
            "plan": plan_path,
            "output": tmp_path / "run",
            "require_speedup": None,
            "require_workload": None,
        },
    )()
    with pytest.raises(ValueError, match="plan hash"):
        harness.run_plan(run_args)


def valid_records():
    keys = [(0, 64, "point_read", candidate) for candidate in harness.CANDIDATES]
    records = []
    for repeat, rows, workload, candidate in keys:
        settings = None
        recovery_mode = "pending_wal_replay"
        pending_ns = 5
        pending_validated = True
        if candidate != "refpot":
            threshold, locking = harness.sql_options(candidate)
            settings = dict(
                synchronous=2,
                fullfsync=0,
                checkpoint_fullfsync=0,
                cache_size=-2000,
                wal_autocheckpoint=threshold,
                mmap_size=0,
                locking_mode=locking,
            )
            recovery_mode = "ordinary_close_reopen"
            pending_ns = None
            pending_validated = None
        records.append(
            dict(
                repeat=repeat,
                rows=rows,
                workload=workload,
                candidate=candidate,
                operations=32,
                seed=7,
                setup_ns=1,
                operations_ns=20,
                checkpoint_ns=2,
                service_ns=22,
                pending_wal_reopen_ns=pending_ns,
                clean_reopen_ns=5,
                recovery_mode=recovery_mode,
                wal_bytes=128,
                full_state_validated=True,
                pending_reopen_validated=pending_validated,
                clean_reopen_validated=True,
                recovery_validated=True,
                candidate_order=list(harness.CANDIDATES),
                sqlite_settings=settings,
                verified=True,
            )
        )
    return records, set(keys)


def test_aggregation_uses_exact_persisted_contract():
    records, expected = valid_records()
    args = dict(operations_by_cell={(64, "point_read"): 32}, seed=7, min_duration_ns=10)
    assert harness.aggregate(records, expected, **args)["records"] == len(harness.CANDIDATES)
    with pytest.raises(ValueError, match="matrix mismatch"):
        harness.aggregate(records[:-1], expected, **args)
    with pytest.raises(ValueError, match="duplicate"):
        harness.aggregate([*records, records[0]], expected, **args)


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("operations", 64, "operations or seed"),
        ("seed", 9, "operations or seed"),
        ("service_ns", 99, "service time"),
        ("operations_ns", float("nan"), "invalid or negative trial integer"),
        ("checkpoint_ns", -1, "negative"),
        ("verified", False, "unverified"),
        ("sqlite_settings", {}, "unverified SQLite settings"),
    ],
)
def test_aggregation_rejects_structurally_invalid_records(field, value, match):
    records, expected = valid_records()
    records[1 if field == "sqlite_settings" else 0][field] = value
    with pytest.raises(ValueError, match=match):
        harness.aggregate(
            records,
            expected,
            operations_by_cell={(64, "point_read"): 32},
            seed=7,
            min_duration_ns=10,
        )


def test_aggregation_rejects_under_duration_trials():
    records, expected = valid_records()
    records[0]["operations_ns"] = 9
    records[0]["service_ns"] = 11
    with pytest.raises(ValueError, match="minimum duration"):
        harness.aggregate(
            records,
            expected,
            operations_by_cell={(64, "point_read"): 32},
            seed=7,
            min_duration_ns=10,
        )
