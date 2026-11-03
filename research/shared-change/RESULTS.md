# Shared-change foundation: executed results

## Decision

**Partial validation of a candidate mechanism, not selection of a universal engine design.**
Both native modes implement private preparation, candidate reads, final-state validation,
explicit publication and discard. The overlay avoids full affected-bag materialization;
the modular control already shares unchanged bags, operators and delta evaluation.

For sparse changes, this removes population-dependent bag copies in the tested component.
Dense changes expose the tradeoff: merged candidate reads traverse extra delta entries,
and retained entries approach the modular control. There is no timing, peak-memory,
complete-copy, database-superiority or novelty result here. Transaction overlays are prior art.

Keep both implementations for the next ordinary native-query/Python slice. Do not treat this
as the SQL/NL, durable-storage or concurrency milestone, and do not replace the package engine
on the basis of these counters.

## Qualification

The retained final normal and ASan/UBSan campaigns exercised identical current native source:

- 5 end-to-end test methods, including 8 inherited semantic tests per native mode.
- 640 seeded transaction cases across two domains and both modes: 114 accepted and 526
  rejected. Each case compares every relation and acceptance behavior against independent
  Python recomputation and SQLite. These are repeated scenarios across the two native modes,
  not 640 unique workloads; the sanitizer campaign repeats the same cases.
- Allocation refusal at 136 successive prepare allocations in modular mode and 124 in overlay
  mode; each failure preserves committed state and permits a subsequent successful mutation.
  Publication succeeds with allocation disabled in both modes.
- 40 unique native matrix records: two domains, two populations, five scenarios and two modes.
  Normal and sanitized raw records are identical. Source hashes identify the qualified baseline;
  its sources are archived under `~/.hermes/refpot-research/shared-change-foundation/final-normal/source/`.
  The subsequent native-SQL slice adds a read-only scan entry point and is qualified separately.
- A repository-discovered test rebuilds and reruns the experiment and executes publish/discard
  examples twice per mode from another working directory. This was run locally; no remote CI
  or package installation is implied.
- Independent read-only review found no blockers for the bounded native experiment. The parent
  verified the exact reviewed hashes of native.hpp, driver.cpp and test_native.cpp. The final
  run adds a downstream-work regression and expands manifest coverage after that review;
  the native implementation is unchanged.

Address and undefined-behavior sanitizers passed. Leak detection is disabled and unqualified.
These are finite tests, not a proof for all graphs, arithmetic histories or allocator behavior.

## Complete transaction counter matrix

M/O means modular/overlay. Values below are generated from retained raw records. Inspection-only
cells have no new transaction and therefore no transaction counters; their initialization
and two full-state exports are still recorded. Cancellation cells are retained, not dropped.

| Domain | Population | Change | Bag copies M/O | Retained entries M/O | Visibility entries M/O |
|---|---:|---|---:|---:|---:|
| resource | 32 | cancel | 32 / 0 | 32 / 0 | 0 / 0 |
| resource | 32 | sparse | 136 / 0 | 166 / 39 | 48 / 50 |
| resource | 32 | dense | 136 / 0 | 344 / 312 | 238 / 398 |
| resource | 32 | parent | 32 / 0 | 96 / 96 | 36 / 92 |
| resource | 256 | cancel | 256 / 0 | 256 / 0 | 0 / 0 |
| resource | 256 | sparse | 368 / 0 | 398 / 39 | 52 / 54 |
| resource | 256 | dense | 368 / 0 | 1072 / 1056 | 344 / 600 |
| resource | 256 | parent | 32 / 0 | 96 / 96 | 36 / 92 |
| pricing | 32 | cancel | 32 / 0 | 32 / 0 | 0 / 0 |
| pricing | 32 | sparse | 144 / 0 | 162 / 24 | 27 / 28 |
| pricing | 32 | dense | 144 / 0 | 416 / 408 | 182 / 310 |
| pricing | 32 | parent | 120 / 0 | 344 / 336 | 204 / 404 |
| pricing | 256 | cancel | 256 / 0 | 256 / 0 | 0 / 0 |
| pricing | 256 | sparse | 816 / 0 | 834 / 24 | 27 / 28 |
| pricing | 256 | dense | 816 / 0 | 2432 / 2424 | 208 / 336 |
| pricing | 256 | parent | 568 / 0 | 1688 / 1680 | 428 / 628 |

Logical evaluator visits and derived-node counts match between both modes in every transaction
cell. Visibility counts expose additional overlay merge traversal; they are not timings.

`copied_rows` counts full committed bag entries materialized into candidates, not every row
copy. Retained entries include materialized bags, signed deltas and staged publication nodes,
not bytes or peak memory. Delta key insertions, source-lookup copies, staged insertions,
initialization and full-state exports are recorded separately. See CONTRACT.md for exclusions.
Candidate snapshots still copy returned rows; this is not a zero-copy implementation.

## Reproduction and evidence

Use README.md for build, qualification and runnable-example commands. The evidence directories
contain raw records, derived comparisons, source/binary hashes and actual test logs:

- evidence/final-normal/
- evidence/final-sanitized/

The manifest base revision identifies the starting checkout, not a commit containing these
uncommitted research files. Per-file source hashes identify the implementation exercised.
Native binaries are not checked in; the runner rebuilds them with the recorded flags. Python
and compiler identities are retained, but portability to another compiler/OS is not established.
The controls and shared arithmetic header are repository dependencies, not a standalone package.

## Regressions found and scope limits

Parent tests rejected an earlier implementation that materialized overlay candidates before
discarding copies and allocated during modular publication. The current implementation fixes
both and retains focused regressions; earlier successful tests were insufficient evidence.

The existing application-model suite passes against its original driver and the modular
experiment. Against overlay, its only failed assertion requires copied_rows > 0, a property
of the old materializing implementation rather than a semantic requirement. The preceding
result/derived-work assertions passed. The original test is unchanged; the new research suite
checks identical downstream stopping without imposing that incompatible copy assumption.

This is an in-memory, single-owner, integer/bag relational component. Candidate reads concern
already-declared relations, not arbitrary SQL. No threads, independent persistent snapshots,
crash recovery, durable indexes, authorization frontend, natural-language model calls or
installed Database/Row changes are qualified. No package release, commit, push or PR was made.
