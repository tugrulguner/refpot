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


## Performance and maturity

The source change-set implementation stages row-local effects instead of cloning the full map. Commit preparation encodes the final effects before durable I/O; after the duplicated redo is synchronized, publication applies the prepared changes without allocation. Recovery validates and prepares each frame, then replays only its row effects rather than copying unrelated rows. The API and on-disk framing are unchanged. These mechanisms improve the shape of transaction staging and replay; they do not establish general performance or production readiness.

The package-performance campaign compares the actual Python package with prepared SQLite across six cells. Read the canonical [measured results](/project/package-performance/) and [reproduction guide](https://github.com/tugrulguner/refpot/blob/1b6f850613936591f13a04bf7ddd17505cc9e219/benchmarks/package-performance/README.md). Provenance identifies locally built wheels carrying 0.1.1 metadata; these are neither published PyPI 0.1.1 wheels nor a 0.1.2 package artifact. The overall **2×-over-SQLite goal remains unmet**: the 1,000-row singleton-update, 1,000-row batch-update, and 10,000-row singleton-update cells are below 2×. The 10,000-row batch cell exceeds 2×, and the two point-read cells exceed 2×, but those scoped wins do not satisfy the overall gate.

Historical random-update results are separate: the **3.04–5.95×** result belongs only to its audited experimental harness, not the Python package, and its reopen comparison remains **16/16 losses**. See the [recommendation](/status/), [roadmap](/project/roadmap/), [historical methodology](https://github.com/tugrulguner/refpot/tree/1b6f850613936591f13a04bf7ddd17505cc9e219/benchmarks/random-updates), and [package-performance guide](https://github.com/tugrulguner/refpot/blob/1b6f850613936591f13a04bf7ddd17505cc9e219/benchmarks/package-performance/README.md).

The API and storage format are experimental. There is no production durability guarantee; physical power-loss safety, broad cross-platform behavior, concurrent readers, multiwriter use, Windows, SQL, ORM, and SQLite SQL/file/C API compatibility are unsupported.
