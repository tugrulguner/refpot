
RefPot is in **engine-first research and design**, not a released database.

## Available today

The repository contains project documentation, editable artwork, and an [audited random-update experiment](https://github.com/tugrulguner/refpot/tree/main/benchmarks/random-updates) with frozen experimental source, 672 raw records and reproduction commands. All 16 repeated matrix cells passed the scoped 2× service/setup target and best-tested SQLite p99: **3.04–5.95× service**, **2.99–5.91× including setup**. This measures existing-row updates with atomic receipt tracking and equal batching in a Linux ARM64 Docker/ext4 VM, not a general database advantage. Reopen with full-state validation loses all 16 cells; earlier misses remain documented.

## Not shipped

There is no general relational engine, durable insert/update/delete API, qualified concurrency, SQL frontend, Python binding, supported ORM, installable package, or stable public API. The reproducible experimental result does not establish a general performance guarantee.

The **2×-over-SQLite threshold is an acceptance target, not an achieved guarantee**. Performance claims require equivalent complete operations and the declared correctness, durability, and qualification matrix.

License and distribution policy remain undecided. Do not infer production readiness or adoption terms from the design.

## Participate

Read the [design direction](/design/), [qualification method](/performance-method/), and [canonical roadmap](/project/roadmap/). Discuss scoped engine contracts, correctness cases, crash and I/O-failure tests, and measurement methods in [GitHub Issues](https://github.com/tugrulguner/refpot/issues) or the [ModePot community](https://discord.gg/u3AANZr6RG).

[Download this page as Markdown](/docs/status.md).
