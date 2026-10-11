

**Unreleased local source-build preview; no PyPI release.** The checkout now contains an early native C++ redo-and-checkpoint engine with a Python CRUD and transaction interface. It is a preview, not a supported release, and package qualification is still in progress.

## What is present in this preview

- `Database` and `Row` public Python types for caller-supplied signed-64-bit keys and values and UTF-8 text up to 31 encoded bytes.
- An initially empty database, stored at a file path whose parent directory must exist.
- CRUD and explicit transactions; one process owns a database exclusively and the public interface is thread-affine.
- Version-2 `RPSNAP2` snapshots and a `.wal` redo log containing two identical checksummed copies per changed-row transaction.
- Snapshot publication via sync, atomic rename, parent-directory sync, then log truncation and sync.

Install the preview from this source checkout with `uv pip install .` and a C++17 toolchain. Examples are in `examples/`. This is not a released or broadly qualified install path.

## Boundaries and remaining work

No SQL, ORM, concurrent-reader or multiwriter support, Windows support, existing-format compatibility, independent physical replicas, or physical power-loss qualification is claimed. Recovery accepts incomplete unacknowledged tails as discarded, rejects complete corrupt transactions with both copies corrupt, and bounds each snapshot/WAL to 64 MiB. Uncertain writes poison the writer. See the [package contract](/package-contract/) for detail.

Package performance is not established: map copies occur on mutation and diff scan, and CPU optimization remains future work. Historical experimental update-harness results remain scoped at 3.04–5.95×; historical reopen remains a 16/16 loss. Neither is a package benchmark.

Remaining gates include failure/recovery tests, installed-artifact and platform verification, package-specific performance screening, and release readiness. No roadmap milestone is implied complete and publishing requires separate approval.
