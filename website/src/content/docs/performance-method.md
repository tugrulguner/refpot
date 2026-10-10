---
title: Performance qualification method
description: Evidence standards for any future RefPot-versus-SQLite performance claim.
---

**At least 2× improvement over SQLite is an acceptance target, not an achieved guarantee.** No result in this checkout establishes a general database performance advantage. The [audited random-update experiment](https://github.com/tugrulguner/refpot/tree/main/benchmarks/random-updates) supplies experimental source, 672 raw records and executable analysis. It passes the service/setup/p99 matrix for existing-row updates with receipt tracking, not general CRUD. Reopen with full-state validation loses every cell; prior misses remain visible.

## Compare equivalent work

Before claiming a win, define and publish the workload matrix and retain every passing and failing cell. Compare equivalent operations, returned values, transaction boundaries, constraints, and durability acknowledgments against prepared SQLite and the best-tested SQLite configuration for each workload.

Measure three layers separately:

1. **Engine:** native RefPot operations versus prepared native SQLite.
2. **Python binding:** equivalent public operations and materialized results versus Python SQLite interfaces.
3. **ORM:** complete application operations versus optimized ORM baselines, alongside raw-engine measurements.

Include synchronization, commit, checkpoint, compaction, reclamation, and final maintenance costs. Report tail latency, memory, disk growth, recovery, and concurrency separately. Keep native macOS, Linux VM, and bare-metal evidence distinct. Repeat complete campaigns when results are unstable.

## Matrix and reproducibility gates

The canonical [roadmap](https://github.com/tugrulguner/refpot/blob/main/ROADMAP.md) requires correctness cases, successful CRUD, misses, repeated mutations, rollback, mixed workloads, point/range reads, batch and dataset sizes, key locality, memory limits, and concurrency. Persist raw trials, environment identity, source hashes, configurations, the exact matrix, expected-state validation, and a reproduction command. Retain failed cells; do not narrow the matrix after results are known.

A faster lookup or favorable large batch does not establish that RefPot is faster as a database. Dataset scaling, recovery, durability and small-transaction outcomes matter. Claim only the exact measured scope with its limitations.

<a class="next-link" href="/status/">Next — Research status →</a>
