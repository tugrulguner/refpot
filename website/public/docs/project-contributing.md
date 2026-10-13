This package adds a source-built POSIX native engine and Python binding. It is experimental; do not infer full physical-power-loss guarantees or performance wins from the package CI alone. Contributions should include tests and a changelog fragment for user-visible changes.

## Development setup

Install uv, a C++17 compiler, CMake, and Python 3.11–3.14. This package builds on Linux and macOS; Windows is not supported.

```sh
uv sync --all-groups --locked
make check
make build
```

Use `make format` to apply Ruff formatting. CI independently builds the native wheels and tests installed artifacts. Please run `uv run --locked pytest tests/ -q` before opening a pull request.

## Changelog fragments

Add one fragment in `changelog.d/` for user-facing changes, using `<issue-number>.<type>.md` for an existing issue, or `+<unique-slug>.<type>.md` when there is no issue. Types are `added`, `changed`, `deprecated`, `removed`, and `fixed`. Orphan slugs must be unique across the branch and must not collide with any existing fragment; never use a generic shared name. Write a concise user-facing sentence. Pull requests that do not change user-visible behavior may use the maintainer-applied `skip-changelog` label.

```sh
make changelog-draft
```

## Release preparation

Set the package version with `uv version <version>`; do not edit a second version source. Review the draft, then `make changelog` to assemble and consume fragments. Commit the resulting metadata, lockfile, and changelog before tagging `v<version>`. A tag release only runs after CI, verifies ancestry/version/changelog, builds distributions, publishes using PyPI trusted publishing, and creates a GitHub Release. Repository environment and PyPI trusted-publisher configuration are external prerequisites; maintainers must verify them before creating a release tag.
