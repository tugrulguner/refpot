
**Unreleased local source-build preview — not a PyPI release or supported distribution.** Build from this checkout with `uv pip install .` and a C++17 toolchain. The package is an early custom C++ engine with a Python `Database` / `Row` interface; package failure and platform qualification remains in progress.

## Records and operations

A database starts empty; callers supply records. Keys and integer values are signed 64-bit integers. Text is UTF-8 limited to 31 encoded bytes. The public Python entry points are `from refpot import Database, Row`, with CRUD operations and explicit transactions. The database path names a **file, not a directory**; its parent directory must already exist.

SQL, ORM, arbitrary Python values, secondary indexes, migrations, and existing-format compatibility are not provided. No independent physical replicas are maintained.

## Python API

```python
from refpot import Database, Row
```

- `Database(path)` opens or creates a database at a file path. The parent directory must exist.
- `insert(key, value, text="")` creates a row; returns `None`.
- `get(key)` returns an immutable, detached `Row(key, value, text)`.
- `update(key, *, value=None, text=None)` updates an existing row. Omitted fields and `None` leave that field unchanged; there is no NULL value in this schema.
- `delete(key)` deletes an existing row; returns `None`.
- `len(db)` counts the visible rows, including the current transaction's staged changes.
- `transaction()` returns a context manager. Normal exit commits; an uncaught exception rolls back. Nested transactions are rejected. A caught validation/missing/duplicate error does not undo earlier valid staged operations or apply a partial offending operation.
- `checkpoint()` publishes committed state and reclaims redo; it is rejected inside an explicit transaction.
- `close()` releases ownership and discards any staged transaction. It is idempotent. Do not close a database inside a transaction's context; that context cannot subsequently commit.
- `with Database(path) as db:` releases ownership on exit; individual acknowledged mutations do not depend on destructor or close-time checkpointing.

Duplicate inserts raise `ValueError`; missing get/update/delete raises `KeyError`. Booleans, floats and strings are not coerced to integers (`TypeError`); integers outside signed 64-bit range raise `OverflowError`. Oversized, invalid-UTF-8 text raises `ValueError`. Exceeding serialized snapshot or transaction redo capacity raises `ValueError` before writing. Closed handles, nested transactions, wrong ownership, corruption and I/O failures raise `RuntimeError`.

## Ownership and concurrency

Only the creating process and creating thread may use or close a database handle; inherited handles cannot be used after `fork()`. Database-path symlinks and hard links are rejected. Parent-directory aliases still refer to the same lock-file inode. Do not delete or replace a held `.lock`, alias the sidecar files, or mutate database files outside the engine. This preview assumes a private, trusted local filesystem namespace.

A process obtains exclusive ownership of a database. The public API is thread-affine; concurrent readers, multiwriter operation, and Windows support are not claimed.

## On-disk behavior

Snapshot files use the `RPSNAP2` version-2 format with sequence and CRC metadata. Each changed-row transaction is represented by two identical checksummed copies in the `.wal` file. Both copies are synchronized before the in-memory state is published. This is redo redundancy in one log, not independent physical replication.

Checkpointing writes and synchronizes a full snapshot, atomically renames it, and synchronizes the parent directory before truncating and synchronizing the log. An incomplete, unacknowledged tail is discarded during recovery; a complete transaction whose two copies are corrupt is rejected. An uncertain write poisons the writer. Recovery is bounded to 64 MiB per snapshot and WAL.

These mechanisms are implementation behavior, not broad recovery qualification. Failure tests and platform review remain in progress; filesystem sync and process tests do not establish physical power-loss safety. No existing-format compatibility is promised.

## Performance and maturity

The historical **3.04–5.95×** result belongs only to the audited experimental update harness, not this Python package. Package performance has not been qualified. The known reopen result remains **16/16 losses** in the historical comparison. Mutation and diff-scan paths copy maps; this is not presented as benchmark-fast, and CPU optimization is future work.

There is no PyPI release, stable API, general performance claim, or production durability guarantee. See the [recommendation](/package/), [roadmap](/project/roadmap/), and [experimental methodology](https://github.com/tugrulguner/refpot/tree/main/benchmarks/random-updates).
