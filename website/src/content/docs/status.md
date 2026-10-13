---
title: Package preview status
description: What exists in RefPot today, what remains planned, and how to participate.
---

RefPot is an **experimental alpha** custom C++ redo-and-checkpoint engine with a Python CRUD/transaction interface. It is intended for evaluation, not production; platform and recovery qualification remain limited. Release preparation state and gates are recorded in the [release checklist on GitHub](https://github.com/tugrulguner/refpot/blob/main/docs/releasing.md).

## Actual-package performance screen

The package campaign measures the public Python API against prepared SQLite at 1,000 and 10,000 rows for point reads, singleton updates, and batch-32 updates. Across its six cells, the candidate measured 2.75×, 1.23×, and 1.20× at 1,000 rows, and 2.60×, 1.12×, and 2.20× at 10,000 rows, respectively. Three cells remain below 2×, so the overall SQLite acceptance goal is not met. Read results are essentially unchanged between the package versions under test; do not attribute read wins to the transaction change-set work. See the [full results](/project/package-performance/) and the [reproduction guide](https://github.com/tugrulguner/refpot/tree/main/benchmarks/package-performance).

The provenance records locally built wheels carrying 0.1.1 metadata; they are neither published PyPI 0.1.1 wheels nor measurements of a 0.1.2 package artifact.

## Historical experiment (separate)

The repository separately retains an [audited random-update experiment](https://github.com/tugrulguner/refpot/tree/main/benchmarks/random-updates) with frozen experimental source, 672 raw records, and reproduction commands. Its 3.04–5.95× service result measures existing-row updates with atomic receipt tracking and equal batching in a Linux ARM64 Docker/ext4 VM, not a general database advantage. Reopen with full-state validation loses all 16 cells. These findings are not package performance results.

[View the benchmark chart, complete per-cell results, raw evidence and reproduction](/project/benchmarks/). These are historical prototype measurements, not package benchmarks.

## Not provided or qualified

No SQL, ORM, concurrent readers, multiwriter support, Windows or unsupported architectures, existing-format compatibility, independent physical replicas, or physical power-loss qualification is provided. The package now stages transaction effects as row-local change sets and recovery replays validated row effects without copying unrelated map entries; this does not complete broad performance or durability qualification. See the [package contract](/package-contract/).

Do not infer production readiness or general performance from the experimental alpha or the limited six-cell screen. The overall 2×-over-SQLite target remains an acceptance gate.

## Participate

Read the [design direction](/design/), [qualification method](/performance-method/), and [canonical roadmap](/project/roadmap/). Discuss scoped engine contracts, correctness cases, crash and I/O-failure tests, and measurement methods in [GitHub Issues](https://github.com/tugrulguner/refpot/issues) or the [ModePot community](https://discord.gg/u3AANZr6RG).

[Package contract](/package-contract/) · [Download this page as Markdown](/docs/status.md).
