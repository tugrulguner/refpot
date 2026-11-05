from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

RUNNER = Path(__file__).parents[1] / "research" / "transaction-deltas" / "runner.py"
spec = importlib.util.spec_from_file_location("transaction_deltas_runner", RUNNER)
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_sqlite_control_replays_full_state_and_detects_both_mutants():
    result = runner.run_control(engine="sqlite")
    assert runner.validate(result) == result["transaction_count"]
    assert result["engine"] == "sqlite"
    assert result["semantics"] == "absence-aware full-state replay"
    assert result["records"]
    assert {entry["outcome"] for record in result["records"] for entry in record["history"]} >= {
        "accept",
        "reject",
        "rollback",
    }
    for mutant in ("drop-operation", "commit-rollback"):
        with pytest.raises(
            AssertionError, match=r"(statement|transaction|final state|commit|assertion)"
        ):
            runner.run_control(engine="sqlite", mutant=mutant)


@pytest.mark.parametrize("engine", ["native-overlay", "native-modular"])
def test_native_control_matches_sqlite_and_independent_history(engine):
    native = runner.run_control(engine=engine)
    sqlite = runner.run_control(engine="sqlite")
    assert runner.validate(native) == runner.validate(sqlite)
    assert native["records"] == sqlite["records"]


def test_missing_update_is_a_successful_zero_row_statement():
    state = runner._initial()
    before = runner._oracle(state)
    assert (
        runner._apply(state, {"op": "update_fact", "id": 999, "dimension": 1, "amount": 4}) is None
    )
    assert runner._oracle(state) == before


def test_rollback_mutant_commits_a_valid_change_then_fails_state_oracle():
    with pytest.raises(AssertionError, match="transaction full-state mismatch"):
        runner.run_control(engine="sqlite", mutant="commit-rollback")


def test_sqlite_control_preserves_absence_bag_and_operation_error_cases():
    result = runner.run_control(engine="sqlite")
    cases = {entry["id"] for record in result["records"] for entry in record["history"]}
    assert {
        "dimension-delete-temporary-missing",
        "dimension-reinsert-repair",
        "missing-commit-rejected",
        "missing-row-rollback",
        "duplicate-projection-and-derived-rhs",
        "ordinary-duplicate-error",
    } <= cases
    validated = runner.validate(result)
    assert validated == result["transaction_count"]


def test_benchmark_records_measure_only_service_and_peak_rss_is_bytes(tmp_path):
    results = runner.run_performance(engines=("sqlite",), repeats=2, output_dir=tmp_path, rows=40)
    assert len(results["records"]) == 4  # two workload shapes, paired repeats
    assert all(record["service_ns"] > 0 for record in results["records"])
    assert all(record["peak_process_rss_bytes"] > 0 for record in results["records"])
    assert all(record["rss_unit"] == "bytes" for record in results["records"])
    assert all(record["setup_and_validation_timed"] is False for record in results["records"])
    assert all(Path(record["raw_path"]).exists() for record in results["records"])
