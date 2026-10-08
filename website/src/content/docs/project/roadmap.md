---
title: Roadmap
description: Canonical RefPot research milestones, generated from the repository roadmap.
---


RefPot's goal is a custom embedded relational database engine, usable directly, with a
simple Python ORM on top. The engine is not SQLite underneath. Performance and simplicity
must both be demonstrated through complete operations, not inferred from implementation
language or isolated data structures.

All milestones below are **planned and unchecked**. Earlier scratch experiments inform the
hypotheses; they do not complete a product milestone. This roadmap has no delivery dates.

## Non-negotiable gates

- Own the execution and storage engine; do not substitute a SQLite wrapper.
- Keep the engine independently useful without the ORM.
- Require at least 2× over SQLite on a declared, agreed workload matrix before making the
  corresponding performance claim. Do not narrow the matrix after seeing failed results.
- Preserve equivalent correctness, returned data, transaction boundaries, and durability.
- Keep ordinary usage straightforward; internal adaptation must not become mandatory
  application configuration or silently change guarantees.
- Publish failed cells, raw evidence, maintenance costs, and limitations alongside wins.

## 0. Fix the contract and qualification matrix

Define what the first engine promises before optimizing it.

- [ ] Specify supported values, key semantics, missing and duplicate behavior, ordering,
      validation, and the first constraint subset.
- [ ] Specify begin/commit/rollback, visibility, acknowledged durability, crash behavior,
      error outcomes, and what happens after an uncertain commit.
- [ ] Select the first concurrency/isolation contract and document unsupported patterns.
- [ ] Agree the engine workload matrix: successful CRUD, misses, repeated mutations,
      rollback, mixed workloads, point/range reads, batch sizes, dataset sizes, key locality,
      memory limits, and concurrent request counts.
- [ ] Identify SQLite baseline configurations and fairness rules for each workload.
- [ ] Design minimal developer workflows for engine-only use and the later ORM; evaluate
      ceremony and explicit transaction ownership without promising public names yet.

**Exit:** a reviewable semantic contract, fixed acceptance matrix, and expected-state oracle.
SQL/API/file compatibility, language, and storage architecture remain explicit decisions,
not assumptions inherited from a prototype.

## 1. Build one coherent durable engine slice

The next implementation gate is an integrated engine, not another disconnected lookup win.

- [ ] Implement successful durable insert, read, update, and delete against a real index
      and stored record representation; no fixture-derived values or fixed-key shortcuts.
- [ ] Enforce the chosen value/constraint subset through the same operation boundary.
- [ ] Implement atomic commit and rollback, including repeated mutations of the same row.
- [ ] Define a versioned, self-describing storage format with validated metadata, bounds,
      checksums, and rejection of unsupported versions.
- [ ] Implement bounded logging/checkpointing and safe reclamation; retain required redo
      until replacement state is durably published.
- [ ] Exercise concurrent requests under the declared visibility/conflict contract; keep
      single-writer serialization explicit if chosen rather than implying multiwriter support.
- [ ] Expose an engine-only executable harness with complete final-state and reopen checks.

**Exit:** durable CRUD, concurrent requests, bounded recovery, and transaction semantics work
as one system. Performance alone cannot waive a correctness failure.

### Candidate mechanisms, not settled architecture

Evaluate cache-aware separated key/value layouts and occupancy-dependent routing,
preallocated bounded logical redo, incremental dirty-region checkpoints, and
mutation-density-aware encoding. Compare complete combinations, including their maintenance
and recovery costs. Keep full-snapshot ring designs as baselines, not automatic winners.

The tested page-image prototype lost against tuned SQLite; that does not rule out a full
copy-on-write tree/root-swap architecture. A Rust rewrite is a permitted implementation
choice, not evidence of speed. Do not select a language before the relevant measurement.

## 2. Qualify failure behavior and recovery

Run these checks during milestone 1 and expand them before trusting durability claims.

- [ ] Differential and state-machine tests for CRUD, duplicates, misses, constraints,
      transaction sequences, rollback restoration, and reopen.
- [ ] Process termination at record write, sync, acknowledgment, checkpoint publication,
      wraparound, and reclamation boundaries; verify permitted outcomes against a ledger.
- [ ] Fault injection for short writes, interrupted syscalls, EIO, ENOSPC, allocation
      failures, and failures during recovery itself.
- [ ] Reject corrupted headers, counts, lengths, payloads, trailers, and generations without
      accepting fabricated state or performing unbounded allocation.
- [ ] Test interrupted checkpoints, stale temporary files, multiple wraps, restart,
      continued writes, and a second restart.
- [ ] Verify concurrent visibility, conflicts, transaction identity, and error outcomes.
- [ ] Run independent sanitizer/fuzz campaigns and preserve exact tested source identities.
- [ ] Document filesystem/synchronization assumptions and verify the baseline uses matched
      primitives. Process-kill tests are not physical power-loss qualification.

**Exit:** a published failure model and passing qualification corpus. State remaining
unsupported guarantees plainly; “fsync was called” is not a universal durability proof.

## 3. Earn the native-engine performance claim

- [ ] Benchmark the coherent slice against prepared native SQLite with identical data,
      returned tuples, real writes, transaction boundaries, and durability policy.
- [ ] Sweep relevant SQLite checkpoint settings and retain the best-tested baseline per cell.
- [ ] Include commit synchronization, checkpoints, compaction, reclamation, and final
      maintenance; report initialization and calibration costs separately.
- [ ] Calibrate trial duration, alternate candidate order, repeat pairs, and repeat complete
      campaigns when variance is suspicious. Preserve both runs, including disagreements.
- [ ] Persist raw trials, environment identity, source hashes, configurations, exact matrix,
      expected-state validation, and a programmatic analysis/reproduction command.
- [ ] Measure throughput, p95/p99, memory, total disk footprint including overlapping
      checkpoint files, sustained log growth, and recovery time across dataset scaling.
- [ ] Require reproducible 2× performance across the agreed matrix with explicit latency
      and resource criteria; failed small-transaction cells remain failures.

**Exit:** a reproducible native-engine result covering the agreed scope. If the gate fails,
report failure and investigate the mechanism; do not promote a single winning batch as an
across-the-board result. Keep macOS native, Linux VM, and bare-metal evidence separate.

### Guarded optimization experiments

- **Routing:** test representative held-out requests and measure selector regret,
  calibration, switching, and migration. Use hysteresis and a deterministic fallback;
  choosing the fastest tiny pilot is not a sufficient policy.
- **Encoding/checkpoints:** compare logical redo, dense deltas, and incremental checkpoints
  end-to-end with replay/reclamation safety intact.
- **Group commit:** combine already-waiting compatible work without added waiting to grow
  groups; preserve each transaction's identity and acknowledgment boundary. Compare against
  a similarly coalesced SQLite frontend as well as serial SQLite. One outstanding sequential
  transaction cannot benefit from nonexistent neighbors.
- **Cache evidence:** distinguish exposed cache topology from measured cache misses.
  Do not claim PMU evidence without actual counters.

## 4. Stabilize relational execution and direct use

- [ ] Define and implement the first SQL subset, with explicit type, NULL, collation,
      conversion, constraint, and ordering semantics.
- [ ] Add parameterized SQL preparation/planning and a structured-operation path feeding
      the same execution core, without bypassing constraint or transaction enforcement.
- [ ] Add the agreed range, projection, filtering, and relational operations incrementally;
      document unsupported SQL rather than implying full compatibility.
- [ ] Provide actionable errors, plan inspection, and bounded operational statistics.
- [ ] Expand correctness and benchmark matrices when functionality expands; rerun the gates.
- [ ] Ship runnable engine-only examples and storage/recovery documentation.

**Exit:** independently useful direct engine access with a documented relational scope.
SQLite SQL, file, or C API compatibility requires a separate explicit decision and tests.

## 5. Build and verify the Python binding

- [ ] Define a small public interface with predictable types, lifetimes, errors, and explicit
      transactions; keep tuning machinery private by default.
- [ ] Verify result ownership, cancellation/error boundaries, and chosen thread/concurrency
      behavior; declare interpreter support based on tested builds.
- [ ] Compare complete public operations against Python SQLite interfaces with equivalent
      result materialization; measure binding overhead separately from native execution.
- [ ] Provide installable artifacts and runnable `examples/` verified through the installed
      package, not only source-tree imports.

**Exit:** usable engine-only Python access with independently published binding performance
and no implication that native-engine ratios automatically carry through Python.

## 6. Add the simple ORM

- [ ] Define a minimal model/query/transaction interface using concrete developer tasks,
      not a large speculative configuration surface.
- [ ] Compile ORM requests to validated structured operations instead of requiring an
      ORM → SQL → parser round trip on RefPot's engine.
- [ ] Keep transactions, query execution, and expensive loading visible; avoid mandatory
      repository/factory stacks and hidden queries.
- [ ] Prove ORM/direct-operation semantic equivalence for the supported feature set.
- [ ] Benchmark complete ORM workflows against optimized SQLAlchemy paths and raw-engine
      baselines, with returned objects, validation, writes, and commits included.
- [ ] Ship runnable CRUD, transaction, relationship, and failure examples as features land.

**Exit:** an ORM whose simplicity is demonstrated in ordinary usage and whose performance
is measured separately. “Fastest ORM” is not a claim until a defined comparison supports it.

## 7. Prepare a supported release

- [ ] Settle license and distribution policy before inviting package adoption.
- [ ] Add packaging, supported-platform/interpreter CI, reproducible tests, and release
      automation once an actual implementation exists.
- [ ] Document storage versioning, backup/restore, migrations, operational limits, and the
      supported failure/concurrency model.
- [ ] Verify installation, examples, recovery, and the declared performance matrix from
      release artifacts on the supported environments.
- [ ] Align README, reference docs, roadmap, and release notes with what actually ships.

**Exit:** a supported release with honest capability boundaries, reproducible evidence,
and no unsupported performance or durability guarantees.

## Outside this initial push

No server deployment, cloud replication, distributed consensus, broad compatibility promise,
public tuning framework, or production engine is implied by this documentation launch.
Research prototypes remain experimental until deliberately integrated and qualified.

[Download the canonical roadmap as Markdown](/docs/project-roadmap.md).
