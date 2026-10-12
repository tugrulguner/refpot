These guides exercise the public experimental alpha. Install with `python -m pip install refpot==0.1.1` on CPython 3.11–3.14. Prebuilt wheels cover Linux x86_64 and macOS arm64; only source builds need a C++17 toolchain. The API and storage format are not stable. Do not use these examples as performance or physical power-loss qualification.


## Reopen committed data and checkpoint explicitly

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
