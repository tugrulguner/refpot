# Results: bounded package-SQL comparison

## Run

Executed from `/Users/tugrulguner/.hermes/worktrees/refpot-shared-change-foundation`:

```sh
python3 research/package-sql/run.py \
  --output "$HOME/.hermes/refpot-research/package-sql-comparison/qualified-final"
```

Compiler command was `c++ -std=c++17 -O2 -DNDEBUG` for baseline and the same plus `-DPACKAGE_SQL_NEW=1` for package SQL. Both compiled successfully. The runner completed 24 process runs (baseline/package × overlay/modular × sizes 32/128 × three workloads). It validated equal executed SQL sequences and equal final contents for every matching pair. All 24 confirmed visible writes (explicit-transaction read-your-writes in the repeated/growing-key workloads, autocommit visibility in CREATE workloads); the 8 growing-key runs (two controls × two modes × two sizes) verified rollback. Frozen source hashes matched the post-run hashes.

The output's `summary.json` reports all final states equal, read-your-writes true, rollback checks true, and source hashes unchanged. Exact compiler commands and all frozen hashes are in `manifest.json`.

## Allocation observations

Columns show baseline → package candidate for **global operator-new calls** and **requested bytes**, aggregated over every executed statement in that particular case (including setup and SQL verification statements). The raw artifact retains per-statement figures.

| Mode | Size | Workload | Statements per control | `operator new` calls baseline → package | Requested bytes baseline → package |
|---|---:|---|---:|---:|---:|
| overlay | 32 | repeated-key | 53 | 1,704 → 977 | 121,464 → 68,800 |
| overlay | 32 | growing-key | 81 | 5,277 → 1,457 | 339,912 → 98,648 |
| overlay | 32 | create-populated | 74 | 2,324 → 1,538 | 158,504 → 114,392 |
| overlay | 128 | repeated-key | 197 | 14,354 → 3,763 | 1,027,128 → 264,640 |
| overlay | 128 | growing-key | 273 | 62,831 → 5,203 | 3,928,776 → 353,624 |
| overlay | 128 | create-populated | 266 | 8,670 → 5,672 | 578,600 → 417,752 |
| modular | 32 | repeated-key | 53 | 3,912 → 1,970 | 211,320 → 110,536 |
| modular | 32 | growing-key | 81 | 8,745 → 2,493 | 497,704 → 144,824 |
| modular | 32 | create-populated | 74 | 4,147 → 3,457 | 236,576 → 193,232 |
| modular | 128 | repeated-key | 197 | 50,834 → 20,020 | 2,492,472 → 923,080 |
| modular | 128 | growing-key | 273 | 107,531 → 21,695 | 5,986,216 → 1,030,328 |
| modular | 128 | create-populated | 266 | 40,541 → 37,927 | 1,873,952 → 1,716,176 |
| **all matrix runs** | — | — | **1,888** | **310,870 → 106,172** | **17,452,624 → 5,436,032** |

Every workload did its own complete final-row validation before emitting output. `create-populated` also validated every row in `second` and `late`; those table contents were emitted in `final_tables` and compared pairwise by the runner. The SQL statement sequence itself was compared between controls.

## Caveats and scope

- This counts `operator new` and `operator new[]` calls and requested sizes during `Database::execute` only. It does not count direct `malloc` paths and is not RSS, peak memory, or total allocator accounting. No timing data or speed claim was collected.
- Aggregate totals include setup, mutations, read-your-writes checks, rollback checks, and final state checks. Inspect each operation in raw JSON to isolate statements; do not interpret the table as a single-operation benchmark.
- The results cover these two source snapshots, two modes, three SQL sequences, two small cardinalities, and this compiler/build configuration only.
- New SQL's `BoundPredicate` and `Aggregate` are common relational operators used by both of its modes. That shared code is common to both candidate runs; this comparison does not establish a novel-IR claim, a broad architectural advantage, or superiority over another SQL engine/product.

## Retained artifacts

All retained files are under `/Users/tugrulguner/.hermes/refpot-research/package-sql-comparison/qualified-final/`:

- `raw.jsonl` — 24 complete raw result records, with per-statement query and allocation counts.
- `aggregate.json` — Python aggregation of the raw JSON records.
- `manifest.json` — frozen source hashes, matrix, compile flags, and actual commands.
- `source-hashes-after.json` — post-run hashes.
- `summary.json` — machine-checked completion/correctness gates.
- `compile-baseline.log`, `compile-package.log` — compiler output.
