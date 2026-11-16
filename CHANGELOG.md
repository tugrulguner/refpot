# Changelog

All notable changes to RefPot will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Unreleased changes live as files in [`changelog.d/`](changelog.d/) until release
preparation assembles them here. Run `make changelog-draft` to preview the next release.

<!-- towncrier release notes start -->

## [0.1.2] - 2026-11-16

The SQL API remains experimental and separately
scoped from the fixed-schema Database/Row API.

### Added

- Add an experimental volatile native transactional relational model slice with reservation and pricing examples, independent recomputation and SQLite-view controls, and allocation-failure/correctness tests. This research slice does not change the installed Database/Row API or storage format and provides no durability, concurrency or optimization agent.
- Add atomic `ALTER MATERIALIZED VIEW` replacement to the experimental SQL preview, preserving output shape while recomputing dependent results and validating assertions at one durable frontier. Includes migration/reopen examples and bounded failure qualification; included in version 0.1.2.
- Add optional bounded whole-model persistence to the experimental `refpot.sql` preview. A file-backed database recovers catalog definitions, assertions, and weighted source/derived relation state before serving, with synchronized canonical bag deltas and explicit bounded checkpoints. `Database()` remains volatile. This preview is included in version 0.1.2; broad durability, migration, backup, and platform qualification remain open.
- Add transaction-local maintained-relation propagation and a bounded correlated `NOT EXISTS` form for absence-aware final-state assertions in the experimental SQL preview. These volatile APIs are included in version 0.1.2; the fixed-schema API and storage are unchanged.
- Add volatile maintained SQL views and deferred empty-relation assertions to the experimental SQL preview. Views retain duplicate rows, track source changes, and support transaction-local reads; rejected final-state constraints discard the entire transaction. This is included in version 0.1.2 and does not claim durability, concurrency, broad SQL support, or an engine-performance advantage.
- Adds an unreleased, explicitly selected, bounded read-only SQL agent-query preview with explicit schema disclosure, native authority checks, and a provider-free runnable fixture example. Does not complete roadmap M2 or semantic evaluation; included in 0.1.2 artifacts.
- Document the unreleased volatile native SQL preview contract separately from the currently published fixed-schema API. The experimental API is included in version 0.1.2 artifacts; broader SQL, durability, concurrency, and roadmap M1 qualification remain outstanding.
- Publish source-pinned package screening evidence, frozen plans, all 300 trial records and 12 recovery records, with a portable offline verifier and corruption regressions. Keep the failed SQLite target cells visible; these are locally built source-revision measurements, not release-artifact qualification.
- Adds a bounded per-cell pilot that freezes shared operation counts and minimum durations for paired runs, warms write paths outside timing, and validates persisted raw records against the plan. Recovery evidence distinguishes RefPot pending-WAL replay from SQLite ordinary close/reopen; plan hashes detect accidental edits. This remains a screening harness, not crash-recovery or general performance qualification.

### Changed

- Add visible social links and public website feedback routes.
- Avoid materializing duplicate logical relation bags when encoding SQL-preview commits and checkpoints or calculating current catalog image size. Borrow shared physical bags for the duration of persistence preparation while retaining logical-name ordering, existing record bytes, and detached native compatibility callbacks. This removes intermediate bag copies, not logical record duplication on disk or all serialization allocations.
- Refocus the roadmap on a self-maintaining relational engine and optional, verified internal agent specialization; withdraw the fixed SQLite speed multiplier while preserving historical evidence and alpha qualification boundaries.
- Reuse exact bound filter/projection results from existing maintained views for eligible ordinary SQL-preview reads. Preserve output labels, bag multiplicities, sorting and limits; active transactions and restricted read-only execution retain the original path. This is bounded reuse, not general query rewriting or a universal performance guarantee.
- Revise the planned RefPot roadmap around unified data-and-change engine research and simpler agent-free Python usage, with a competent shared-kernel baseline and explicit correctness protocols. Commit to first-class natural-language querying through the same query interface; compare generated SQL and structured proposals, and qualify execute/clarify/decline decisions with held-out semantic risk/coverage tests. Preserve durable self-maintenance, authorized writes, concurrency and verified physical-design research. These are planned capabilities, not new package APIs.
- Share equivalent maintained operators and identity projections in the experimental SQL preview while preserving logical view names and the existing logical persistence format. Physical plans are reconstructed on reopen; definition changes prepare replacement state before publication. This is conventional common-expression sharing, not an original engine mechanism or a general performance claim.
- Align the release workflow and publication guidance with the ModePot family pattern: normal GitHub releases are explicitly marked latest, and public installation/docs no longer describe version 0.1.1 as a prerelease candidate.
- Expose the retained benchmark chart, full results and reproduction evidence on the website; add canonical contributor and coding-agent guides and regression coverage for README-to-site illustration parity.
- Present public installation and standalone Python programs in the README and homepage, with task-led CRUD, transaction, persistence, error/ownership, API reference, and recovery documentation generated from canonical sources.
- Replace full transaction-state copies and commit-time state scans with staged row effects and encoded-size accounting. Prepare the final effects before WAL I/O; after duplicated redo synchronization, publish prepared changes without allocation. Recovery applies validated row-local frame effects without copying unrelated rows.

### Fixed

- Anchor native SQL storage paths to their opening working directory so later directory changes cannot redirect checkpoints, truncate the original database's acknowledged WAL without its snapshot, or overwrite a same-named database elsewhere.
- Correct RefPot identity and social artwork to describe the experimental native database and Python CRUD/transaction API, remove obsolete unshipped ORM and unreleased claims, and clarify database discovery metadata.
- Correct the RefPot wordmark to keep the name white and the pot suffix orange across README, website, and social artwork.
- Defer below-the-fold homepage diagrams and reserve their intrinsic layout dimensions to avoid competing with first-fold content.
- Keep OpenRouter catalog prices and reported usage costs exact when decoding JSON so tiny nonzero values cannot underflow into an accepted zero-cost response.
- Keep a direct, clearly labeled Feedback action visible in compact navigation, while retaining ModePot in the menu and keeping feedback context limited to the canonical public page.
- Keep personal GitHub, LinkedIn and X links beside the creator attribution with restrained text sizing instead of crowding project navigation.
- Match the RefPot wordmark to its off-white flask on dark artwork, with dark ink on light headers.
- Repair generated website documentation links, preserve literal code examples during publication, restore the homepage keyboard skip target, and give practical guides topic-specific descriptions. Pin published evidence links to their canonical source revision.
- Report native aggregate overflow from agent-generated queries as `SQLError`, matching ordinary SQL execution while preserving separate Python argument-range errors.

## [0.1.1] - 2026-10-12

### Added

- Add the native C++ database engine and Python `Database`/`Row` API with caller-provided fixed-schema CRUD, explicit atomic transactions, rollback, checkpointing, and persistent reopen.
- Add signed-64-bit integer validation, a 31-byte UTF-8 text limit, bounded versioned/checksummed storage, exclusive process/thread ownership, and rejection of further operations after uncertain write failures.
- Include runnable CRUD and transaction examples, package contract documentation, and retained experimental benchmark evidence with its known reopen/validation losses. The package has no qualified performance or physical power-loss claim.
- Add a source-built POSIX native package workflow with locked CI, Python support bounds, changelog fragments, and verified native wheels.

### Changed

- Clarify the roadmap's completed package foundations and add repository-local agent and RefPot database skill guidance without overstating release readiness.

### Fixed

- Sanitize website analytics URL and acquisition payloads and disable unused flag requests, with real-SDK persisted-acquisition and capture-opt-out regression coverage.
