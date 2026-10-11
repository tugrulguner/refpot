# Release checklist

1. Confirm the exact intended version and update the sole editable version with `uv version X.Y.Z`.
2. Review `make changelog-draft`, assemble with `make changelog`, and inspect both staged and unstaged changes. Confirm no user-facing fragment was omitted.
3. Run `uv sync --all-groups --locked`, `make check`, `uv build`, and `uv run --locked twine check dist/*.whl dist/*.tar.gz`. Verify package metadata and artifacts.
4. Merge the preparation change only through normal review and required checks. Confirm the exact release commit is reachable from `main` before creating `vX.Y.Z`.
5. Before tagging, an administrator must ensure the GitHub `pypi` environment admits release tags and PyPI has the exact pending/active trusted-publisher tuple (project `refpot`, owner `tugrulguner`, repository `refpot`, workflow `.github/workflows/release.yml`, environment `pypi`). No long-lived PyPI token is used.
6. The release workflow must complete CI, build and validate distributions, publish via OIDC, and create a GitHub Release with the same artifacts. Verify the GitHub Release and public package independently after publication.

No tag, publication, environment creation, or repository-setting change is part of routine release preparation.

## Website deployment

Like the sibling ModePot projects, `.github/workflows/deploy-website.yml` builds and tests the static website before deploying `website/wrangler.toml` from `main`. Its production environment must be configured with the repository variable `CLOUDFLARE_ACCOUNT_ID` and secret `CLOUDFLARE_API_TOKEN` for a durable, least-privilege deployment identity. Never copy a local OAuth session token into Actions.

These GitHub/PyPI environments and deployment credentials are not configured by this preview change. Workflow files establish the contract, not live publication or unattended deployment readiness. Before enabling deployment, verify the existing Cloudflare Worker integration so Workers Builds and Actions do not compete for the same production hostname. After deployment, verify the exact source commit and public HTTPS content independently.
