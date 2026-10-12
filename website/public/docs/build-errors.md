These guides exercise the public experimental alpha. Install with `python -m pip install refpot==0.1.1` on CPython 3.11–3.14. Prebuilt wheels cover Linux x86_64 and macOS arm64; only source builds need a C++17 toolchain. The API and storage format are not stable. Do not use these examples as performance or physical power-loss qualification.


## Handle validation errors without changing stored data

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

## Keep one owner and treat uncertain writes separately

Use a private, trusted filesystem namespace. A database path names a **file**, not a directory; its parent must already exist. One process exclusively owns each database and only the creating thread may use its handle. Do not pass a handle to another thread or use an inherited handle after `fork()`.

An uncertain write poisons the owner. Close it, reopen and inspect stored state before choosing whether to retry: the uncertain transaction may be entirely present or absent. A `RuntimeError` is not proof that nothing committed. Avoid blind retries that can duplicate application actions. Capacity/argument rejection is distinct from an uncertain I/O failure. Recovery implementation checks are bounded and do not establish broad filesystem or physical power-loss guarantees.

Continue with [API reference](/reference/api/) and [recovery internals](/internals/recovery/).
