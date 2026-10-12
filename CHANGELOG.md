# Changelog

All notable changes to RefPot will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Unreleased changes live as files in [`changelog.d/`](changelog.d/) until release
preparation assembles them here. Run `make changelog-draft` to preview the next release.

<!-- towncrier release notes start -->

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
