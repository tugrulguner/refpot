
RefPot is in **engine-first research and design**, not a released database.

## Available today

The repository contains the project definition, design direction, qualification roadmap, and editable artwork. Earlier isolated native experiments inform the hypotheses, but their exploratory artifacts have not been imported as a supported implementation.

## Not shipped

There is no general relational engine, durable insert/update/delete API, qualified concurrency, SQL frontend, Python binding, supported ORM, installable package, or stable public API. No reproducible general performance result is available from this checkout.

The **2×-over-SQLite threshold is an acceptance target, not an achieved guarantee**. Performance claims require equivalent complete operations and the declared correctness, durability, and qualification matrix.

License and distribution policy remain undecided. Do not infer production readiness or adoption terms from the design.

## Participate

Read the [design direction](/design/), [qualification method](/performance-method/), and [canonical roadmap](/project/roadmap/). Discuss scoped engine contracts, correctness cases, crash and I/O-failure tests, and measurement methods in [GitHub Issues](https://github.com/tugrulguner/refpot/issues) or the [ModePot community](https://discord.gg/u3AANZr6RG).

[Download this page as Markdown](/docs/status.md).
