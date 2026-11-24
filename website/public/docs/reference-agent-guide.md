## When to use

Use when building an application with the current Python database preview or checking whether a requested feature is supported. This skill documents the published fixed-schema `refpot.Database` contract; it does not establish production readiness. Version 0.1.2 additionally has a `refpot.sql.Database` preview documented in [the SQL preview contract](/reference/sql-preview/): `Database()` is volatile, while a path opts into bounded whole-model persistence. A bounded, read-only `agent=True` query-generation slice is part of version 0.1.2; it requires configured trusted Python generator code and explicit schema disclosure. This feature does not complete M2. The native binder enforces query authority but cannot establish user intent. Review [the evaluation evidence and remaining gates](https://github.com/tugrulguner/refpot/blob/445e68e0c6f464b9a985f03b1b9f8ca8367475d6/docs/agent-query-evaluation.md). Persistent SQL mode is not broadly qualified and aborts an entire explicit transaction on any executed statement error. Do not transfer the fixed-schema transaction behavior below to that separate API. ORM is not shipped. The SQL source preview additionally supports `ALTER MATERIALIZED VIEW name AS SELECT ...` outside transactions: one existing view with unchanged output names/order, transitive recomputation and assertion validation before atomic publication. See [the migration/reopen example](https://github.com/tugrulguner/refpot/blob/445e68e0c6f464b9a985f03b1b9f8ca8367475d6/examples/sql_evolution.py). Do not infer table/column changes, online migration or backwards compatibility with older preview readers.

## Prerequisites and installation

RefPot is an experimental alpha. Install the latest published package with `python -m pip install refpot`. Prebuilt wheels target Linux x86_64 and macOS arm64 on CPython 3.11–3.14; source builds require a C++17 compiler toolchain. Windows, other architectures, and free-threaded Python are unsupported. Run these commands through your agent's command-execution tool (Hermes: `terminal`), starting in a directory where a new `refpot` checkout can be created:

```sh
git clone https://github.com/tugrulguner/refpot.git
cd refpot
uv venv --python 3.11
uv pip install --python .venv/bin/python .
.venv/bin/python examples/crud.py
.venv/bin/python examples/transactions.py
```

If a checkout already exists, inspect its branch and working tree and run the installation commands from that repository's root; do not overwrite local work. Use `.venv/bin/python` for subsequent examples. Installing the Python package does not automatically install this agent skill. The skill directory can be copied into an agent's supported skill location using that agent's documented installation procedure.

## Exact API boundaries

- Keys and integer values are signed 64-bit integers: `-2**63` through `2**63 - 1`. Booleans and non-integers are rejected.
- Text must be a string of at most 31 UTF-8 encoded bytes. Count `len(text.encode("utf-8"))`, not characters: `"é" * 15` uses 30 bytes; `"é" * 16` exceeds the limit.
- A database path names a file in an existing parent directory. Use a private, trusted filesystem namespace. One process exclusively owns a database; only the handle's creating thread may use it. Do not use an inherited handle after `fork()`.
- Duplicate inserts raise `ValueError`; fetching, updating or deleting missing keys raises `KeyError`. Bad argument types raise `TypeError`; out-of-range integers raise `OverflowError`.
- Explicit transactions use `with db.transaction():`. An exception escaping the block rolls it back; normal exit commits. Catching an exception inside the block does not request rollback. Nested transactions are unsupported.
- Snapshot and WAL recovery are each bounded to 64 MiB. Capacity refusal is distinct from an uncertain I/O failure. An uncertain write poisons the handle: close it and reopen, then inspect persisted state before retrying. The uncertain transaction can be fully present or absent.

## Repeatable example

Save this as `refpot_example.py` and execute `.venv/bin/python refpot_example.py` from the checkout root. Temporary storage makes repeated runs independent; all data is deleted when the example exits.

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from refpot import Database, Row

with TemporaryDirectory(prefix="refpot-skill-") as directory:
    path = Path(directory) / "example.rp"
    with Database(path) as db:
        db.insert(1, 42, "answer")
        db.update(1, value=43)
        assert db.get(1) == Row(1, 43, "answer")
        with db.transaction():
            db.insert(2, 99, "é" * 15)
        try:
            with db.transaction():
                db.update(1, value=100)
                raise RuntimeError("roll back")
        except RuntimeError:
            pass
        assert db.get(1) == Row(1, 43, "answer")
        try:
            db.insert(3, 1, "é" * 16)
        except ValueError:
            pass
        else:
            raise AssertionError("oversized UTF-8 text was accepted")
        db.delete(2)
        db.checkpoint()
    with Database(path) as db:
        assert db.get(1) == Row(1, 43, "answer")
        assert len(db) == 1
        print(db.get(1))
```

## Verification and pitfalls

Require both shipped examples and the repeatable example to exit successfully. Confirm reopening preserves the committed row and rollback preserves its previous value. These checks exercise the package; they do not benchmark performance or simulate physical power loss.

The six-cell performance screen against prepared SQLite used locally built wheels labeled 0.1.1, not published 0.1.2 artifacts. Three cells fell below 2×. The historical 2× SQLite target is retired; the measurements do not establish a general performance advantage. Historical prototype ratios describe a separate experiment.

The fixed-schema API does not support SQL, joins, or public index APIs. The separate SQL preview supports a bounded SQL subset, including one inner join; see the [SQL preview contract](/reference/sql-preview/). ORM, concurrent readers, multiwriter use, and SQLite file/API compatibility are unsupported. Physical power-loss safety remains unqualified. Do not use either preview for important data without an independently suitable backup and failure policy.

Use the [package contract](https://github.com/tugrulguner/refpot/blob/445e68e0c6f464b9a985f03b1b9f8ca8367475d6/docs/package-contract.md) for complete method semantics and the [roadmap](https://github.com/tugrulguner/refpot/blob/445e68e0c6f464b9a985f03b1b9f8ca8367475d6/ROADMAP.md) for future work. For repository changes, follow [AGENTS.md](https://github.com/tugrulguner/refpot/blob/445e68e0c6f464b9a985f03b1b9f8ca8367475d6/AGENTS.md) and [CONTRIBUTING.md](https://github.com/tugrulguner/refpot/blob/445e68e0c6f464b9a985f03b1b9f8ca8367475d6/CONTRIBUTING.md). Never invent APIs to satisfy an unsupported request.
