# Changelog

All notable changes to RefPot will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Unreleased changes live as files in [`changelog.d/`](changelog.d/) until release
preparation assembles them here. Run `make changelog-draft` to preview the next release.

<!-- towncrier release notes start -->

## [0.1.2] - 2026-10-13

### Added

- Publish source-pinned package screening evidence, frozen plans, all 300 trial records and 12 recovery records, with a portable offline verifier and corruption regressions. Keep the failed SQLite target cells visible; these are locally built source-revision measurements, not release-artifact qualification.
- Adds a bounded per-cell pilot that freezes shared operation counts and minimum durations for paired runs, warms write paths outside timing, and validates persisted raw records against the plan. Recovery evidence distinguishes RefPot pending-WAL replay from SQLite ordinary close/reopen; plan hashes detect accidental edits. This remains a screening harness, not crash-recovery or general performance qualification.

### Changed

- Align the release workflow and publication guidance with the ModePot family pattern: normal GitHub releases are explicitly marked latest, and public installation/docs no longer describe version 0.1.1 as a prerelease candidate.
- Expose the retained benchmark chart, full results and reproduction evidence on the website; add canonical contributor and coding-agent guides and regression coverage for README-to-site illustration parity.
- Present public installation and standalone Python programs in the README and homepage, with task-led CRUD, transaction, persistence, error/ownership, API reference, and recovery documentation generated from canonical sources.
- Replace full transaction-state copies and commit-time state scans with staged row effects and encoded-size accounting. Prepare the final effects before WAL I/O; after duplicated redo synchronization, publish prepared changes without allocation. Recovery applies validated row-local frame effects without copying unrelated rows.


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
