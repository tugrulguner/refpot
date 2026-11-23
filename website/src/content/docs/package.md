---
title: Package quick start
slug: package
description: Install RefPot and choose the experimental SQL preview or the fixed-schema Python API.
---

**Experimental alpha.** RefPot is not a production-qualified database. It runs a native database engine inside your Python program.

## Prerequisites and install

Use Python 3.11–3.14. Install the currently published experimental alpha with:

```sh
python -m pip install refpot
```

Prebuilt wheels are available for Linux x86_64 and macOS arm64 on CPython 3.11–3.14. A C++17 compiler is required only when building from source. From a checkout root, use `uv`:

```sh
uv pip install .
```

This builds the package from the current checkout.

## Choose an API

- **SQL preview (0.1.2 or later):** start with `refpot.sql.Database` and the [runnable reservation example](/#try-a-reservation-rule), then use the [SQL reference](/reference/sql-preview/) to explore maintained views, commit rules, and persistence. No model is required for ordinary SQL.
- **Fixed-schema Python API:** use `refpot.Database` and `Row` to store integer-keyed records. The complete example below uses this API, which has its own storage format and transaction contract.

## Run a complete program

Save this complete program as `quickstart.py` and run `python quickstart.py` (or run the repository copy with `python examples/quickstart.py`):

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from refpot import Database, Row

with TemporaryDirectory() as directory:
    path = Path(directory) / "example.rp"
    with Database(path) as db:
        db.insert(1, 42, "answer")
        db.update(1, value=43)
        assert db.get(1) == Row(1, 43, "answer")
        with db.transaction():
            db.insert(2, 99)
        try:
            with db.transaction():
                db.update(1, value=100)
                raise RuntimeError("rollback")
        except RuntimeError:
            pass
        assert db.get(1) == Row(1, 43, "answer")
        db.delete(2)
        db.checkpoint()
    with Database(path) as db:
        assert db.get(1) == Row(1, 43, "answer")
        print(db.get(1))
```

```sh
python quickstart.py
```

The program uses the native package and temporary files. Also see the standalone [CRUD example](https://github.com/tugrulguner/refpot/blob/main/examples/crud.py) and [transaction example](https://github.com/tugrulguner/refpot/blob/main/examples/transactions.py).

## Next — Reference

Continue with [CRUD](/build/crud/), [transactions and rollback](/build/transactions/), [persistence and checkpointing](/build/persistence/), or [errors and ownership](/build/errors/). Read the [complete package contract](/package-contract/) for operations, errors, ownership, file formats, recovery limits, and qualification boundaries. See [status and next steps](/status/), [design direction](/design/), and [performance methodology](/performance-method/). The [roadmap](/project/roadmap/) remains the canonical milestone record.
