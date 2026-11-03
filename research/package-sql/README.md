# Package SQL source-work comparison

This is a bounded, reproducible comparison of the retained local SQL research implementation `research/native-sql/sql.hpp` against `native/relational/sql.hpp`. It measures **C++ `operator new` activity around executed SQL statements**, not wall-clock time. It does not establish a speed claim or a general advantage over other databases/architectures.

## Reproduce

From the repository root, with Python 3 and a C++17 compiler available as `c++`:

```sh
python3 research/package-sql/run.py \
  --output "$HOME/.hermes/refpot-research/package-sql-comparison/run-NEW"
```

`run-NEW` must not exist. The runner snapshots SHA-256 hashes of the workload, runner, both SQL headers, their foundation/operators headers, and the model header before compiling; it records compiler commands and checks these hashes again after execution. It builds exactly two binaries from the same workload translation unit: baseline include by default and candidate include with `-DPACKAGE_SQL_NEW=1`. Both use `-std=c++17 -O2 -DNDEBUG`.

The matrix is 2 controls × 2 storage modes (`overlay`, `modular`) × sizes 32 and 128 × 3 workloads, or 24 process runs. Each pair receives the same SQL sequence; the runner checks SQL sequence equality and checks the entire final table state equality between baseline and package candidate.

- `repeated-key`: seed `size` rows, BEGIN, repeatedly UPDATE key 1 (16 updates at 32 rows, 64 at 128), SELECT the changed value inside the transaction, COMMIT, then verify every row.
- `growing-key`: seed rows, BEGIN, insert `size` new keys, SELECT COUNT inside the transaction, COMMIT; then insert eight more rows in a second explicit transaction, verify the in-transaction count, ROLLBACK, and verify the committed state.
- `create-populated`: populate `records` and `second`, CREATE a third table after both are populated, insert and read its row, and exactly verify all table contents. This covers catalog growth after population.

Counters are enabled only during `Database::execute`; each raw record contains per-statement `new_calls` and `requested_bytes`. Final-state verification and read-your-writes checks execute real SQL. The runner persists raw JSON first, then aggregates from that JSON in Python.

## Evidence and interpretation

See [RESULTS.md](RESULTS.md) for the completed run, exact command, totals, and per-workload counts. Raw evidence and manifests are included in [`evidence/`](evidence/) and retained externally at:

`$HOME/.hermes/refpot-research/package-sql-comparison/qualified-final/`

The count is global `operator new`/`operator new[]` calls and the requested sizes passed to those operators in this process. It is not RSS, peak memory, total `malloc` calls/bytes, or complete process allocation accounting; direct allocator calls that bypass these operators are not included. Counts include all SQL statements in the specified workload, including setup and SQL state checks; the raw JSON preserves each statement separately. No timings are collected.

Both storage modes use the same SQL/operator implementation within each header candidate. The new SQL path shares the typed `BoundPredicate` and `Aggregate` operators in `native/relational/operators.hpp` across overlay and modular modes. That shared implementation is common within the candidate, not evidence of a novel/common-operator advantage over baseline. These observations are limited to these source snapshots, workloads, sizes, compiler flags, and allocation metric; they do not establish a broad architectural or competitor advantage.
