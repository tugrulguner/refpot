---
name: refpot-database
description: Use RefPot's current embedded Python database contract.
version: 0.1.0
author: Tugrul Guner, Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [database, embedded, python, transactions]
    related_skills: []
---

# RefPot database skill

Use this skill when building an application with RefPot's current Python database preview or when checking whether a requested database feature is supported. RefPot is an unreleased, experimental native engine; do not infer SQL, ORM, production, or broad durability support.

## Install the current preview

RefPot is not published on PyPI. From a checkout of the repository, install/build with a C++17 toolchain and Python 3.11–3.14:

```sh
uv pip install .
```

The package supports Linux and macOS in its current preview; Windows is unsupported. Consult the repository README and `docs/package-contract.md` for the exact current constraints before deployment.

## Current API shape

```python
from pathlib import Path
from refpot import Database, Row

path = Path("data/example.rp")  # parent directory must already exist
with Database(path) as db:
    db.insert(1, 42, "answer")
    db.update(1, value=43)
    row = db.get(1)
    assert row == Row(1, 43, "answer")
    db.delete(1)
```

Use only caller-supplied integer keys/values and the supported bounded text fields; check `docs/package-contract.md` for precise limits, missing/duplicate behavior, transaction semantics, and errors. Transactions are explicit with `with db.transaction(): ...`; closing and reopening the same path exercises persisted state. The path is a database file, not a directory.

## Boundaries

- Do not invent or use SQL, ORM/model classes, joins, indexes, or APIs not present in the package contract.
- One process owns a database, and only the thread that created the handle may use it. Concurrent readers and multiwriter use are unsupported.
- Recovery behavior is bounded and tested for specific cases; it is not a general physical power-loss guarantee or production durability certification.
- Performance is unqualified. Historical benchmark ratios describe a separate experiment, not the installed package.
- Do not place important data in the preview without an independently suitable backup and failure policy.

When a requested capability is outside this contract, state that limitation and point to `ROADMAP.md`; do not emulate it with hidden SQL or claim it is planned as a committed API. For repository changes, follow `AGENTS.md` and `CONTRIBUTING.md`.
