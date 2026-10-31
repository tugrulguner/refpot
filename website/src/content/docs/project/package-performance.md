---
title: Package performance results
description: Canonical RefPot guidance and evidence with explicit scope.
---

This screen used **locally built wheels carrying `0.1.1` version metadata** to compare the transaction-staging/recovery change at the source revisions pinned below. These are not measurements of the published PyPI 0.1.1 wheel or of v0.1.2 release artifacts. All results are a single-host, warm-cache public-Python API screen; the broader product target is not met.

## Recomputed result matrix

Each time is median end-to-end service time in milliseconds (operations plus final checkpoint; read workloads have no checkpoint), from five raw repeats. “SQLite” is the fastest median among the four measured SQLite configurations in the **candidate** campaign. Speedup is SQLite median / candidate RefPot median. The eligibility column marks whether that cell reaches the 2× screen target.

| Rows | Workload | Ops/repeat | Baseline RefPot ms | Candidate RefPot ms | Old→new | Strongest SQLite | SQLite ms | Candidate vs SQLite | 2× cell |
|---:|---|---:|---:|---:|---:|---|---:|---:|:---:|
| 1,000 | Point reads | 16,384 | 21.600 | 21.985 | 0.98× | EXCLUSIVE, WAL autocheckpoint 1000 | 60.393 | 2.75× | PASS |
| 1,000 | Singleton updates | 1,024 | 141.796 | 30.117 | 4.71× | EXCLUSIVE, WAL autocheckpoint 64 | 37.151 | 1.23× | FAIL |
| 1,000 | Batch-32 updates | 16,384 | 957.276 | 39.698 | 24.11× | EXCLUSIVE, WAL autocheckpoint 64 | 47.718 | 1.20× | FAIL |
| 10,000 | Point reads | 16,384 | 24.086 | 23.964 | 1.01× | EXCLUSIVE, WAL autocheckpoint 1000 | 62.329 | 2.60× | PASS |
| 10,000 | Singleton updates | 1,024 | 1,722.642 | 32.277 | 53.37× | EXCLUSIVE, WAL autocheckpoint 64 | 36.078 | 1.12× | FAIL |
| 10,000 | Batch-32 updates | 8,192 | 5,133.725 | 24.840 | 206.67× | EXCLUSIVE, WAL autocheckpoint 1000 | 54.729 | 2.20× | PASS |

The global ≥2× SQLite goal **fails**: three of six cells miss, including both singleton-update cells and the 1,000-row batch cell. Large old→new ratios primarily remove pathological full-map copying/diffing work; they are not general database-speed claims. Point-read performance is essentially unchanged across package revisions; point-read wins against SQLite do **not** come from the mutation-path fix.

### Separate recovery diagnostic

Three repeats per label/count (12 raw records total), same 10,000-row checkpointed fixture, repeated updates to one key. The timed measurement is ordinary close followed by reopen and recovery; full-state validation is outside timing. This is warm-filesystem RefPot-only evidence, **not** a SQLite comparison or crash/power-loss test.

| Pending transactions | Baseline median reopen ms | Candidate median reopen ms | Old→new |
|---:|---:|---:|---:|
| 128 | 78.794 | 4.546 | 17.33× |
| 1,024 | 607.873 | 5.694 | 106.76× |

## Protocol and provenance

Browse the [complete raw evidence and frozen plans](https://github.com/tugrulguner/refpot/tree/1b6f850613936591f13a04bf7ddd17505cc9e219/benchmarks/package-performance/evidence), [SHA-256 manifest](https://github.com/tugrulguner/refpot/blob/1b6f850613936591f13a04bf7ddd17505cc9e219/benchmarks/package-performance/evidence/manifest.json), and [portable offline verifier](https://github.com/tugrulguner/refpot/blob/1b6f850613936591f13a04bf7ddd17505cc9e219/benchmarks/package-performance/verify_evidence.py). The retained files include every measured configuration, not just the winning cells.

- Baseline engine: `6cc633fac687dbdbfab211507b3d87caa5ffcd82`.
- Candidate engine: `e784db03cf797518ec852a19e73202311eabce7f`.
- Frozen harness: `88626e10db9190b77ac0e46c1a3f05dfa5613ace`, SHA-256 `13b91cacfd57ecf53f531495a3625b60111bcfd5ff6e47bb280f63ec850d613e` (included at `evidence/frozen-harness.py`).
- Both engine artifacts were version `0.1.1` wheels. Environment: macOS 26.5.2 arm64, Python 3.14.7, SQLite 3.53.1. `run.json` retains the installed import paths, binary SHA-256, package `__init__.py` hash, version, and operator-supplied `REFPOT_SOURCE_REVISION` label for each campaign. These are extension hashes, not wheel hashes; `native_core_cpp` is null in these installed-wheel runs. The archived revision label is not a verified source-to-artifact attestation. Original local paths are retained as provenance only; neither the offline verifier nor evidence file resolution depends on those paths.
- Two frozen row-count plans, seed `918271`, five repeats, all three workloads, all five backends. Minimum timed operations duration: 20,000,000 ns (20 ms). Each baseline/candidate pair uses identical plan bytes, operation counts, seed and harness. Plan SHA-256 (both campaigns): 1,000 rows `c4c579af8ccf1dfbb6838ad38753e9795cdbd2274db625dccf7ee53f106c8761`; 10,000 rows `f7502b91c516c403f6a1350735dea30e6ca54213876e990efc625d09ce8faae5`.
- The campaigns were measured separately, not alternated baseline/candidate by repeat. Pilot traces, all 300 screen trials, both sides' recovery records, run environments, frozen plans/sidecars, prior summaries/comparison, and source verification materials are preserved under `evidence/`. `evidence/manifest.json` pins every other evidence file's SHA-256.
- SQLite used actual parameterized cached statements, WAL/FULL, and EXCLUSIVE locking for the selected strongest comparison. The tested SQLite PRAGMAs were read back; configurations varied WAL autocheckpoint between 64/1000 and locking NORMAL/EXCLUSIVE. RefPot timed write service includes final checkpoint; separate recovery validation is not pooled into these timings.

### Limits

This is a warm-cache macOS screen with a 20 ms timing floor, separate engine campaigns, and no physical power-loss testing or cross-platform/native qualification. It is not proof of power-failure durability, syscall equivalence, larger-than-memory behavior, concurrency, sustained maintenance-threshold behavior, or mixed/insert/delete workload performance. SQLite `fullfsync` and `checkpoint_fullfsync` were OFF. The recovery probe is ordinary close/reopen, not forced crash recovery. Do not pool these results with earlier prototype/review screens or call them v0.1.2 results.

## Offline integrity verification

From any checkout/copy with Python 3.10+ (stdlib only; no package import, original scratch directory, SQLite extension, or network required):

```sh
python3 benchmarks/package-performance/verify_evidence.py
```

The verifier checks the evidence manifest and all file hashes; sidecars and plan pairing; recorded source-revision labels, harness/version identities; the full trial and pilot matrices; calibration counts and 20 ms floor; timing arithmetic and validation flags; SQLite settings/recovery-mode claims; recovery rows; and independently recomputed per-cell medians, strongest SQLite selection and ratios. Expected verified counts: 300 raw trial records and 12 recovery records. To validate an isolated copy, use `--evidence-dir PATH/TO/evidence`.

## Reproduce as a new campaign

The frozen harness is the exact hashed harness used for the existing evidence, but **running it creates new measurements**; it does not reproduce the historical timings. Build/install two isolated wheels from the exact source revisions above and confirm each installed `refpot` version/import path/binary hash before timing. With the corresponding build environments active, run separately and into fresh output directories:

```sh
python benchmarks/package-performance/evidence/frozen-harness.py run \
  --plan benchmarks/package-performance/evidence/baseline1000/plan.json \
  --output /absolute/path/to/new-baseline-1000
python benchmarks/package-performance/evidence/frozen-harness.py run \
  --plan benchmarks/package-performance/evidence/baseline10000/plan.json \
  --output /absolute/path/to/new-baseline-10000
# Repeat with candidate1000/candidate10000 plans in the candidate wheel environment.
```

The run command requires its adjacent `plan.sha256` sidecar. Set `REFPOT_SOURCE_REVISION` to the exact engine revision used to build each installed wheel; the harness otherwise cannot infer a checkout identity from an installed binary. Do not change plan or harness contents and call the result the same campaign. Run metadata records the installed extension and `__init__.py` hashes plus the declared source revision, not wheel archive hashes or an independently verified build-to-source link. The offline verifier checks recorded labels and evidence consistency; it cannot reconstruct missing build provenance. Rebuilding may produce different binaries and newly measured results.

To repeat the recovery diagnostic, create its deterministic logical fixture with the installed candidate wheel, then run the archived probe separately with each wheel environment. Replace the output paths with new directories. `TMPDIR` must name an existing writable scratch directory. The original fixture bytes were not retained in this evidence bundle; this recreates the same row contents, not the historical artifact or timings.

```sh
python benchmarks/package-performance/recovery_fixture.py /absolute/path/to/new-fixture.rp
python benchmarks/package-performance/evidence/provenance/pr-recovery-comparison.py \
  --fixture /absolute/path/to/new-fixture.rp \
  --output /absolute/path/to/new-candidate-recovery.jsonl --label candidate
# Run the same probe with the baseline wheel, a new output path and --label baseline.
```

The frozen provenance scripts preserve their original local paths and context. Use the portable offline verifier above for the retained evidence; the old `verify-pr-evidence.py` is an archival record, not the current verification entry point.

[Download this page as Markdown](/docs/project-package-performance.md)
