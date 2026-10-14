# Release checklist

RefPot is an **experimental alpha**, intended for evaluation rather than production use. This change-set is not tag-ready: finish and review all release gates, then obtain explicit maintainer approval before tagging or publishing. Published prebuilt wheels target Linux x86_64 and macOS arm64 on CPython 3.11–3.14; Windows, other architectures, free-threaded Python, and physical power-loss guarantees are unsupported. See `docs/package-contract.md` for scope and caveats.

1. Confirm the intended version and update the sole editable version with `uv version X.Y.Z` (`uv version 0.1.2` for this preparation).
2. Review `make changelog-draft`, assemble with `make changelog`, and inspect staged and unstaged changes. Confirm the generated `0.1.2` notes include every user-facing fragment.
3. Run `uv sync --all-groups --locked`, `make check`, `uv build`, and `uv run --locked twine check dist/*.whl dist/*.tar.gz`. Verify metadata and artifacts, then test the built wheel in an isolated environment outside the checkout.
4. Merge the preparation change only through normal review and required checks. Confirm the exact release commit is reachable from `main` before creating `vX.Y.Z`.
5. Before tagging, verify that the GitHub `pypi` environment admits release tags and PyPI has the exact trusted-publisher tuple: project `refpot`, owner `tugrulguner`, repository `refpot`, workflow filename `release.yml`, environment `pypi`. No long-lived PyPI token is used.
6. The tag-triggered workflow must complete CI, build and validate distributions, publish via OIDC, and create a normal public GitHub release marked latest with the same artifacts. Independently verify the GitHub Release and installability from the public package index before describing the package as published.

Research-review package-performance measurements use source revisions represented by wheels labeled 0.1.1; they are not results for package artifacts built from 0.1.2 metadata. PyPI renders the README embedded in each uploaded distribution, so correcting an already-published README requires a future patch release, not an overwrite or re-upload.

No tag or publication is part of routine release preparation. The pending PyPI publisher has been configured; confirm the exact tuple before tagging rather than asking for credentials or changing settings.

## Website deployment

`.github/workflows/deploy-website.yml` builds and tests the static website before deploying `website/wrangler.toml` from `main`. Its production environment must be configured with the repository variable `CLOUDFLARE_ACCOUNT_ID` and secret `CLOUDFLARE_API_TOKEN` for a durable, least-privilege deployment identity. Never copy a local OAuth session token into Actions.

The Cloudflare deployment was previously verified. Before changing deployment ownership, check the existing Worker integration so Workers Builds and Actions do not compete for the same production hostname. After deployment, verify the exact source commit and public HTTPS content independently.
