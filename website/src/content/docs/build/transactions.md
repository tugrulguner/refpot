---
title: Transactions and rollback
description: "Use explicit RefPot transactions and verify rollback behavior in the experimental alpha."
---

These guides exercise the experimental alpha. Install the latest published version with `python -m pip install refpot` on CPython 3.11–3.14. Prebuilt wheels cover Linux x86_64 and macOS arm64; only source builds need a C++17 toolchain. The API and storage format are not stable. Do not use these examples as performance or physical power-loss qualification.


## Commit a group or roll it back

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


[Download this page as Markdown](/docs/build-transactions.md)
