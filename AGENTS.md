# RefPot agent and contributor guidance

RefPot is an experimental alpha custom embedded native database engine. Read `README.md`, `docs/package-contract.md`, and `ROADMAP.md` before changing behavior or describing capabilities. Version 0.1.1 is the current public release; 0.1.2 preparation is not publication. Keep the alpha maturity and qualification boundaries clear.

## Contract and claims

- The implemented API is the fixed-schema Python `Database`/`Row` CRUD and explicit transaction contract. SQL and ORM are planned, not shipped.
- Preserve the documented signed-64-bit integer and bounded UTF-8 text limits, single-process/single-creating-thread ownership, file-path semantics, and current persistence/recovery boundaries.
- Do not claim general performance, production readiness, physical-power-loss qualification, multiwriter/concurrent-reader support, Windows support, or SQLite SQL/file/C API compatibility.
- Keep historical random-update results scoped to their audited harness. They are not package performance claims; the historical reopen result remains 16/16 losses.
- Treat a passing unit test or CI lane as evidence for that test only. Do not mark broad roadmap qualification complete based on narrower tests.

## Changes and verification

- Add regression tests for behavior changes and a unique `changelog.d/+<slug>.<type>.md` fragment for user-visible changes unless a tracking issue supplies the numbered fragment.
- Follow `CONTRIBUTING.md` and `docs/releasing.md` for locked development, local builds, changelog handling, and release checks.
- Run `make check`, `make build`, and `uv run --locked twine check dist/*.whl dist/*.tar.gz` for package changes. Run the website's documented checks/build and browser tests when website files change.
- Release tags and PyPI publication require explicit maintainer authorization. Workflow configuration is not proof that external policies are ready. The public 0.1.1 artifact is available from PyPI; do not republish or retag it.
- Keep generated/temporary build artifacts out of commits and inspect `git diff --check` plus the complete final diff before opening a PR.

## Repository skill

`skills/refpot-database/SKILL.md` is the repository-local installable agent skill for users and coding agents working with the current Python package contract. Keep its claims aligned with implementation, tests, and public docs; do not copy it into a user-global profile as part of repository work.
