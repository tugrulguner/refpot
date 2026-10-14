# RefPot practical guides

These guides exercise the experimental alpha. Install the latest published version with `python -m pip install refpot` on CPython 3.11–3.14. Prebuilt wheels cover Linux x86_64 and macOS arm64; only source builds need a C++17 toolchain. The API and storage format are not stable. Do not use these examples as performance or physical power-loss qualification.

## CRUD

### Create, read, update and delete a row

Save the complete program below as `crud.py`, then run `python crud.py`. Temporary storage makes it safe to run twice; all files are deleted when the program exits. For data you want to keep, choose a private file path in an existing parent directory instead.

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from refpot import Database, Row

with TemporaryDirectory() as directory:
    path = Path(directory) / "records.rp"
    with Database(path) as db:
        db.insert(1, 42, "answer")
        assert db.get(1) == Row(1, 42, "answer")
        db.update(1, value=43)
        assert db.get(1) == Row(1, 43, "answer")
        db.insert(2, 7)
        db.delete(2)
        assert len(db) == 1
        try:
            db.get(2)
        except KeyError:
            pass
        else:
            raise AssertionError("deleted row still exists")
    with Database(path) as db:
        assert db.get(1) == Row(1, 43, "answer")
```

A database starts empty. `insert` creates a row; `update` changes only the provided non-`None` fields. `get` returns an immutable, detached `Row`. Keys and integer values are signed 64-bit integers; text is limited to 31 UTF-8 encoded bytes. Duplicate inserts raise `ValueError`; missing reads, updates and deletes raise `KeyError`. These are fixed-schema operations, not SQL or an ORM.

Continue with [transactions](/build/transactions/), [errors and ownership](/build/errors/), or the [exact API reference](/reference/api/). The repository also contains [examples/crud.py](https://github.com/tugrulguner/refpot/blob/main/examples/crud.py).

## Transactions

### Commit a group or roll it back

Save this as `transactions.py` and run `python transactions.py`. Each program run uses fresh temporary storage.

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from refpot import Database, Row

with TemporaryDirectory() as directory:
    path = Path(directory) / "transactions.rp"
    with Database(path) as db:
        db.insert(1, 10)
        with db.transaction():
            db.update(1, value=20)
            db.insert(2, 30, "committed")
            assert db.get(1) == Row(1, 20, "")
        try:
            with db.transaction():
                db.update(1, value=99)
                db.delete(2)
                raise RuntimeError("cancel the group")
        except RuntimeError:
            pass
        assert db.get(1) == Row(1, 20, "")
        assert db.get(2) == Row(2, 30, "committed")
    with Database(path) as db:
        assert db.get(1) == Row(1, 20, "")
        assert len(db) == 2
```

Normal exit from `with db.transaction():` commits; an exception escaping the block rolls it back. Reads on the owning handle see staged writes. Catching an error *inside* the block does not request rollback: earlier valid staged operations can still commit. Nested transactions are rejected. Do not close the database or request a checkpoint inside an active transaction.

This example proves the API's commit and rollback behavior, not concurrent isolation or physical power-loss safety. One creating process/thread owns the handle; concurrent readers and multiwriter operation are unsupported. Continue with [persistence and checkpointing](/build/persistence/) or [uncertain failures](/build/errors/).

## Persistence

### Reopen committed data and checkpoint explicitly

Save this as `persistence.py`, then run `python persistence.py`. The temporary parent directory exists before `Database` opens its file. The data survives close/reopen within this program; the temporary directory is removed afterward.

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from refpot import Database, Row

with TemporaryDirectory() as directory:
    path = Path(directory) / "persistent.rp"
    with Database(path) as db:
        db.insert(1, 42, "saved")
    with Database(path) as db:
        assert db.get(1) == Row(1, 42, "saved")
        db.update(1, value=43)
        db.checkpoint()
    with Database(path) as db:
        assert db.get(1) == Row(1, 43, "saved")
```

Acknowledged mutations do not depend on a destructor or close-time checkpoint. The engine records changes in a WAL; an explicit checkpoint publishes a snapshot before reclaiming redo. Snapshot and WAL recovery are bounded to 64 MiB each. Capacity refusal occurs before writing; do not assume an arbitrary database size is supported.

Keep the database and its WAL together. Backup/restore, migration between storage versions, and existing-format compatibility are not supported workflows. Do not casually copy or delete live storage files. Reopening successfully is not physical power-loss qualification. See [storage and recovery internals](/internals/recovery/) for ordering, corrupted copies, incomplete tails and remaining limitations.

## Errors and ownership

### Handle validation errors without changing stored data

Save this as `errors.py` and run `python errors.py`. The program demonstrates two rejected operations and verifies the original row is intact.

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from refpot import Database, Row

with TemporaryDirectory() as directory:
    path = Path(directory) / "validation.rp"
    with Database(path) as db:
        db.insert(1, 42, "answer")
        try:
            db.insert(1, 99)
        except ValueError:
            pass
        else:
            raise AssertionError("duplicate insert was accepted")
        try:
            db.update(1, text="é" * 16)
        except ValueError:
            pass
        else:
            raise AssertionError("oversized UTF-8 text was accepted")
        assert db.get(1) == Row(1, 42, "answer")
```

The text limit counts encoded bytes, not characters: `"é" * 16` uses 32 UTF-8 bytes. Booleans and non-integer keys/values raise `TypeError`; out-of-range integers raise `OverflowError`. Missing keys raise `KeyError`. Closed handles, corrupt storage, invalid ownership and I/O failures raise `RuntimeError`; consult the [exact contract](/package-contract/) for each operation.

### Keep one owner and treat uncertain writes separately

Use a private, trusted filesystem namespace. A database path names a **file**, not a directory; its parent must already exist. One process exclusively owns each database and only the creating thread may use its handle. Do not pass a handle to another thread or use an inherited handle after `fork()`.

An uncertain write poisons the owner. Close it, reopen and inspect stored state before choosing whether to retry: the uncertain transaction may be entirely present or absent. A `RuntimeError` is not proof that nothing committed. Avoid blind retries that can duplicate application actions. Capacity/argument rejection is distinct from an uncertain I/O failure. Recovery implementation checks are bounded and do not establish broad filesystem or physical power-loss guarantees.

Continue with [API reference](/reference/api/) and [recovery internals](/internals/recovery/).
