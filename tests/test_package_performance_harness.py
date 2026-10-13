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
    assert any(len({entry[2] for entry in updates if entry[1] == key}) > 1
               for key in {entry[1] for entry in updates})
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
    result = harness.run_trial(tmp_path, rows=32, workload="update_batch32", candidate="refpot",
                              operations=32, seed=13, identity="refpot-trial")
    assert result["verified"] is True
    assert result["full_state_validated"] is True
    assert result["pending_reopen_validated"] is True
    assert result["clean_reopen_validated"] is True
    assert result["service_ns"] == result["operations_ns"] + result["checkpoint_ns"]
    assert result["checkpoint_ns"] > 0
    assert not (tmp_path / "refpot-trial").exists()


def test_plan_and_run_refuse_existing_output_directories(tmp_path: Path) -> None:
    existing = tmp_path / "evidence"
    existing.mkdir()
    args = type("Args", (), {"output": existing, "operations": 32, "repeats": 1,
                              "rows": 32, "seed": 1})()
    with pytest.raises(FileExistsError):
        harness.create_plan(args)
    assert list(existing.iterdir()) == []

    fresh_plan = tmp_path / "plan"
    harness.create_plan(type("Args", (), {"output": fresh_plan, "operations": 32,
                                           "repeats": 1, "rows": 32, "seed": 1})())
    run_output = tmp_path / "run"
    run_output.mkdir()
    run_args = type("Args", (), {"plan": fresh_plan / "plan.json", "output": run_output,
                                  "require_speedup": None, "require_workload": None})()
    with pytest.raises(FileExistsError):
        harness.run_plan(run_args)
    assert list(run_output.iterdir()) == []


def test_aggregation_rejects_missing_and_duplicate_trial_keys() -> None:
    candidates = list(harness.CANDIDATES)
    keys = [(0, 64, "point_read", candidate) for candidate in candidates]
    records = [dict(repeat=r, rows=n, workload=w, candidate=c, verified=True, service_ns=10 + i)
               for i, (r, n, w, c) in enumerate(keys)]
    expected = set(keys)
    assert harness.aggregate(records, expected)["records"] == len(candidates)
    try:
        harness.aggregate(records[:1], expected)
    except ValueError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("incomplete matrix was accepted")
    duplicate = [*records, records[0]]
    try:
        harness.aggregate(duplicate, expected)
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("duplicate trial key was accepted")
