
RefPot is a custom native embedded database for Python. Starting with 0.1.2, it ships a bounded [SQL preview](/reference/sql-preview/) alongside the [fixed-schema Python API](/package-contract/). The ORM and the unified architecture described below remain planned.

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

## Preview and roadmap

The package preview implements CRUD, transactions and snapshot/WAL persistence, with row-local change sets for staging, nonallocating publication after redo synchronization, and row-local replay. Recovery qualification remains in progress. The historical six-cell package screen recorded three cells below the then-used 2× SQLite target. It used locally built wheels carrying 0.1.1 metadata, not 0.1.2 release artifacts. The fixed speed target is no longer a roadmap gate. See the [roadmap](/project/roadmap/) for open qualification gates and the [performance method](/performance-method/) for evidence requirements.

<a class="next-link" href="/performance-method/">Next — Performance qualification method →</a>
