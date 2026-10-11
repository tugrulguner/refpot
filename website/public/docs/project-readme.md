# refpot

<p align="center">
  <img src="docs/assets/refpot-lockup.png" alt="RefPot — embedded, relational, simple" width="600">
</p>

<p align="center"><a href="https://modepot.io/">Part of ModePot</a> &nbsp; · &nbsp; Project website: <a href="https://refpot.modepot.io/">RefPot — research and design</a> &nbsp; · &nbsp; <a href="https://tugrul.modepot.io/">Created by Tugrul Guner</a></p>

<p align="center">
  <strong>An unreleased custom embedded database preview for Python.</strong>
</p>

<p align="center">
  A source-build preview of a custom C++ redo-and-checkpoint engine with Python CRUD and explicit transactions. Not a PyPI release or a qualified production database.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Status-Unreleased%20preview-49515e" alt="Status: unreleased local source-build preview">
  <a href="https://discord.gg/u3AANZr6RG"><img src="https://img.shields.io/badge/Discord-Join%20ModePot-5865F2?logo=discord&amp;logoColor=white" alt="Join the ModePot Discord"></a>
  <a href="https://github.com/tugrulguner/refpot"><img src="https://img.shields.io/github/stars/tugrulguner/refpot?style=flat" alt="GitHub stars"></a>
</p>

<p align="center">
  <a href="#project-status">Package preview</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="docs/package-contract.md">Package contract</a> ·
  <a href="ROADMAP.md">Roadmap</a> ·
  <a href="#planned-design-direction">Design direction</a> ·
  <a href="#performance-target">Performance target</a> ·
  <a href="#community">Community</a> ·
  <a href="#contributing">Contributing</a>
</p>

<p align="center">
  <img src="docs/assets/refpot-execution.png" alt="Planned RefPot architecture, not shipped: direct SQL and a Python ORM's structured operations share one execution core, validation, constraints, transaction guarantees, storage, and recovery" width="960">
</p>

> [!IMPORTANT]
> This checkout contains an unreleased local source-build preview, not a PyPI release or supported distribution. Package failure and platform qualification remain in progress. There is no general performance claim or production durability guarantee.

## Project status

The repository has an early native C++ custom redo-and-checkpoint engine and Python `Database` / `Row` CRUD plus explicit transactions. The database starts empty and uses caller-provided signed-64-bit integer keys/values and UTF-8 text up to 31 encoded bytes. It opens a file path (not a directory); the parent directory must exist.

The source-build preview can be installed with `uv pip install .` from this checkout with a C++17 toolchain. It is **not released on PyPI**. The public interface is thread-affine, one process owns a database exclusively, and concurrent readers, multiwriter, Windows, existing-format compatibility, and SQL/ORM are unsupported. Recovery and failure qualification remain ongoing.

### Quick start

```sh
uv pip install .
```

See runnable [CRUD example](examples/crud.py) and [transaction example](examples/transactions.py), plus the exact [package contract](docs/package-contract.md). Provide an existing parent directory and a file path to `Database`; databases start empty.

## Current package architecture

<p align="center"><a href="docs/assets/refpot-package.svg"><img src="docs/assets/refpot-package.png" alt="Unreleased source-build preview architecture: Python Database and Row use a native C++ engine; transactions synchronize duplicated checksummed redo before memory publication; checkpoint snapshot sync, rename and directory sync precede log truncation. Limits and qualifications are listed in the accessible text below." width="960"></a></p>

[Open the full-size editable SVG](docs/assets/refpot-package.svg) · [Detailed package contract](docs/package-contract.md)

The Python interface is thread-affine and process-exclusive. Snapshot/WAL recovery is bounded to 64 MiB each. Incomplete unacknowledged tails are discarded; complete transactions with both copies corrupt are rejected; uncertain writes poison the writer. These implementation details do not mean broad recovery qualification is complete. Mutation and diff scan copy maps; this preview is not benchmark-fast.

## Retained benchmark findings

<p align="center"><img src="docs/assets/refpot-benchmark.png" alt="Audited random-update benchmark: both campaigns pass the scoped service/setup/p99 matrix; reopen with full-state validation loses every cell" width="960"></p>

[Detailed findings, raw evidence and reproduction](benchmarks/random-updates/README.md) ·
[Full-size chart](docs/assets/refpot-benchmark.png) ·
[Next package recommendation](docs/package-recommendation.md)

The experimental findings are retained separately from package performance. The 3.04–5.95× result is scoped to the historical update harness; package performance is unqualified. Known historical reopen result remains 16/16 losses. SQL and ORM remain later milestones.

## Planned design direction

The preserved [planned architecture visual above](#refpot) shows a future SQL/ORM direction, not this preview. Neither SQL nor ORM is implemented.

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

## Performance target

**At least 2× improvement over SQLite is an acceptance target, not an achieved guarantee.**

Before claiming it, define and publish a workload matrix, then retain every passing and
failing cell. Compare equivalent operations, returned values, transaction boundaries,
constraints, and durability acknowledgments against prepared SQLite and its best-tested
configuration for each workload.

Measure the layers separately:

1. **Engine:** native RefPot operations versus prepared native SQLite.
2. **Python binding:** equivalent public operations and materialized results versus
   Python SQLite interfaces.
3. **ORM:** complete application operations versus optimized ORM baselines, alongside
   raw-engine measurements so abstraction costs remain visible.

Include maintenance and synchronization in throughput; report tail latency, memory,
disk growth, recovery, and concurrency separately. Repeat complete campaigns when results
are unstable. Keep native macOS, Linux VM, and bare-metal results distinct. A faster lookup
or a favorable batch does not make RefPot a faster database across the board.

## Community

Join the [ModePot Discord](https://discord.gg/u3AANZr6RG) for design discussions,
implementation questions, early ideas, and database use cases across the family.
Use [GitHub Issues](https://github.com/tugrulguner/refpot/issues) for scoped proposals
and reproducible findings. The source-build preview is unreleased and not yet broadly qualified.

## Contributing

The first useful work is helping define a small, testable engine contract and qualification
matrix. Correctness cases, crash and I/O-failure scenarios, reproducible benchmark methods,
and low-ceremony usage designs are more useful now than a broad speculative API.

Discuss substantial architecture or public-contract changes in
[GitHub Issues](https://github.com/tugrulguner/refpot/issues) before implementing them.
Do not introduce a SQLite wrapper as the engine, publish invented benchmark output, or
present research prototypes as production capabilities.

The logo source is [SVG](docs/assets/refpot-lockup.svg); the README uses its
[PNG rendering](docs/assets/refpot-lockup.png).
