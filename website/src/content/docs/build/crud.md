---
title: CRUD
description: Practical guide to the public experimental alpha.
---

These guides exercise the public experimental alpha. Install with `python -m pip install refpot==0.1.1` on CPython 3.11–3.14. Prebuilt wheels cover Linux x86_64 and macOS arm64; only source builds need a C++17 toolchain. The API and storage format are not stable. Do not use these examples as performance or physical power-loss qualification.


## Create, read, update and delete a row

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


[Download this page as Markdown](/docs/build-crud.md)
