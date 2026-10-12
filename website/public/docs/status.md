
RefPot 0.1.1 is the first **experimental alpha release candidate** of a custom C++ redo-and-checkpoint engine and Python CRUD/transaction interface. It is intended for evaluation, not production. Public-index installation has not yet been independently verified; use the locally built artifact until then. Package and platform qualification remains limited.

## Historical experimental result

The package behavior is detailed in the [package contract](/package-contract/). Separately, the repository retains an [audited random-update experiment](https://github.com/tugrulguner/refpot/tree/main/benchmarks/random-updates) with frozen experimental source, 672 raw records and reproduction commands. All 16 repeated matrix cells passed the scoped 2× service/setup target and best-tested SQLite p99: **3.04–5.95× service**, **2.99–5.91× including setup**. This measures existing-row updates with atomic receipt tracking and equal batching in a Linux ARM64 Docker/ext4 VM, not a general database advantage. Reopen with full-state validation loses all 16 cells; earlier misses remain documented.

## Not provided or qualified

No SQL, ORM, concurrent readers, multiwriter support, Windows or unsupported architectures, existing-format compatibility, independent physical replicas, or physical power-loss qualification is provided. Public-index installation of 0.1.1 is pending independent verification. Mutation and diff-scan paths copy maps; package performance is not benchmark-fast or qualified. See the [package contract](/package-contract/).

The **2×-over-SQLite threshold is an acceptance target, not an achieved guarantee**. Performance claims require equivalent complete operations and the declared correctness, durability, and qualification matrix.

Do not infer a supported release, production readiness, or package performance from the preview.

## Participate

Read the [design direction](/design/), [qualification method](/performance-method/), and [canonical roadmap](/project/roadmap/). Discuss scoped engine contracts, correctness cases, crash and I/O-failure tests, and measurement methods in [GitHub Issues](https://github.com/tugrulguner/refpot/issues) or the [ModePot community](https://discord.gg/u3AANZr6RG).

[Package contract](/package-contract/) · [Download this page as Markdown](/docs/status.md).
