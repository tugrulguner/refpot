# RefPot website

This directory publishes research and design documentation, not a database runtime.
It follows the ModePot family shell while deliberately omitting package installation,
API examples, a playground, and performance claims that RefPot has not shipped.

## Local verification

Use Node 22.19 or newer within the Node 22 release line (the CI runtime), then:

```sh
cd website
npm ci
npx playwright install chromium
npm run check
npm run build
```

`check` runs Astro diagnostics. `build` synchronizes the canonical roadmap and public
Markdown downloads, builds six static layouts, validates their analytics/discovery
contracts and local destinations, and runs the browser acceptance suite on an isolated
preview server. The tests cover 1280, 768, 390 and 320px with Light/Dark/Auto, live OS
changes, family navigation, keyboard menu access, and the 404 shell.

The repository presentation gate is `python3 -m unittest discover -s tests -v` from
its root. There is no RefPot package to install or engine executable to start.

The canonical `ROADMAP.md` generates `/project/roadmap/` and its Markdown download.
The public README download is the exact repository README. Other downloads are
frontmatter-stripped copies of their canonical site documents.

## Artwork

The lockup and architecture artwork are unchanged copies of `../docs/assets/`.
The compact mark preserves the same flask and database glyph. Social artwork has
an editable `public/social-card.svg` source and a 1200×630 PNG. After editing it, run
`npm run render:assets` with Playwright Chromium installed and inspect the result.

## Deployment

`wrangler.toml` maps `refpot-site` to `refpot.modepot.io`, using Workers Static Assets.
Do not deploy production from an uncommitted tree. First verify a separate preview
from the committed, reviewed build; production rollout and the umbrella links are
separate gates. The canonical hostname is launch-pending until HTTPS and all advertised
routes are read back successfully.

The GitHub workflow checks every pull request and `main`; it does not depend on
Cloudflare secrets and does not deploy pull requests over production. For automatic
production deployment, connect this repository through Cloudflare Workers Builds:

- Production branch: `main`
- Root directory: `website`
- Build command: `npm ci && npx playwright install --with-deps chromium && npm run check && npm run build`
- Deploy command: `npx wrangler deploy`

Cloudflare's repository integration supplies deployment authentication. It is not
configured merely by committing this file. Without that integration, an authenticated
maintainer can deploy the same verified configuration using Wrangler; report the exact
source commit and verify DNS/TLS, HTTP content, discovery and navigation afterward.
