# refpot

<p align="center">
  <img src="docs/assets/refpot-lockup.png?v=wordmark-accent-1" alt="RefPot — embedded, relational, simple" width="600">
</p>

<p align="center">Part of <a href="https://modepot.io/">ModePot</a>. &nbsp; <a href="https://refpot.modepot.io/">Project website</a> &nbsp; <a href="https://tugrul.modepot.io/">Created by Tugrul Guner</a></p>

<p align="center">
  <strong>A custom embedded database preview for Python.</strong>
</p>

<p align="center">
  RefPot is an experimental alpha: a native C++ redo-and-checkpoint engine with Python CRUD and explicit transactions. Install the latest published version with `python -m pip install refpot`. Package and platform qualification remain limited.
</p>

<p align="center">
  <a href="https://github.com/tugrulguner/refpot/actions/workflows/ci.yml"><img src="https://github.com/tugrulguner/refpot/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/refpot/"><img src="https://img.shields.io/pypi/v/refpot.svg" alt="PyPI version"></a>
  <img src="https://img.shields.io/badge/Python-3.11--3.14-3776AB?logo=python&amp;logoColor=white" alt="Python 3.11 through 3.14">
  <img src="https://img.shields.io/badge/Status-Experimental%20alpha-49515e" alt="Experimental alpha">
  <a href="https://github.com/tugrulguner/refpot/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License"></a>
  <a href="https://discord.gg/u3AANZr6RG"><img src="https://img.shields.io/badge/Discord-Join%20ModePot-5865F2?logo=discord&amp;logoColor=white" alt="Join the ModePot Discord"></a>
  <a href="https://github.com/tugrulguner/refpot"><img src="https://img.shields.io/github/stars/tugrulguner/refpot?style=flat" alt="GitHub stars"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="#why-refpot">Why RefPot</a> ·
  <a href="#package-contract">Package contract</a> ·
  <a href="https://refpot.modepot.io/">Documentation</a> ·
  <a href="https://refpot.modepot.io/package-contract/">Deep reference</a> ·
  <a href="#examples">Examples</a> ·
  <a href="https://github.com/tugrulguner/refpot/blob/main/skills/refpot-database/SKILL.md">Agent skill</a> ·
  <a href="#community">Community</a> ·
  <a href="#contributing">Contributing</a>
</p>

<p align="center">
  <img src="docs/assets/refpot-execution.png" alt="Planned RefPot architecture, not shipped: direct SQL and a Python ORM's structured operations share one execution core, validation, constraints, transaction guarantees, storage, and recovery" width="960">
</p>

> [!IMPORTANT]
> Experimental alpha. Package and platform qualification remain limited; no general performance claim or production durability guarantee is made.

## Why RefPot

RefPot is an early custom embedded database engine: a native C++ redo-and-checkpoint core exposed through a small Python `Database` / `Row` API. The package preview already supports fixed-schema CRUD and explicit transactions; it is not merely a research design. SQL and ORM are future design direction, not shipped interfaces.

## Quick start

Requires Python 3.11–3.14. Install the experimental alpha from PyPI:

```sh
python -m pip install refpot
```

Save this complete program as `quickstart.py` and run it with `python quickstart.py`:

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from refpot import Database, Row

with TemporaryDirectory(prefix="refpot-quickstart-") as directory:
    path = Path(directory) / "example.rp"  # Parent directory must already exist.
    with Database(path) as db:
        db.insert(1, 42, "answer")
        db.update(1, value=43)
        assert db.get(1) == Row(1, 43, "answer")
        with db.transaction():
            db.insert(2, 99)
        try:
            with db.transaction():
                db.update(1, value=100)
                raise RuntimeError("roll back this transaction")
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

The complete quick start demonstrates CRUD, transaction commit and rollback, checkpointing, and persistence after close/reopen. No output is prescribed; run it to see the actual `Row` representation. The same program is available as [examples/quickstart.py](examples/quickstart.py).

## Package contract

The database starts empty. Keys and integer values are signed 64-bit integers; text is UTF-8 limited to 31 encoded bytes. The database path names a **file, not a directory**, and its parent directory must already exist. One process exclusively owns each database; only its creating thread may use the handle.

The native engine uses versioned snapshots and a WAL. Snapshot and WAL recovery are each bounded to 64 MiB. Incomplete unacknowledged tails are discarded; complete transactions with both copies corrupt are rejected; uncertain writes poison the writer. These implementation details are not broad recovery qualification or a physical power-loss guarantee. Concurrent readers, multiwriter use, Windows, existing-format compatibility, SQL and ORM are unsupported. See the full [package contract](docs/package-contract.md) and [package recommendation](docs/package-recommendation.md).

## Current package architecture

<p align="center"><a href="docs/assets/refpot-package.svg"><img src="docs/assets/refpot-package.png" alt="RefPot experimental alpha architecture: Python Database and Row use a native C++ engine; transaction changes are prepared, duplicated redo is synchronized, then prepared row effects are published without allocation; recovery replays validated row-local effects. Checkpoint snapshot sync, rename and directory sync precede log truncation. Qualification limits apply." width="960"></a></p>

[Open the full-size editable SVG](docs/assets/refpot-package.svg) · [Detailed package contract](docs/package-contract.md)

Transactions stage per-row changes without full-map copies. Commit preparation serializes the final change set before WAL I/O; only after both checksummed redo copies are synchronized does nonallocating publication update committed memory. Recovery validates/prepares a frame before applying row-local changes. These mechanisms preserve the API and storage framing, and do not by themselves establish package performance or broader qualification.

## Build

Task-oriented guides are available for [CRUD](https://refpot.modepot.io/build/crud/), [transactions and rollback](https://refpot.modepot.io/build/transactions/), [persistence and checkpointing](https://refpot.modepot.io/build/persistence/), [errors and ownership](https://refpot.modepot.io/build/errors/), plus the runnable [CRUD example](examples/crud.py), [transaction example](examples/transactions.py), and [complete quick-start program](examples/quickstart.py).

## Reference

The [package contract](docs/package-contract.md) documents the exact `Database` and `Row` API, validation, errors, ownership, capacity and unsupported behavior. Hosted guides: [API reference](https://refpot.modepot.io/reference/api/) · [package reference](https://refpot.modepot.io/package-contract/).

## Internals

The [current package architecture](docs/assets/refpot-package.png) records implementation behavior, not an independently qualified guarantee. [Recovery internals](https://refpot.modepot.io/internals/recovery/) explain file ownership, snapshot/WAL behavior and current limits. The separate [planned execution diagram](docs/assets/refpot-execution.png) remains explicitly planned, not shipped.

## Project

See [project status](https://refpot.modepot.io/status/), [design direction](https://refpot.modepot.io/design/), [roadmap](https://refpot.modepot.io/project/roadmap/), [contributing](CONTRIBUTING.md), and [release policy](docs/releasing.md).

## Examples

The standalone [CRUD example](examples/crud.py) exercises insert, update, delete, context-managed close, and reopen. The [transaction example](examples/transactions.py) demonstrates read-your-writes, commit, rollback, checkpoint, and reopen. Run them after installation:

```sh
python examples/crud.py
python examples/transactions.py
```

The full task-first docs live at [RefPot documentation](https://refpot.modepot.io/) with [package quick start](https://refpot.modepot.io/package/), [package reference](https://refpot.modepot.io/package-contract/), [status and next steps](https://refpot.modepot.io/status/), and [design direction](https://refpot.modepot.io/design/).

## Retained benchmark findings

<p align="center"><img src="docs/assets/refpot-benchmark.png" alt="Audited random-update benchmark: both campaigns pass the scoped service/setup/p99 matrix; reopen with full-state validation loses every cell" width="960"></p>

[Detailed findings, raw evidence and reproduction](benchmarks/random-updates/README.md) ·
[Hosted historical benchmark report](https://refpot.modepot.io/project/benchmarks/) ·
[Full-size chart](docs/assets/refpot-benchmark.png) ·
[Next package recommendation](docs/package-recommendation.md)

The historical findings are separate from package performance. The 3.04–5.95× result applies only to the historical update harness; its reopen result remains 16/16 losses. Package results are reported separately below.

## Planned design direction

The preserved [planned architecture visual](#refpot) shows a future SQL/ORM direction, not this preview. Neither SQL nor ORM is implemented.

- **Engine first.** Establish correctness and performance before building the ORM.
- **One semantic boundary.** Direct operations must not bypass validation or constraints.
- **Explicit guarantees.** Internal plan selection must not silently weaken durability,
  isolation, transaction boundaries, or result semantics.
- **Bounded maintenance.** Include checkpointing, reclamation, and recovery debt in design
  and measurement, rather than hiding them outside favorable timings.
- **Simple public usage.** Keep storage layout, encoding, and routing choices private
  unless a user genuinely needs an operational control.

Language, storage format, index structure, isolation model, and SQL compatibility scope
remain decisions to earn through coherent experiments. A native-language rewrite alone
is not a differentiator. No SQLite SQL, file-format, or C API compatibility is promised.

## Package performance evidence

The actual-package campaign uses the public Python API and prepared SQLite over six workload/size cells. See the canonical [measured results](benchmarks/package-performance/RESULTS.md) and [reproduction guide](benchmarks/package-performance/README.md). Provenance identifies locally built wheels carrying 0.1.1 metadata; these are neither published PyPI 0.1.1 wheels nor a 0.1.2 package artifact. The overall 2× SQLite target remains unmet: three of six measured cells are below 2× (both singleton/batch writes at 1,000 rows and singleton updates at 10,000 rows). Point reads exceed 2× in both sizes, and 10,000-row batch updates exceed 2×; these wins do not satisfy the complete target.

## Community

Join the [ModePot Discord](https://discord.gg/u3AANZr6RG) for design discussions,
implementation questions, early ideas, and database use cases across the family.
Use [GitHub Issues](https://github.com/tugrulguner/refpot/issues) for scoped proposals
and reproducible findings. The experimental alpha is not yet broadly qualified.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and contribution workflow. Repository-local coding-agent guidance is in [AGENTS.md](https://github.com/tugrulguner/refpot/blob/main/AGENTS.md), with the installable [RefPot database skill](https://github.com/tugrulguner/refpot/blob/main/skills/refpot-database/SKILL.md) for consumer-facing API boundaries. The first useful work is helping define a small, testable engine contract and qualification
matrix. Correctness cases, crash and I/O-failure scenarios, reproducible benchmark methods,
and low-ceremony usage designs are more useful now than a broad speculative API.

Discuss substantial architecture or public-contract changes in
[GitHub Issues](https://github.com/tugrulguner/refpot/issues) before implementing them.
Do not introduce a SQLite wrapper as the engine, publish invented benchmark output, or
present research prototypes as production capabilities.

The logo source is [SVG](docs/assets/refpot-lockup.svg); the README uses its
[PNG rendering](docs/assets/refpot-lockup.png).

## License

RefPot is distributed under the [MIT License](LICENSE).

See [CHANGELOG.md](CHANGELOG.md) for changes and [release guidance](docs/releasing.md) for release policy.
