# RefPot package status and next steps

**Experimental alpha.** Version 0.1.1 is the current public PyPI release; version 0.1.2 is in preparation and not yet published. The package contains an early native C++ redo-and-checkpoint engine with a Python CRUD and transaction interface. Release preparation does not establish production readiness; package qualification remains limited.

## What is present in this preview

- `Database` and `Row` public Python types for caller-supplied signed-64-bit keys and values and UTF-8 text up to 31 encoded bytes.
- An initially empty database, stored at a file path whose parent directory must exist.
- CRUD and explicit transactions; one process owns a database exclusively and the public interface is thread-affine.
- Version-2 `RPSNAP2` snapshots and a `.wal` redo log containing two identical checksummed copies per changed-row transaction.
- Snapshot publication via sync, atomic rename, parent-directory sync, then log truncation and sync.
- Row-local transaction change sets: staged work does not clone the whole database map; commit preparation completes before WAL writes; synchronized redo is followed by prepared, nonallocating publication; recovery replays validated row effects without copying unrelated rows.

Install the currently published alpha with `python -m pip install refpot`. Prebuilt wheels target Linux x86_64 and macOS arm64 on CPython 3.11–3.14; only source builds need a C++17 toolchain (`uv pip install .`). Examples are in `examples/`. Version 0.1.2 is not yet available from PyPI.

## Performance evidence and limits

The actual-package campaign compares the public Python package with prepared SQLite over six cells. See [canonical measured results](https://github.com/tugrulguner/refpot/blob/main/benchmarks/package-performance/RESULTS.md) when integrated and the [reproduction guide](../benchmarks/package-performance/README.md). Research-review evidence measures source revisions in wheels labeled 0.1.1, not new 0.1.2 release artifacts. Three of the six cells remain below 2×; the overall 2× SQLite target is unmet. The 10,000-row batch-update and both point-read cells exceed 2×, but those wins do not satisfy the complete target.

Historical experimental update-harness results are separate: 3.04–5.95× belongs only to that harness, and the historical reopen comparison remains 16/16 losses. Neither should be conflated with package results.

## Boundaries and remaining work

No SQL, ORM, concurrent-reader or multiwriter support, Windows support, existing-format compatibility, independent physical replicas, or physical power-loss qualification is claimed. Recovery accepts incomplete unacknowledged tails as discarded, rejects complete corrupt transactions with both copies corrupt, and bounds each snapshot/WAL to 64 MiB. Uncertain writes poison the writer. See the [package contract](package-contract.md) for detail.

Open gates include failure/recovery qualification, installed-artifact and platform verification, sustained and broader package-performance testing, and qualification of release artifacts. No broad roadmap milestone is implied complete; tagging and publication require separate explicit approval.
