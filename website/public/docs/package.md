
**Unreleased local source-build preview — not a PyPI release or supported distribution.** RefPot contains an early custom C++ redo-and-checkpoint engine with a Python `Database` / `Row` interface. Qualification remains in progress.

## Prerequisites and install

Use Python 3.11–3.14, `uv`, and a C++17 compiler. From the repository root, with its `pyproject.toml`:

```sh
uv pip install .
```

This builds the package from the current checkout. There is no PyPI installation command; do not use `pip install refpot` as a published path.

## Run the examples

```sh
python examples/crud.py
python examples/transactions.py
```

Both scripts create temporary database files and exercise the native package. The CRUD example inserts, updates, deletes, closes, and reopens persisted state. The transaction example verifies read-your-writes, commit, rollback, checkpoint, and reopen.

## Minimal API

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from refpot import Database, Row

with TemporaryDirectory() as directory:
    path = Path(directory) / "example.rp"  # Parent directory already exists.
    with Database(path) as db:
        db.insert(1, 42, "answer")
        db.update(1, value=43)
        assert db.get(1) == Row(1, 43, "answer")
        with db.transaction():
            db.insert(2, 99)
        try:
            with db.transaction():
                db.update(1, value=100)
                raise RuntimeError("roll back")
        except RuntimeError:
            pass
        assert db.get(1) == Row(1, 43, "answer")
    with Database(path) as db:
        assert db.get(1) == Row(1, 43, "answer")
```

The code uses the actual Python API and native package, not a browser playground or simulated database. Run the shipped scripts for complete executable examples.

## Next — Reference

Read the [complete package contract](/package-contract/) for operations, errors, ownership, file formats, recovery limits, and qualification boundaries. See [status and next steps](/status/), [design direction](/design/), and [performance methodology](/performance-method/). The [roadmap](/project/roadmap/) remains the canonical milestone record.
