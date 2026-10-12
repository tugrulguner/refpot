
**Experimental alpha release.** RefPot is available on PyPI but is not a production-qualified database. It contains an early custom C++ redo-and-checkpoint engine with a Python `Database` / `Row` interface. Qualification remains in progress.

## Prerequisites and install

Use Python 3.11–3.14. Install the published experimental alpha with:

```sh
python -m pip install refpot==0.1.1
```

Prebuilt wheels are available for Linux x86_64 and macOS arm64 on CPython 3.11–3.14. A C++17 compiler is required only when building from source. From a checkout root, use `uv`:

```sh
uv pip install .
```

This builds the package from the current checkout.

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
