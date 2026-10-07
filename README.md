# refpot

<p align="center">
  <img src="docs/assets/refpot-lockup.png" alt="RefPot — embedded, relational, simple" width="600">
</p>

<p align="center">Part of <a href="https://modepot.io/">ModePot</a>. &nbsp; <a href="https://tugrul.modepot.io/">Created by Tugrul Guner</a></p>

<p align="center"><strong>A custom embedded relational engine. A simple Python ORM. No database server.</strong></p>

<p align="center">Own the engine, remove unnecessary work, and make ordinary database operations straightforward.</p>

<p align="center">
  <a href="#why-refpot">Why RefPot</a> ·
  <a href="#project-status">Status</a> ·
  <a href="ROADMAP.md">Roadmap</a> ·
  <a href="#design-direction">Design direction</a> ·
  <a href="#performance-target">Performance target</a> ·
  <a href="#contributing">Contributing</a>
</p>

> [!IMPORTANT]
> RefPot is in engine-first research and design. This repository starts with project
> documentation and identity, not a released database. There is no installable package,
> stable API, production durability guarantee, or general 2× performance claim yet.

## Why RefPot?

RefPot is being designed as **its own embedded relational database engine**, with a
Python ORM built on top. It is not a SQLite wrapper, and the engine should be useful
without the ORM.

The architectural hypothesis is one execution core with two entry points: SQL for direct
engine use, and structured operations for the ORM. The ORM should not need to generate SQL
only for the engine to parse the same operation back again. Both paths must enforce the
same constraints, transaction rules, and recovery behavior.

The developer experience matters just as much: open a local database, declare data, perform
ordinary reads and writes, and use explicit transactions. Avoid mandatory repository stacks,
hidden queries, and a public menu of internal tuning strategies. This is a design goal,
not an API available today.

## Project status

**In this repository:** the project definition and editable logo artwork.

**In earlier research:** isolated native read, transaction, logging, checkpoint, and routing
prototypes. These are not a finished RefPot implementation or a supported distribution.

**Not shipped:** a general relational engine, durable insert/update/delete API, qualified
concurrency, SQL frontend, Python binding, or ORM. The exploratory benchmark artifacts have
not been imported into this repository; no published performance result is reproducible
from this checkout yet.

Research provides a reason to continue, not a product claim:

- Cache-aware separated key/value layouts improved scoped native point-read costs. That
  does not establish durable database performance.
- Preallocated redo rings with bounded snapshots exceeded 2× against best-tested SQLite
  configurations in some large update-batch workloads in a Linux ARM64 VM.
- Small durable transactions did not reliably meet the target. Dataset scaling and
  recovery exposed tradeoffs; no single tested layout won everywhere.
- A short-pilot strategy selector sometimes chose poorly. Automatic adaptation still
  needs representative measurement, bounded costs, and a safe fallback.

## Design direction

The proposed layers are:

```text
SQL frontend ────────┐
                    ├── Execution core ── Indexes / storage
Structured operations┘                 └─ Transactions / recovery
          ↑
      Python ORM
```

These are planned boundaries, not existing modules.

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
