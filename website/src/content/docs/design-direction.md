---
title: Design direction
slug: design
description: Current RefPot architecture hypotheses, design constraints, and unresolved choices.
---

RefPot is proposed as a custom embedded relational database engine with a simple Python ORM on top. It is not a SQLite wrapper; direct engine use must remain useful without the ORM.

## One semantic execution core

The hypothesis is two entry paths—direct SQL and structured ORM operations—feeding one execution core. The ORM should not generate SQL only for RefPot to parse the same operation back again. Both paths must apply the same validation, constraints, transaction semantics, and recovery behavior.

## Correctness and explicit guarantees first

- **Engine first:** establish correctness and performance before building the ORM.
- **One semantic boundary:** no direct path should bypass validation or constraints.
- **Explicit guarantees:** internal plan selection must not silently weaken durability, isolation, transaction boundaries, or result semantics.
- **Bounded maintenance:** include checkpointing, reclamation, and recovery debt in design and measurement.
- **Simple public use:** keep storage layout, encoding, and routing private unless users need an operational control.

## Open decisions

Language, storage format, index structure, isolation model, SQL compatibility scope, and supported values remain decisions to earn through coherent experiments. A native-language rewrite alone is not a differentiator. No SQLite SQL, file-format, or C API compatibility is promised.

Candidate mechanisms include cache-aware separated key/value layouts, occupancy-dependent routing, preallocated bounded logical redo, incremental dirty-region checkpoints, and mutation-density-aware encoding. These are hypotheses, not selected architecture. The page-image prototype lost against tuned SQLite; it does not rule out a full copy-on-write tree/root-swap design. A Rust rewrite is a permitted option, not proof of performance.

## Research status

Earlier isolated native prototypes inform hypotheses but are not an integrated implementation. They do not establish a durable database, qualified concurrency, a supported API, or product performance claims. See the [roadmap](/project/roadmap/) for current unchecked milestones and the [performance method](/performance-method/) for evidence requirements.

<a class="next-link" href="/performance-method/">Next — Performance qualification method →</a>
