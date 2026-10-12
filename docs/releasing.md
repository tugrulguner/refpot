# Release checklist

RefPot 0.1.1 is the first **experimental alpha** package release. It is intended for evaluation, not production use. The currently supported package builds target Linux x86_64 and macOS arm64 on CPython 3.11–3.14; Windows, other architectures, free-threaded Python, and physical power-loss guarantees are unsupported. The engine's scope and caveats are documented in `docs/package-contract.md`.

1. Confirm the intended version and update the sole editable version with `uv version X.Y.Z` (first release: `0.1.1`).
2. Review `make changelog-draft`, assemble with `make changelog`, and inspect staged and unstaged changes. Confirm the generated `0.1.1` notes include every user-facing fragment.
3. Run `uv sync --all-groups --locked`, `make check`, `uv build`, and `uv run --locked twine check dist/*.whl dist/*.tar.gz`. Verify metadata and artifacts, then test the built wheel in an isolated environment outside the checkout.
4. Merge the preparation change only through normal review and required checks. Confirm the exact release commit is reachable from `main` before creating `vX.Y.Z`.
5. Before tagging, verify that the GitHub `pypi` environment admits release tags and PyPI has the exact trusted-publisher tuple: project `refpot`, owner `tugrulguner`, repository `refpot`, workflow filename `release.yml`, environment `pypi`. No long-lived PyPI token is used.
6. The tag-triggered workflow must complete CI, build and validate distributions, publish via OIDC, and create a GitHub **prerelease** with the same artifacts. Independently verify the GitHub Release and installability from the public package index before describing the package as published.

Until public-index installation is verified, installation is a release candidate and must use a locally built artifact; do not claim `pip install refpot==0.1.1` is available yet. After publication is verified, the user install command is `python -m pip install refpot==0.1.1`.

No tag or publication is part of routine release preparation. The pending PyPI publisher has been configured; confirm the exact tuple before tagging rather than asking for credentials or changing settings.

## Website deployment

`.github/workflows/deploy-website.yml` builds and tests the static website before deploying `website/wrangler.toml` from `main`. Its production environment must be configured with the repository variable `CLOUDFLARE_ACCOUNT_ID` and secret `CLOUDFLARE_API_TOKEN` for a durable, least-privilege deployment identity. Never copy a local OAuth session token into Actions.

The Cloudflare deployment was previously verified. Before changing deployment ownership, check the existing Worker integration so Workers Builds and Actions do not compete for the same production hostname. After deployment, verify the exact source commit and public HTTPS content independently.
