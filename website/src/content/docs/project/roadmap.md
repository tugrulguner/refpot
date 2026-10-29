---
title: Roadmap
description: Canonical RefPot research milestones, generated from the repository roadmap.
---


RefPot's direction is a **self-maintaining embedded relational database for Python**,
with an optional internal agent that designs workload-specific execution structures.
RefPot owns its native storage and execution engine; it is not a SQLite wrapper.

Developers define source tables, derived relations and rules. The planned engine maintains
that model transactionally. Its optimization agent investigates **how to compute and
maintain the model**, never what the application's rules or answers should mean.

This is the development direction, not a description of shipped capabilities. A checked item means only that bounded deliverable exists; it does not imply a supported release. All new milestones below are planned and unchecked. There are no delivery dates.

The fixed **2× SQLite target is withdrawn**. Preserve achieved improvements, raw results
and unfavorable comparisons, but do not use a speed multiplier as the product thesis or
release gate. Older reports and target wording elsewhere describe the historical campaign;
this roadmap defines the current objective, without changing those measurements.

## Current implementation: experimental alpha

The fixed-schema Python `Database` / `Row` API supports CRUD, explicit transactions and
snapshot/WAL persistence. It is thread-affine and exclusively owned by one process.
Derived relations, internal optimization agents, SQL, ORM and concurrent access are **not
shipped**. See the [package contract](/package-contract/),
[package results](/project/package-performance/), and
[release checklist](https://github.com/tugrulguner/refpot/blob/0f880f5ef2b17405bc1b6f3c4f43c050d99878b6/docs/releasing.md).

### Implemented foundations

- [x] Configure package metadata, Python 3.11–3.14 Linux/macOS CI, artifact verification, and tag-triggered release automation. Passing installed-wheel lanes verify only their tested behavior; they do not establish physical power-loss safety.
- [x] Publish version 0.1.1 as a normal latest GitHub release and on PyPI; verify public artifact installation. This publication milestone does not complete platform, example, recovery, or performance qualification.
- [x] Implement fixed-schema CRUD, explicit transactions, snapshot/WAL persistence, change-set staging/commit, and row-local recovery replay. This is not the complete durability qualification gate.
- [x] Run a six-cell actual-package comparison against prepared SQLite using locally built wheels carrying 0.1.1 metadata. Three of six cells were below 2×. These remain historical screening results, not measurements of a 0.1.2 artifact or an active multiplier gate.
- [x] Add the MIT license and prepare 0.1.2 documentation, metadata, changelog and artifact presentation. Preparation alone does not publish or qualify that release.

### Still-open qualification and product gates

- [ ] Complete native CRUD/transaction/recovery failure qualification; implementation exists but qualification remains in progress.
- [ ] Verify wheel/source distributions and execute installed CRUD/transaction examples on all declared platforms.
- [ ] Qualify errors, corruption, lock ownership and process-restart behavior; retain explicit filesystem assumptions and limits beyond process/fault tests.
- [ ] Expand package measurements to sustained maintenance/checkpoints, mixed/insert/delete workloads, dataset scaling and release artifacts. Add concurrency measurements only when that capability exists.

Retain these obligations while developing the new model. Existing package behavior and
storage compatibility must not change without an explicit migration contract. Observation,
MVCC and dependency-tracking experiments may supply requalified components; scratch tests
and native-relative speedups do not establish shipped functionality or SQLite superiority.

## Product boundary and intended advantage

The first application model is resource allocation:

`reservations → usage totals → available capacity → eligibility`

A transaction changes reservations, propagates affected results, checks capacity and team
limits against the complete proposed state, then commits everything or rejects everything.
Readers must not see new reservations with old availability. Restart must restore one
coherent source/derived/model version.

For supported definitions, applications should not need manually maintained derived-table
writes, cache-invalidation handlers, refresh workers or derived-state reconciliation scripts.
Domain rules remain developer-owned. Dense changes can still require substantial work;
there is no universal constant-time or delta-only cost promise.

Two parts share one engine:

- **Deterministic core:** storage, typed relational execution, incremental maintenance,
  constraints, transactions, validation, publication and recovery.
- **Optional internal optimization agent:** inspect sanitized execution evidence, propose
  shared physical representations and maintenance plans, and run budgeted experiments.
  A deterministic checker and runtime policy decide whether candidates are admissible and
  useful enough to install. The agent cannot approve its own candidate.

RefPot is a database engine, not a backend package. Summonpot or another caller owns
endpoints, application goals, business agents, external tools and approval workflows.
Internal engine agents are in scope; application orchestration is not.

### Competitive thesis to prove

Incremental views, reactive databases, learned optimizers and verified rewrites already
exist. Atomic derived maintenance alone is not new: PostgreSQL + pg_ivm is a direct
baseline, and a competent SQLite layer may reproduce the application behavior.

The research target is **agent-guided synthesis of shared, transactionally maintained
physical representations inside an embedded engine**, including their maintenance,
installation and retirement. The intended user benefit combines less application-owned
synchronization with less manual physical-design work. Neither algorithmic novelty nor
competitive superiority is established by this roadmap.

Compare complete models against SQLite with reusable/generated maintenance, pg_ivm and
an appropriate reactive/incremental platform. Consider Convex, SpacetimeDB, Feldera,
Pathway and Differential Datalog according to their actual contracts. Compare agent-guided
search with non-agent search over the same candidate language, not only an untuned baseline.

## Non-negotiable gates

- Keep ordinary database operations independently useful without a model, server or ORM.
- Preserve exact query meaning, types, multiplicities, ordering, errors, isolation and
  durability across every optimization; unsupported transformations must be rejected.
- Finish exact derived state and write-time invariants before acknowledging a commit.
  Do not silently replace exact results with eventually consistent outputs.
- Prepare allocations before publication and keep inference outside transaction locks and
  the query hot path. Recovery must not call a model or arbitrary application Python.
- Keep agent execution optional, bounded and opt-in; deny arbitrary generated native code,
  unrestricted production writes and application tools. Exclude row values, SQL literals
  and sensitive identifiers from provider telemetry by default.
- Measure complete read/write, maintenance, construction, migration, reclamation and
  recovery costs. Retain historical results and report regressions alongside improvements.
- Do not claim arbitrary Python purity, incrementalize arbitrary bytecode, or mistake an
  LLM assertion or a passing test suite for a proof of equivalence.
- Prove standard and free-threaded Python support on actual interpreter builds. Threaded
  native tests alone establish neither binding safety nor useful multicore execution.

## Delivery sequence

M0–M1 establish the model and native relational representation. M2–M3 investigate agents
against that deterministic foundation, before broad API expansion. M4–M5 qualify whole-model
persistence and concurrency; M6 integrates safe adaptive installation. M7 delivers the
installed consumer experience. Failure tests start with each component, not at the end.
Offline agent experiments do not depend on online promotion being finished.

## M0. Freeze a complete model and competent controls

- [ ] Specify typed source tables, derived definitions, keys, duplicate/NULL semantics,
      arithmetic/overflow, ordering, errors, invariants and transaction visibility.
- [ ] Define the resource-allocation model and a second pricing or permissions model to
      reject domain-specific hardcoding. Include updates, deletes and multi-row rollback.
- [ ] Build an independent full-recomputation oracle and a competent SQLite control with
      reusable/generated maintenance. Exercise pg_ivm and a relevant incremental platform
      before making comparative claims; documentation tables are not executable controls.
- [ ] Freeze workloads with narrow and broad changes, shared and disjoint computations,
      read-heavy and write-heavy phases, memory budgets and recovery expectations.
- [ ] Record the application-owned propagation, tuning and repair responsibilities in
      each implementation, not merely API names or line counts.

**Exit:** executable expected-state traces and controls for two models. Mutants omitting
propagation, absence dependencies or atomic publication must fail. Separate product
convenience, native execution advantage and originality findings.

## M1. Build the deterministic self-maintaining relational core

- [ ] Add multiple typed tables, primary keys and equality indexes, using a bounded native
      relational intermediate representation shared by execution and maintenance.
- [ ] Implement filter/project, equijoins, anti-joins, grouped count/sum, chained derived
      relations and final-state invariants. Start with an acyclic graph and explicit types.
- [ ] Maintain results through inserts, updates and deletes on either side of a join;
      preserve multiplicities, empty groups, negative observations and checked arithmetic.
- [ ] Propagate transaction deltas privately, share supported intermediate work and evaluate
      invariants against the complete final candidate, not statement-order artifacts.
- [ ] Publish source, derived and dependency/index changes atomically or discard them all;
      maintain read-your-writes and operation-level failure semantics.
- [ ] Compare every committed source and derived relation with the independent oracle.
      Expose operator visits and maintenance work; do not hide full reruns behind an API.

**Exit:** both complete models run through the same native implementation without
application-written propagation routines. Readers see no mixed epoch and failed
transactions leave no partial graph changes. This is the first functional deliverable,
not another isolated lookup or aggregate benchmark.

## M2. Build a restricted engine-agent experimentation interface

- [ ] Expose sanitized operator structure, cardinality/work counters and read/write costs,
      with explicit memory, time, inference and experiment budgets.
- [ ] Let one optional agent inspect, hypothesize, compose approved operators, experiment
      on isolated state and revise proposals. Keep deterministic execution as the default.
- [ ] Define a candidate artifact covering the shared representation, read plans,
      maintenance derivation, assumptions and resource estimates—not prose tuning advice.
- [ ] Implement a small deterministic checker for supported rewrite derivations and side
      conditions. Validate initial-state equivalence and preservation under supported
      update transitions; generate maintenance through trusted incrementalization rules.
- [ ] Reject unknown operators, unsupported proofs, unsafe overflow rewrites, faulty delete
      maintenance and proposals crossing opaque Python-function boundaries.
- [ ] Fail closed on malformed/untrusted model output, provider failure or exhausted budget
      without interrupting normal database operations. No inference under writer locks.

**Exit:** a real agent produces a compositional candidate that the engine can execute in
isolation and validate. Faulty rewrites and maintenance mutants are rejected. Provider-free
fixtures test the protocol but do not substitute for exercising the actual agent loop.

## M3. Establish whether agent-guided specialization earns its place

- [ ] Use overlapping joins/aggregates to seek a shared representation across queries,
      rather than only selecting an index or a complete pre-enumerated plan.
- [ ] Compare ordinary optimization, competent hand-factored plans, deterministic search
      over the **same candidate language**, and agent-guided search under matched budgets.
- [ ] Charge inference, all trials, representation construction, ongoing writes, retained
      memory, catch-up and retirement—not just favorable read-query latency.
- [ ] Test held-out workloads and read-heavy/write-heavy transitions. Measure search cost,
      plan quality and regressions, including cases where no change is best.
- [ ] Use agent-generated adversarial mutations as extra testing, not a replacement for
      the deterministic checker or independent oracle.
- [ ] Preserve candidates, derivations, model/provider identity, budgets, sanitized traces,
      exact source identities and reproducible analysis without publishing secrets.

**Exit:** a verified agent-proposed structure demonstrates a useful reduction in physical-design
work or full-workload resource cost against strong controls. Any claimed agent-specific
advantage must survive equal-budget non-agent search. If that does not hold, retain useful
core work and keep agent specialization experimental; do not claim a differentiator from
one winning query or simply searching more candidates. There is no fixed speed multiplier.

## M4. Qualify durable whole-model state and definition evolution

- [ ] Extend the versioned storage contract to source rows, accepted derived outputs,
      definition identity and required dependency/index state at one commit frontier.
- [ ] Choose explicitly which native structures are persisted versus rebuilt behind a
      recovery barrier. Recovery must not call inference or registered Python functions.
- [ ] Preserve bounded logging/checkpointing, capacity checks before acknowledgment,
      allocation-before-publication and poisoned-writer behavior after uncertain I/O.
- [ ] Inject short writes, interrupted syscalls, EIO, ENOSPC and allocation failures during
      preparation, append, sync, publication, checkpoint, recovery and reclamation.
- [ ] Test process termination, corrupted framing/lengths/metadata, interrupted checkpoints,
      stale temporary files, reopen, continued writes and a second restart.
- [ ] Version definitions explicitly. Implement offline atomic model migration first;
      missing/incompatible definitions must not silently present stale state as current.
- [ ] Document backup/restore, format transitions, filesystem assumptions and unsupported
      failure guarantees; process-kill testing is not physical power-loss qualification.

**Exit:** acknowledged transitions survive restart as a coherent model. Unacknowledged
transitions may recover wholly old or wholly new, never partial. Interrupted migrations
expose one complete definition version, and bounded recovery preserves subsequent use.

## M5. Qualify concurrent execution and supported Python computations

- [ ] Implement independently owned transaction contexts, private graph evaluation, exact
      conflict validation and short publication critical sections.
- [ ] Test phantoms, missing-row dependencies, failed observations, own-write ordering and
      write skew through derived constraints against serializable-history oracles.
- [ ] Revalidate reusable observation/MVCC components and bound snapshot, row-version,
      dependency-edge and retired-plan retention; do not transplant prototype mutexes or
      fixed schemas as the product architecture.
- [ ] Add optional keyed deterministic Python cells over immutable tracked inputs, with
      explicit definition versions, dynamic dependencies and whole-cell reruns. Treat
      registered code as trusted, not sandboxed or automatically proven pure.
- [ ] Test branch-dependent edge replacement, caught lookup failures, unchanged-output
      propagation stops and computation exceptions. Reject undeclared side effects by
      contract; do not claim a decorator can enforce arbitrary Python purity.
- [ ] Run Python callbacks outside the publication lock; release the GIL for native work.
      Qualify ownership/lifetimes on standard and actual free-threaded CPython builds.
- [ ] Exercise native sanitizer/race/fuzz campaigns and measure real overlap of independent
      graph regions. Report hot-aggregate serialization and dense fan-out honestly.

**Exit:** source and derived invariants remain correct under concurrent transactions;
independent native work actually overlaps. Supported Python cells and their dependency
changes commit or abort together. No arbitrary caller callbacks are replayed on retry.

## M6. Install and retire verified physical plans safely

- [ ] Build a candidate representation privately from a pinned snapshot while the current
      authoritative plan remains usable; track and apply intervening committed changes.
- [ ] Verify exact catch-up and compatible model identity, then durably switch the physical
      plan catalog at a consistent epoch without changing logical definitions.
- [ ] Retain old plans and their required state for active readers; reclaim only after
      lifetime constraints permit it and account for overlapping memory/storage.
- [ ] Persist accepted artifacts and required metadata so restart needs no model access.
- [ ] Use deterministic activation budgets and regression policy. Keep a usable baseline;
      account for rebuild/catch-up if a retired representation is needed for fallback.
- [ ] Test crashes, concurrent updates, model changes, provider loss and allocation failures
      during build, catch-up, switch, fallback and reclamation.

**Exit:** switching plans, reverting and restarting preserve identical logical results,
errors and transaction guarantees. The agent cannot approve or publish its own proposal.
No claim that rollback is instantaneous or free when old state was not maintained.

## M7. Deliver the usable Python engine and coherent model lifecycle

- [ ] Expose a small structured relational interface with explicit transactions, derived
      relations, invariants, optional keyed cells and actionable execution reports.
- [ ] Ship runnable `examples/` for resources, a second domain, rejection/rollback, recovery,
      definition changes and agent specialization versus model-free execution.
- [ ] Build release artifacts and run examples twice through installed wheels outside the
      checkout on the declared platform/interpreter matrix; preserve existing API tests.
- [ ] Add coherent snapshot-plus-committed-change batches with an explicit slow-consumer
      policy. No failed-transaction notifications, implied durable resume or external
      exactly-once effects.
- [ ] Publish complete workload measurements: latency/throughput, memory, storage,
      synchronization, checkpoints, maintenance, recovery and optimization costs. Preserve
      paired repeats, raw results, strongest eligible controls and reproduction commands.
- [ ] Align public docs and agent-readable exports with actual delivered capabilities;
      keep experimental agent search separate from qualified deterministic behavior.
- [ ] Complete release/publisher prerequisites, then obtain separate authorization for tags,
      publication and deployment and independently verify public artifacts.

**Exit:** a developer installs RefPot, defines either reference model, changes source rows
and gets correct maintained results, atomic rejection, concurrent access and restart
recovery without writing synchronization machinery. Where M3 and M6 are qualified, an
optional agent can specialize that execution without changing the application's contract.
A model outage does not prevent ordinary database use.

## Later extensions, not prerequisites for the first useful model

- [ ] Broaden SQL through the same relational/transaction boundary; specify and test the
      supported subset rather than promise SQLite SQL, file or C API compatibility.
- [ ] Add a simple ORM over validated structured operations, preserving explicit queries
      and transactions. Measure complete ORM usage separately from native/Python execution.
- [ ] Investigate monotone recursion, online logical-model upgrades and larger-than-memory
      operation with separate contracts, failure tests and competitive controls.

No backend framework, chat-to-SQL product, business-agent runtime, mandatory external
service, cloud replication, distributed consensus or public tuning framework is implied.
The first priority remains one complete self-maintaining model and a verified, useful
agent-proposed execution structure—not a larger compatibility checklist.

[Download the canonical roadmap as Markdown](/docs/project-roadmap.md).
