# Package-core performance screening

This is a reproducible, public-API screening harness for the installable RefPot package. It runs real `refpot.Database` CRUD calls against SQLite's prepared statements; it does not reimplement RefPot's package core or reuse the historical fixed-schema random-update benchmark. It is a Python/package comparison, not a native-engine, physical-power-loss, or production-qualification claim.

## Run the same frozen plan on baseline and candidate

Use Python 3.11–3.14 with RefPot installed (or an editable install for a source checkout) and a system `sqlite3` module. Run the script from a directory with the desired package environment active. Output directories must be new; raw trials and pilot records are appended and fsynced individually. The harness refuses to overwrite existing plan/run directories. Interrupted output remains intact for inspection; it is not resumable, so use a new run directory to repeat.

Plan creation runs a bounded pilot for each row-count/workload cell across the five candidates. It increases operation counts in multiples of 32 until every candidate reaches `--min-duration-ms` (default 50 ms), or fails at the `--operations` cap (default 8192). The plan freezes the resulting per-cell counts and minimum duration; `--repeats` is configurable and frozen too. `pilot.jsonl` preserves the calibration observations. Small smoke runs may lower the target deliberately, but remain screening only.

```sh
python benchmarks/package-performance/harness.py plan \
  --output /path/to/evidence/plan-128-calibrated \
  --rows 128 --operations 8192 --seed 918271 --repeats 3

# Execute this exact plan once with the baseline package environment, then again
# with the candidate package environment. Keep outputs separate.
python benchmarks/package-performance/harness.py run \
  --plan /path/to/evidence/plan-128-calibrated/plan.json \
  --output /path/to/evidence/baseline
python benchmarks/package-performance/harness.py run \
  --plan /path/to/evidence/plan-128-calibrated/plan.json \
  --output /path/to/evidence/candidate
```

The plan freezes row count, per-cell operation counts, seed, repeats, minimum timed-operation duration, workload names and SQLite comparator matrix. Both runs retain its exact copy, SHA-256 sidecar and plan hash in run metadata. To compare released and changed wheels, activate the corresponding isolated environment before each invocation; inspect `run.json` to confirm `refpot_import_path`, version, package source hashes and native binary hash. `harness_sha256` must also match. The source hash map labels the `__init__.py` hash separately from available `native/core.cpp`; source revision is reported only from optional `REFPOT_SOURCE_REVISION` provenance (otherwise `null`/`unknown`), and source dirty status is reported only for a verified editable source checkout. A wheel does not inherit a revision from an unrelated enclosing `.git` directory. Do not compare runs if script or plan hashes differ.

## Workloads and fairness boundary

- `point_read`: identical seeded keys and returned `(key, value, text)` rows.
- `update_single`: successful updates to existing rows; each mutation is acknowledged before the next.
- `update_batch32`: the same successful updates grouped in explicit transactions of 32.

The seed is deterministic, values evolve on repeated keys, keys/values remain signed 64-bit integers, and text is valid UTF-8 within RefPot's 31-byte constraint. Setup/seeding cost is recorded separately. Write workloads prepare an UPDATE outside timing and roll it back before timed operations. Timed write service includes a final checkpoint (`operations_ns + checkpoint_ns`); full-state comparison, an additional untimed mutation, reopen, and clean-reopen validation are outside that service interval. RefPot records a separate pending-WAL replay probe after that mutation, including measured WAL bytes. SQLite records the WAL byte size before its last connection closes, then labels the subsequent ordinary close/reopen separately: closing the final SQLite connection may checkpoint/remove the WAL, so SQLite `pending_wal_reopen_ns` and its pending-replay validation are `null`, not a recovery comparison. Both modes validate full state and measure a later clean reopen. These process-level observations are not crash or power-loss tests.

SQLite uses a strict table with the same bounded text check, prepared/cached SELECT and UPDATE statements, WAL, `synchronous=FULL`, and read-back assertions for `fullfsync=OFF`, `checkpoint_fullfsync=OFF`, cache size, mmap, checkpoint threshold, and lock mode. Four SQLite candidates cover NORMAL and EXCLUSIVE locking with autocheckpoint thresholds 64 and 1000. `fullfsync=OFF` is an explicit setting, not proof of matched physical durability or a claim of equivalent storage guarantees. SQLite writes use autocommit for singleton updates and `BEGIN IMMEDIATE`/`COMMIT` for batches; RefPot uses its public `update` and explicit transaction APIs.

The service ratio uses the median service time for the best tested SQLite candidate divided by RefPot's median; a ratio >= 2 satisfies the optional numerical gate only for the selected workload/cells. `--require-speedup 2` fails when it does not. The report also separates regression percentage versus that SQLite comparator. A bounded screen does not establish a general performance claim, and passing this threshold alone does not qualify durability or the wider roadmap matrix.

## Integrity and output

Each raw JSONL record is flushed and fsynced after a trial; aggregation re-reads `raw.jsonl` from disk rather than trusting in-memory results. It checks the exact expected matrix, frozen operations and seed, positive finite durations, service-time arithmetic, candidate order, exact SQLite settings, all verification flags, and under-duration trials. Plan dimensions must be unique and valid; `plan.sha256` detects accidental plan edits but is not a signature against coordinated tampering. The summary rejects missing/duplicate/invalid records before computing medians. Trial database files are removed after verification, so the evidence directory contains plan and hash sidecar, calibration evidence, metadata, raw records and summary rather than generated databases.

A bounded smoke run for this checkout can use a fresh scratch directory:

```sh
python benchmarks/package-performance/harness.py plan \
  --output /path/to/scratch/refpot-screen-plan \
  --rows 64 --operations 64 --seed 918271 --repeats 1 --min-duration-ms 0.05
python benchmarks/package-performance/harness.py run \
  --plan /path/to/scratch/refpot-screen-plan/plan.json \
  --output /path/to/scratch/refpot-screen-baseline
```

This produces 15 trials (three workloads x five candidates) and is a smoke screen only. No benchmark output is checked into this directory; preserve measured evidence outside the checkout and retain unsuccessful results.
