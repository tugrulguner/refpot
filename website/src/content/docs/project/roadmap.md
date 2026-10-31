---
title: Roadmap
description: Canonical RefPot research milestones, generated from the repository roadmap.
---


RefPot's direction is a **self-maintaining embedded relational database for Python** whose
primary ambition is to invent a better deterministic engine and a simpler database experience.
Storage, queries, writes, transactions, maintenance, concurrency and recovery are all part of
that design problem—not a conventional substrate to finish before adding the interesting AI.
RefPot owns its native storage and execution engine. It is not a SQLite wrapper.

RefPot must earn adoption **with agents completely disabled**. Better ordinary database
operations and better Python usability are first-class product objectives. Optional natural-
language querying and engine agents add capabilities to that database; they are not its main
justification or a substitute for engine invention. SQL and NL still share one query interface.

The goal is not merely a natural-language front end, a faster fixed-schema map, or a familiar
engine with a new API. Challenge unnecessary work, duplicated state and developer ceremony
throughout the core. Useful releases can precede a proven original mechanism, but conventional
feature completion does not satisfy the architectural ambition. Neither a failed optimizer
experiment nor an unresolved novelty claim should block independently useful progress.

This is the development direction, not a description of shipped capabilities. A checked item means only that bounded deliverable exists; it does not imply a supported release. All new milestones below are planned and unchecked. There are no delivery dates.

The fixed **2× SQLite target is withdrawn**. Preserve achieved improvements, raw results
and unfavorable comparisons, but do not use a speed multiplier as the product thesis or
release gate. Older reports and target wording elsewhere describe the historical campaign;
this roadmap defines the current objective, without changing those measurements.

## Current implementation: experimental alpha

The fixed-schema Python `Database` / `Row` API supports CRUD, explicit transactions and
snapshot/WAL persistence. It is thread-affine and exclusively owned by one process.
Derived relations, internal optimization agents, SQL, ORM and concurrent access are **not
shipped**. Natural-language query generation is also not shipped; there is no implemented
SQL `execute` interface to which an agent flag can simply be added. See the
[package contract](/package-contract/), [package results](/project/package-performance/),
and [release checklist](https://github.com/tugrulguner/refpot/blob/1b6f850613936591f13a04bf7ddd17505cc9e219/docs/releasing.md).

### Implemented foundations

- [x] Configure package metadata, Python 3.11–3.14 Linux/macOS CI, artifact verification, and tag-triggered release automation. Passing installed-wheel lanes verify only their tested behavior; they do not establish physical power-loss safety.
- [x] Publish version 0.1.1 as a normal latest GitHub release and on PyPI; verify public artifact installation. This publication milestone does not complete platform, example, recovery, or performance qualification.
- [x] Implement fixed-schema CRUD, explicit transactions, snapshot/WAL persistence, change-set staging/commit, and row-local recovery replay. This is not the complete durability qualification gate.
- [x] Run a six-cell actual-package comparison against prepared SQLite using locally built wheels carrying 0.1.1 metadata. Three of six cells were below 2×. These remain historical screening results, not measurements of a 0.1.2 artifact or an active multiplier gate.
- [x] Add the MIT license and prepare 0.1.2 documentation, metadata, changelog and artifact presentation. Preparation alone does not publish or qualify that release.
- [x] Merge a bounded native transactional relational model slice with independent-oracle, rollback, mutant and sanitizer tests. It is volatile, single-threaded and separate from the installed Python API—not a durable relational release. See its [contract](https://github.com/tugrulguner/refpot/blob/1b6f850613936591f13a04bf7ddd17505cc9e219/research/application-model/CONTRACT.md) and [results](https://github.com/tugrulguner/refpot/blob/1b6f850613936591f13a04bf7ddd17505cc9e219/research/application-model/RESULTS.md).

### Still-open qualification and product gates

- [ ] Complete native CRUD/transaction/recovery failure qualification; implementation exists but qualification remains in progress.
- [ ] Verify wheel/source distributions and execute installed CRUD/transaction examples on all declared platforms.
- [ ] Qualify errors, corruption, lock ownership and process-restart behavior; retain explicit filesystem assumptions and limits beyond process/fault tests.
- [ ] Expand package measurements to sustained maintenance/checkpoints, mixed/insert/delete workloads, dataset scaling and release artifacts. Add concurrency measurements only when that capability exists.

Retain these obligations while developing the relational engine. Preserve existing
`Database` / `Row` behavior and storage compatibility unless an explicit migration contract
is approved. Observation, MVCC and dependency-tracking experiments may supply requalified
components; scratch tests and native-relative speedups do not establish shipped functionality.

### What the latest research changes—and does not change

Local, unpublished experiments explored shared join plans and maintained keyed summaries.
The real agent lost to deterministic search in the former and tied competent hand-factored
and deterministic controls in the latter. Summaries removed substantial work relative to
an unfactored control on some workloads, but also regressed on a smaller case. These are
restricted experimental observations, not published-package performance claims or a proof
of an original mechanism. The evidence is not part of this roadmap-only change.

Retain useful native representations and ordinary fallbacks. Keep seeking more fundamental
ways to remove duplicated state and work, but do not make an optimizer-agent win a
prerequisite for SQL, natural-language querying, or durable self-maintenance. Query generation
and physical synthesis solve different problems and must pass different gates.

## Deterministic engine and usability are the primary design agenda

The central question is: **why choose RefPot for ordinary database work when no agent is
configured?** A natural-language demo cannot answer it. Neither can implementing SQL, using
C++, or packaging known operators. The intended answer must combine a concrete engine
advantage with a simpler complete developer workflow, under explicit workload and guarantee
boundaries. There is no claim that one design will win every workload.

Start this work in M0–M1; it is **not deferred to M7** or restricted to agent-generated plans.
Treat the current map-backed package, volatile relational slice and earlier experiments as
baselines and components to challenge—not as the settled future architecture. Preserve the
shipped contract while investigating alternatives in isolated native slices. Freeze observable
semantics before interfaces harden; do not prematurely freeze the physical representation.

### Core architectural questions and evidence

| Design axis | Ambition to investigate | Evidence required with agents disabled |
| --- | --- | --- |
| **Storage and access design** | Co-design authoritative records, lookup/range access, indexes and query execution instead of accepting separate representations and conversions by default. Compare row/column/hybrid and established storage organizations where relevant; do not select or reject a family by fashion. | Point/range reads, joins, singleton/batch writes and scaling; complete memory, write-amplification and maintenance costs, including losing cases. |
| **One change, less repeated work** | Investigate whether one typed change representation can drive visibility, index updates, derived maintenance, constraint checks and durable evidence without repeated full-state scans, copies or translations. Share necessary work across operations, not only across agent-selected queries. | Original-state oracles, insert/update/delete/rollback, sparse and broad changes, transaction acknowledgment and retained-state accounting. Removing work must not move an uncounted cost into commit or recovery. |
| **Concurrency by construction** | Design ownership, versions, dependency validation and publication together so independent work can overlap without making every operation pay for unrelated work. Avoid treating a global lock or the GIL as the architecture. | Serializable-history checks where promised, conflicts/phantoms/write skew, actual multicore overlap, skewed workloads, bounded versions and reclamation. |
| **Durability without redundant machinery** | Challenge which state and transition evidence must be stored, rebuilt or duplicated; integrate commit, checkpoint and recovery design rather than bolt persistence onto a volatile result. | Equal acknowledgment guarantees, I/O/crash/corruption tests, bounded recovery and continued use, full checkpoint/space/reclamation cost. Fewer syncs obtained by weakening acknowledgment guarantees are not an architectural win. |
| **Python usability as an engine constraint** | Design ordinary schema definition, typed parameters/results, explicit transactions, bulk operations and lifecycle together. Minimize conversion and ownership friction without hidden queries, flushes, mandatory sessions/repositories or an ORM dependency. | Runnable installed workflows for setup, querying, mutation, rollback, migration and reopen; API concept/lifetime inventory, error-recovery steps and Python-boundary cost—not just shorter snippets. |

These are architectural hypotheses, not names for already-invented mechanisms. For each
candidate, state the unnecessary work or user responsibility it removes, the invariant that
makes removal valid, nearest prior art, shifted costs and a falsifying experiment. Record
counterexamples and reject cosmetic simplifications honestly; a negative result must refine the
next architectural question, not turn engine invention into an optional future extra.

### An agent-free adoption case, not just an agent-free fallback

Use a complete Python workflow: define tables, load/update data, run repeated queries, commit
or reject a multi-row change, maintain declared results, evolve definitions and reopen after
failure. Compare with competent SQLite usage and appropriate alternatives under matched
semantics. Track runtime work, latency distributions, throughput, memory/storage and recovery
alongside setup concepts, manual synchronization, tuning and repair responsibilities.

Separate three verdicts: **usable deterministic database**, **demonstrated engine/usability
advantage**, and **original mechanism**. The first can ship honestly before the others, but
does not complete them. Agent-mode results cannot clear either deterministic advantage gate.
Keep fast ordinary operations, low overhead and predictable scaling as engineering objectives
without reinstating a universal speed multiplier. Agent features must not impose provider,
configuration or steady-state inference overhead on ordinary database use.

## One query interface, one native execution engine

**Proposed API, not available in the published package.** The exact result/configuration
names remain to be specified in M0; the same method and `query` parameter are the intended
contract. Assume the example's tables or derived relations have already been declared.

```python
db.execute(query="SELECT name FROM teams WHERE available_slots >= 2")

db.execute(
    query="Find teams with at least two available slots",
    agent=True,
)
```

- Default / `agent=False`: interpret `query` as SQL; bind parameters, validate and execute.
- `agent=True`: interpret that same input as natural language; a configured query-generation
  agent writes supported SQL, then RefPot validates and executes it. Do not guess the input
  language. Missing agent configuration is an explicit error, not a fallback to another mode.
- Handwritten and agent-generated SQL use the **same parser, binder, permission checks,
  logical IR, native planner and executor**. SQL is not delegated to SQLite, and an agent's
  prose answer is not a database result.
- Both paths use the same typed result and execution-error contract. Agent mode additionally
  exposes generated SQL, bound values, assumptions and generation provenance through
  inspectable metadata, subject to redaction policy. Generation/clarification/provider errors
  remain distinguishable from parser, transaction and storage errors.
- Agent mode changes query compilation, not authority. Read-only comes first; explicitly
  authorized mutation and definition work follow their own gates. A valid query need not
  express the caller's intended meaning: deterministic validation does not prove NL intent.

### Contracts to settle before the interface becomes public

1. **SQL, values and results.** Specify parameter binding separately from query text; never
   interpolate generated values into SQL. Define names, types/coercions, NULL and three-valued
   logic, bag multiplicity, collation, overflow, decimal precision and timestamp/time-zone
   behavior as each type is introduced. Reject unsupported syntax/types explicitly. Promise
   ordering only with `ORDER BY`; fix streaming/cursor ownership, cancellation and row limits.
   A limit must not silently turn an exact aggregate into a sampled answer.
2. **Intent and semantic context.** Use explicit schema descriptions, relationships and
   developer-owned definitions for terms such as "available", "active" and "recent". Resolve
   units, reference time and time zone explicitly. Ambiguity is not authorization: return a
   structured clarification/error rather than invent a business rule, ask interactively
   inside a library call, or choose a risky interpretation merely because it parses.
3. **Provider and disclosure boundary.** Configure the provider/model separately from the
   per-call flag. Default context is permitted schema and declared semantic descriptions,
   not table contents or returned rows. The user's request, identifiers and bound values can
   themselves be sensitive; disclose what is sent before opt-in and allow redaction/local
   providers. Row sampling or result sharing requires separate scope. Do not promise control
   over a provider's retention. No credentials in traces or unrestricted external tools.
4. **Untrusted output and budgets.** Validate the complete generated statement/AST, not just
   its first keyword. Enforce statement count, allowed functions/operators, object access,
   row/byte/work/time limits and bounded repair attempts. Reject write-bearing CTEs, side-effect
   functions and injected instructions outside the allowed grammar/authority. The agent cannot
   widen its own context, privileges or execution budget; no generated Python/native code.
5. **Inference, transactions and freshness.** Perform inference outside transaction locks,
   publication critical sections and active writer ownership. Initial agent mode generates
   before opening an execution transaction; reject its use inside an already-active transaction
   rather than suspending locks. Read-your-writes is supplied by executing the inspected,
   generated SQL deterministically in an explicit transaction. Later snapshot-aware generation
   must define pinned-snapshot lifetimes and cancellation before being enabled. Rebind and
   recheck schema, policy and semantic-context versions at execution. Reject stale meaning
   rather than execute a previously approved query against a changed definition. Schema-only
   generation does not freeze data; results come from the execution snapshot.
6. **Reuse, privacy and failure.** Define inspection/compile-without-execution and explicit
   reuse of generated SQL with bound parameters. Distinguish a query cache from a result cache;
   cache identity includes relevant schema, policy, semantic-context, provider/model/prompt and
   parameter scope, plus snapshot/data scope when data informed generation. Revalidate reused
   queries and isolate tenants/callers. Bound cache lifetime and audit retention; redact secrets
   without discarding required execution provenance. Timeouts, cancellation or provider loss
   before execution have no database effects; uncertain commit outcomes follow storage rules,
   not blind agent retries.

## Product boundary and intended advantage

Three responsibilities share one engine without being conflated:

| Responsibility | Output and authority | Success criterion |
| --- | --- | --- |
| Deterministic database—primary product | Invented native execution/storage mechanisms, ordinary queries/writes, maintained relations, atomic commits and recovery; simple Python usage | Correctness plus a demonstrated agent-free engine and usability advantage; originality assessed separately |
| Optional query-generation agent | Supported executable SQL within the caller's existing scope | Useful intent-to-query accuracy, honest clarification and bounded cost; same engine semantics |
| Optional physical-optimization agent | Candidate representations and maintenance plans, not logical business rules | Verified semantics and control-relative benefit after all construction/maintenance/lifecycle costs |

The first complete maintained model is resource allocation:

`reservations → usage totals → available capacity → eligibility`

A transaction changes reservations, propagates affected results, checks capacity and team
limits against the complete proposed state, then commits everything or rejects everything.
SQL and natural-language reads query the same resulting relations. A later explicitly
authorized natural-language reservation request must face the same constraints as direct
SQL, not bypass them because the agent intended a reasonable allocation. Restart must
restore one coherent source/derived/definition version.

A second pricing or permissions model rejects domain-specific hardcoding. For supported
definitions, applications should not need manually maintained derived-table writes,
cache-invalidation handlers, refresh workers or reconciliation scripts. Ordinary tables and
ad hoc queries remain useful without declaring any maintained graph. An ad hoc SQL or NL
query does not implicitly create a permanent maintained relation or a storage obligation.
Developer-declared logical definitions and optimizer-private physical structures have
separate catalogs and lifecycles.

RefPot is a database engine, not a backend package. Summonpot or another caller owns
endpoints, business-agent goals, application tools and approval workflows. Database query
generation, deterministic maintenance and bounded engine experimentation are in scope;
application orchestration is not. A query agent is not a general tool-using application agent.

### Competitive thesis to prove

The primary thesis is **a better deterministic embedded engine and simpler Python database
usage**, supported by a mechanism that removes unnecessary work, state or developer-owned
protocols. Exact self-maintenance and deterministic physical design are parts of that thesis,
not its entire scope. One SQL/NL query path and optional agents extend it; their presence cannot
justify choosing the ordinary database. None of these capabilities alone establishes novelty.
SQL generation, incremental views, reactive databases,
early aggregation and learned optimizers already exist. PostgreSQL + pg_ivm is a direct
maintenance baseline; competent SQLite layers and query-generation libraries are relevant
controls, not straw men.

Compare complete models against prepared SQLite with reusable/generated maintenance,
pg_ivm and a relevant incremental platform. Consider Convex, SpacetimeDB, Feldera, Pathway
and Differential Datalog according to their actual contracts. Evaluate query-generation
quality separately from engine cost; compare physical agents with non-agent search over
the same candidate language. Measure eliminated synchronization/tuning/repair responsibilities,
not just fewer API names. Neither competitive superiority, switching demand nor algorithmic
novelty is established by this roadmap.

## Non-negotiable gates

- Keep ordinary database operations independently useful without inference, credentials,
  network, an external server, an ORM or a declared maintained model.
- Preserve query meaning, types, multiplicities, ordering guarantees, errors, isolation and
  durability across optimization; reject unsupported transformations rather than approximate.
- Finish exact derived state and write-time invariants before acknowledging a commit.
  Dense changes can require substantial work; promise neither constant-time maintenance nor
  eventually consistent results disguised as exact ones.
- Prepare allocations before publication. Recovery must not call inference or arbitrary
  application Python. Query generation may add latency only when explicitly requested;
  optimization inference is off the foreground query/commit path.
- Make agent authority, provider disclosure and budgets explicit. Agent output, schema
  descriptions and retrieved data are untrusted inputs, not privileged instructions.
- Measure full reads, writes, maintenance, construction, migration, retention and recovery.
  Report regressions and ordinary fallback behavior beside gains; tests are not equivalence proofs.
- Qualify installed artifacts and actual standard/free-threaded CPython builds. Native
  threaded tests alone establish neither binding safety nor useful multicore execution.
- Keep new capabilities additive or explicitly migrated. A volatile model-slice test is not
  evidence for durable package semantics; an agent fixture is not a live provider test.

## Delivery sequence and dependencies

M0 establishes the deterministic architecture/usability hypotheses and freezes observable
contracts. M1 compares native designs and delivers the first SQL/ordinary-operation slice;
it is not merely a parser in front of an assumed engine. Core invention continues through
M3 maintenance, M4 durability and M5 concurrency, with agent-free evidence at every boundary.
M2 adds optional NL reads after M1 and is not a dependency of M3–M5. M6 extends explicit agent
authority beyond reads. M7 extends physical-design research and optionally adds agent synthesis;
it is not the starting point for original engine work. M8 qualifies live plan installation.
M9 integrates broad SQL, lifecycle and complete deterministic usability qualification, then
qualifies each advertised optional mode separately. Milestone numbers do not serialize these
independent tracks; an NL corpus/provider adapter must not hold up the deterministic core.

This is not a waterfall withholding all releases until M9. Every implemented slice needs
runnable installed examples and truthful scope. A durable SQL/maintained-model preview can
ship after its M1/M3/M4 and existing alpha gates; advertising NL additionally requires M2.
Concurrent access requires M5, generated writes M6, and adaptive installation M8. A release
may omit unqualified capabilities, never imply them. Release/merge authority remains separate.

## M0. Establish core design hypotheses and freeze observable contracts

- [ ] Write falsifiable architectural hypotheses for the deterministic design axes above,
      including a candidate cost model, nearest known designs and an agent-free adoption case.
      Identify ordinary workloads and developer responsibilities each proposal must improve;
      do not choose the storage/transaction architecture solely by extending the current prototype.
- [ ] Specify minimal Python workflows and explicit ownership/error semantics before binding
      them to internal structures. Compare concept count, conversions, hidden work and recovery
      burden with competent incumbent usage. Usability is not deferred to an ORM or M9 polish.
- [ ] Specify the shared query/configuration/result/error interface, typed parameters,
      supported SQL grammar and capability discovery. Keep the installed `Database` / `Row`
      boundary and future relational catalog migration explicit.
- [ ] Resolve each contract above, including inspection without execution, semantic ambiguity,
      schema/policy changes, transaction ownership, provider disclosure and cache identity.
- [ ] Define two complete maintained models, plus useful ordinary table/query workflows that
      need no maintained graph. Specify keys, types, duplicates, NULL, arithmetic, constraints,
      isolation, failure and recovery expectations without hardcoding one application.
- [ ] Build independent full-recomputation/state oracles and competent executable controls.
      Freeze narrow/broad changes, shared/disjoint computations, read/write mixes and budgets.
- [ ] Freeze an NL evaluation corpus with intended query semantics, acceptable equivalent SQL,
      ambiguous/refused requests, paraphrases, units, schema drift and adversarial context.
      Record application-owned propagation, tuning and repair work separately from query quality.

**Exit:** falsifiable core design proposals and usability workflows, executable expected-state
traces for two models and ordinary querying, and concrete query/authority contracts. The
deterministic contract and controls unblock M1 independently of the optional NL corpus.
Mutants omitting propagation, absence dependencies or atomic publication must fail. Separate
engine correctness, engine/usability advantage, originality and NL quality; the earlier bounded
native slice alone completes none of these broader gates.

## M1. Prove the first deterministic design slice and deliver native SQL

- [ ] Implement and compare competing native designs for the highest-value M0 hypothesis,
      using the same ordinary operations, semantics and complete cost accounting. Retain the
      existing baseline and negative results; make the selected representation and unresolved
      limitations explicit. Do not claim invention from a faster isolated operator.
- [ ] Carry the selected slice into ordinary Python usage and test usability alongside native
      behavior: typed parameters/results, bulk operations, predictable lifetimes and actionable
      errors. Keep logical semantics stable while revising physical internals from evidence.
- [ ] Add a typed multi-table catalog, keys/indexes and schema binding over a common native
      logical IR. SQL parsing may use a dependency; execution/storage must remain RefPot-owned.
- [ ] Deliver a declared first SQL subset: parameterized `SELECT`, projection/filter, equijoins,
      grouped count/sum, ordering and limits, with explicit NULL/type/overflow semantics.
      Reject unsupported features rather than silently delegate or reinterpret them.
- [ ] Add deterministic table definition and parameterized insert/update/delete through the
      same catalog/transaction boundary. Stage SQL expansion explicitly; do not claim full
      SQLite syntax, file-format or C-API compatibility.
- [ ] Define autocommit versus explicit transactions, read-your-writes, statement failures,
      cursor/snapshot lifetimes, cancellation and bounded execution. Expose supported syntax,
      query plans and work counters without requiring agent configuration.
- [ ] Differential-test queries and mutations against independent semantics and matched SQL
      controls; fuzz parser/binder boundaries and reject side-effect/unknown operators.
- [ ] Integrate a bounded Python preview and runnable `examples/` from installed wheels,
      clearly labeled volatile until M4 qualifies relational persistence. Preserve old API tests.

**Exit:** callers create tables, change rows and run useful handwritten SQL on the native
engine, without an agent or maintained model. Typed parameters, results, errors, rollback and
inspection work through the public preview—not only a research-driver protocol. Retain a
measured architectural decision and a comparative usability result, including failures. A
conventional baseline may support an honest preview; it does not close the deterministic
invention or adoption-advantage objectives. No agent feature is required to demonstrate the slice.

## M2. Generate and execute natural-language queries through that same interface

- [ ] Add explicit `agent=True` dispatch and optional provider configuration. Generate
      supported SQL plus typed bindings, then use exactly M1's validation/execution path.
      Enforce a read-only AST/function/object scope initially; no separate NL execution engine.
- [ ] Implement permitted semantic context, inspectable query/assumptions/provenance, structured
      clarification and bounded repair. No synthetic result rows, automatic language guessing,
      hidden interactive prompts or inferred permission to write.
- [ ] Enforce provider/privacy policy, budgets, cancellation and revalidation of schema, policy
      and semantic-context identity. Keep generation before execution transactions; reject
      unsupported transaction contexts. Implement explicit generated-query inspection/reuse.
- [ ] Test parity between handwritten and generated SQL for results, errors and transaction
      behavior. Test NL semantics independently: paraphrases, ambiguity, schema changes, denied
      objects, malicious context, timeout, malformed output and provider loss.
- [ ] Run both provider-free fixtures and an explicitly configured real-provider E2E corpus.
      Record actual model/prompt identity, latency, retries, failure/clarification rates and
      measured usage/cost when available; unknown billing is unknown, not zero.
- [ ] Run installed SQL/NL examples with common result handling; prove ordinary SQL still
      works with no provider/dependencies configured and while the provider is unavailable.

**Exit:** natural language produces a real supported query and real native results under
read-only authority. Report semantic success and false-acceptance failures separately from
syntactic validity. A successful optimization experiment is not required. This is
**read-only first, not read-only forever**; M6 defines the later mutation/definition gates.

## M3. Make declared derived relations and constraints self-maintaining

- [ ] Compare deterministic change/propagation representations against both full recomputation
      and competent incremental maintenance. Account for duplicated work removed and shifted
      cost on sparse and dense changes; qualifying self-maintenance is not contingent on an agent.
- [ ] Extend the common IR with maintained filter/project, equijoins, anti-joins, grouped
      count/sum and chained relations. Start with an acyclic graph and explicit definitions;
      keep persistent declaration distinct from ad hoc SQL or NL query execution.
- [ ] Maintain inserts, updates and deletes on either side of joins; preserve multiplicities,
      NULL behavior, empty groups, absence dependencies and checked arithmetic.
- [ ] Propagate transaction deltas privately, share supported intermediate work and evaluate
      invariants against the complete final candidate rather than statement-order artifacts.
      Specify immediate versus final-state constraints; do not weaken existing API semantics.
- [ ] Publish source, derived and dependency/index changes atomically or discard them all.
      Maintain read-your-writes and operation-level exception safety, including caught errors.
- [ ] Run both complete reference models against an independent original-definition oracle;
      mutations of maintenance and atomic-publication logic must fail. Expose maintenance
      visits/copies/memory so recomputation is not hidden behind an incremental API label.
- [ ] Demonstrate SQL and, when M2 is available, NL reads of the same maintained results.
      Run installed examples for multi-row commit, delete/update propagation and rejection.

**Exit:** both models run without application-written propagation routines; failed
transactions leave no partial graph changes and readers see no mixed state. This establishes
the functional maintained engine, not durability, concurrency or algorithmic novelty.

## M4. Qualify whole-model durability and schema/definition evolution

- [ ] Evaluate M0's state/transition-evidence designs against the retained durable baseline
      under equal acknowledgment semantics. Measure logging, checkpoints, space and recovery
      together; neither a volatile speedup nor weakened sync guarantees selects the architecture.
- [ ] Version source rows, logical schemas/definitions, accepted derived outputs and required
      dependency/index metadata at one commit frontier. Choose what persists versus rebuilds
      behind a recovery barrier; reopen must need neither inference nor Python callbacks.
- [ ] Preserve bounded logging/checkpointing, pre-acknowledgment capacity checks,
      allocation-before-publication and poisoned-writer behavior after uncertain I/O.
- [ ] Inject short writes, interrupted syscalls, EIO, ENOSPC and allocation failures during
      prepare, append, sync, publication, checkpoint, recovery and reclamation. Test process
      termination, corrupt framing/lengths/metadata, stale files and repeated reopen/write/reopen.
- [ ] Implement offline atomic schema/definition migration first. Invalidate affected plans,
      generated-query reuse and semantic-context bindings; never serve stale derived state as
      current or silently reinterpret a previously bound query after a definition change.
- [ ] Define backup/restore, integrity checking and old-format transitions. Retain explicit
      filesystem assumptions; process-kill tests do not establish physical power-loss safety.
- [ ] Run installed model/SQL recovery examples and the supported platform failure matrix,
      alongside existing alpha qualification. Recovery and normal deterministic use must
      continue without provider credentials, model access or an agent cache.

**Exit:** acknowledged transitions survive restart as one coherent model. An uncertain
transition is wholly absent or present, never partial. Interrupted migration exposes one
complete definition version; bounded recovery preserves continued writes and a second restart.

## M5. Qualify concurrency, free-threading and tracked Python computations

- [ ] Compare candidate ownership/validation/publication designs on ordinary concurrent
      workloads with agents disabled, measuring useful overlap, contention, tail latency and
      retained state. Let those results inform the core architecture, not only lock tuning.
- [ ] Implement independently owned transaction contexts, private graph evaluation, exact
      conflict validation and short publication critical sections. State isolation guarantees
      explicitly; validate phantoms, missing/failed observations, write skew and own-write order
      against serializable-history oracles before claiming serializable maintained models.
- [ ] Requalify observation/MVCC experiments and bound snapshots, row versions, dependency
      edges and retired structures. Demonstrate real overlap of independent native work;
      report hot-key/hot-aggregate serialization and dense fan-out honestly.
- [ ] Release the GIL for native work; qualify binding ownership/lifetimes on standard and
      actual free-threaded CPython. Run native sanitizer/race/fuzz campaigns and installed
      multithreaded workloads, not only threaded C++ harnesses.
- [ ] Separately add optional keyed deterministic Python cells over immutable tracked inputs,
      versioned definitions and whole-cell reruns. Registered code is trusted—not sandboxed,
      automatically pure or an invitation to execute agent-generated Python.
- [ ] Test branch-dependent dependency replacement, caught lookup failures, unchanged-output
      propagation stops and callback exceptions. Callbacks run outside publication locks;
      never replay arbitrary caller callbacks on automatic retries or recovery.
- [ ] Define Python-cell persistence/rebuild behavior under M4 without callback replay. Test
      how conflict retries, callback failure and definition changes preserve atomic effects.

**Exit:** concurrent native queries and maintained writes preserve declared isolation and
invariants with bounded retained state. Optional Python cells require their own qualification;
they do not block useful native concurrency or weaken provider-free recovery.

## M6. Extend explicit agent authority to writes and persistent definitions

- [ ] After M1/M2/M3/M4, support deliberately authorized generated DML through the same query
      parameter and native transaction path. Require M5 for claims about concurrent generated
      writes. `agent=True` alone never authorizes mutation, DDL or definition installation.
- [ ] Define narrowly scoped capabilities for operations, tables/columns and applicable row
      policies, with transaction-time affected-row/work limits. Recheck authority and constraints
      during execution; a preflight count or dry run is not protection against changed data.
- [ ] Expose generated SQL and bindings for caller inspection/approval where requested.
      Bind approvals to query, parameters, schema/policy/semantic versions and expiration;
      rejection or changed meaning requires a new decision, not silent agent substitution.
- [ ] Define no-effect, aborted and uncertain-outcome errors; never automatically reissue a
      possibly committed write. Specify bounded idempotency identity/retention where supported,
      atomically coupling effects and outcome receipts rather than promising exactly-once magic.
- [ ] In a separately gated subphase, generate schema or maintained-definition proposals.
      Apply them only through explicit definition authority and M4 migration/recovery rules;
      an ordinary query must not install them. Business-rule meaning remains caller-owned.
- [ ] Exercise overbroad mutations, ambiguity, authorization drift, concurrent change, provider
      failure, cancellation, constraint rejection, crash/reopen and expired retry identities
      through installed examples and actual-provider tests as well as deterministic fixtures.

**Exit:** authorized NL writes obey the same transaction, invariant and durability guarantees
as handwritten SQL; rejected requests have no partial effects. Generated definitions remain
proposals until explicitly accepted. Application approvals stay with the caller, not a new
RefPot business-workflow framework.

## M7. Extend deterministic physical design and verified agent synthesis

- [ ] Extend the architectural work begun in M0–M5 rather than introduce invention only here.
      First qualify representations and maintenance strategies with deterministic construction
      and selection; assess what an optional proposer adds in a separate comparison.
- [ ] Start from necessary state, acknowledgment and recovery invariants. Investigate shared
      representations across queries, factorized maintenance, reuse across candidate states,
      and ways to eliminate redundant propagation/logging/storage—not only index selection or
      selecting among prewritten plans. State what work disappears and which cost replaces it.
- [ ] For each mechanism, identify nearest prior art, state its semantic/domain assumptions
      and define a falsifying complete-model experiment before claiming invention. Preserve
      useful conventional mechanisms without presenting integration alone as originality.
- [ ] Expose sanitized operator structure and measured costs through an isolated, budgeted
      engine experimentation interface. A real optional agent can inspect, compose approved
      operators, evaluate and revise; it cannot execute arbitrary code or change logical rules.
- [ ] Require candidate artifacts containing representation, read/maintenance plans, derivations,
      side conditions and resource estimates. Check initial equivalence and supported update
      transitions through a small deterministic checker/trusted incrementalization rules.
      Fail closed on unsupported proofs, unsafe arithmetic and opaque Python boundaries.
- [ ] Compare ordinary optimization, competent hand-factored plans, deterministic search over
      the **same candidate language** and agent search under matched budgets. Charge inference,
      all trials, construction, writes, retained memory, catch-up, retirement and recovery.
- [ ] Test held-out workloads, scaling and phase transitions, including "no change" wins.
      Preserve frozen source/candidate identities, exact counts, regressions, independent
      original-definition oracles and reproducible evidence. Tests supplement—not replace—the
      restricted equivalence argument. Never present instruction restrictions as a sandbox.

**Exit:** an executable mechanism removes meaningful complete-workload cost or physical-design
work against strong controls without weaker semantics. Agent-specific promotion additionally
requires control-relative benefit; rediscovering the hand design or losing to equal-budget
search is not that benefit. Retain useful deterministic progress and continue ambitious
research when an agent hypothesis fails. No fixed multiplier and no veto on M1–M6 delivery.

## M8. Install, adapt and retire verified physical representations safely

- [ ] Depend on M3/M4/M5 and an admissible checked candidate language from M7, not on agent
      superiority. Deterministic proposals may use the same lifecycle; an unqualified proposer
      stays experimental. Logical definitions and physical installation authority remain distinct.
- [ ] Build privately from a pinned snapshot, track intervening committed changes and validate
      exact catch-up against compatible logical/schema identity. Keep the authoritative plan
      usable; switch the durable physical catalog only at a consistent safe point.
- [ ] Retain old plans/state for active readers and reclaim after lifetime constraints permit.
      Account for overlapping memory/storage and bound catch-up under sustained writes; decline
      activation rather than violate latency, capacity or recovery limits.
- [ ] Persist accepted artifacts and required metadata so restart needs no agent. Enforce
      deterministic activation budgets and regression policy; keep a usable ordinary fallback.
      Include rebuild/catch-up cost if a retired representation must be recreated.
- [ ] Test crash, provider loss, allocation failure, concurrent writes and model changes during
      build, catch-up, switch, fallback and reclamation; measure sustained adaptation costs.

**Exit:** installation, fallback and restart preserve identical logical results, errors and
transaction guarantees. The agent cannot approve or publish its own proposal. Reversion is
not claimed instantaneous or free when old state was not maintained.

## M9. Broaden the database and qualify the complete Python experience

- [ ] Run the full deterministic acceptance and comparative usability campaign with agents disabled.
      Require an explicit agent-free adoption case before claiming RefPot's overall advantage;
      report ordinary query/write/transaction/recovery results separately from NL convenience or
      agent search. Carry unresolved architectural objectives forward rather than mark them done
      because the feature matrix is complete.
- [ ] Grow SQL deliberately: richer joins/subqueries, CTEs, expressions, grouping/aggregates
      and window operations, with a published support matrix and independent semantic tests.
      Distinguish executable queries from the narrower incrementally maintainable subset;
      unsupported persistent definitions fail explicitly rather than silently weakening guarantees.
- [ ] Add coherent snapshot-plus-committed-change batches with slow-consumer/backpressure and
      retention policies. No failed-transaction notifications, implied durable resume or external
      exactly-once effects. Qualify any durable resume feature separately.
- [ ] Ship runnable `examples/` for ordinary SQL, common SQL/NL results, two maintained models,
      rollback, recovery, migrations, concurrency, optional cells and each advertised agent mode.
      Run them twice through installed wheels outside the checkout on the declared matrix.
- [ ] Publish full-workload latency/throughput, memory/storage, synchronization, checkpoints,
      maintenance, recovery, inference and optimization costs. Preserve paired repeats, raw
      results, strongest eligible controls and reproduction commands; separate intent accuracy
      from native-engine performance and original-mechanism claims.
- [ ] Qualify predictable resource ceilings, diagnostics, cancellation and integrity/backup
      workflows. Keep installation and ordinary use simple; optional agents and an eventual ORM
      must not impose a model, service, framework or hidden application protocol on SQL callers.
- [ ] Align human docs, agent-readable exports, supported-feature discovery and artifacts with
      delivered behavior. Obtain separate release/publication/deployment authorization and
      independently verify the public artifacts; a roadmap checkbox does not ship an API.

**Exit:** a developer installs RefPot and uses each advertised mode through one coherent native
engine, with bounded resource behavior and explicit authority/failure semantics. Ordinary
use is designed to be compelling without a model, not merely to survive model outages.
Demonstrated differentiation must name the task, competitor, mechanism and measured engine
and usability benefit—not merely the combined feature list or the existence of agent mode.

## Further architecture frontier—not abandoned ambition

- [ ] Investigate larger-than-memory execution, spilling and bounded-state maintenance with
      explicit I/O/capacity/recovery contracts and complete-workload controls.
- [ ] Extend maintained computation toward supported recursion/fixpoints, richer aggregates
      and online logical-schema/model evolution, with termination and migration guarantees.
- [ ] Investigate deeper co-design of authoritative state, physical representations and durable
      transition evidence to remove duplicated work. Keep exploratory mechanisms isolated until
      full failure/compatibility gates justify replacing the shipped baseline.
- [ ] Add a simple optional ORM over the same validated operations. Preserve explicit SQL,
      transactions and independent engine usage; benchmark complete ORM workloads separately.

No backend framework, mandatory external service, cloud replication, distributed consensus
or application-agent runtime is implied. The ambition is a substantial embedded database and
an original engine contribution, with useful SQL/NL querying delivered along the way—not an
endless experiment gate, a query wrapper, or a compatibility checklist mistaken for invention.

[Download the canonical roadmap as Markdown](/docs/project-roadmap.md).
