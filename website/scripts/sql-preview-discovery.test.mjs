import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const root = new URL('../', import.meta.url);
const source = async path => readFile(new URL(path, root), 'utf8');

test('unreleased SQL preview has a canonical generated page and Markdown export', async () => {
  const generator = await source('scripts/sync-public-docs.mjs');
  assert.match(generator, /slug: 'reference\/sql-preview'[\s\S]*?source: '\.\.\/\.\.\/docs\/sql-preview\.md'/);
  assert.match(generator, /title: 'Unreleased SQL preview'/);
});

test('SQL preview source links resolve to its public route', async () => {
  const links = await source('scripts/publish-source-links.mjs');
  assert.match(links, /\['docs\/sql-preview\.md','\/reference\/sql-preview\/'\]/);
});

test('SQL preview is discoverable without claiming a published package feature', async () => {
  const [sidebar, header, llms] = await Promise.all([
    source('astro.config.mjs'), source('src/components/FamilyHeader.astro'), source('public/llms.txt'),
  ]);
  assert.match(sidebar, /slug: 'reference\/sql-preview'/);
  assert.match(header, /href="\/reference\/sql-preview\/"[^>]*>Unreleased SQL preview<\/a>/);
  assert.match(llms, /\/reference\/sql-preview\//);
  assert.match(llms, /unreleased|not included in the currently published package/i);
  assert.doesNotMatch(llms, /SQL and ORM are shipped/i);
});

test('rendered-output verification inventories the page and Markdown export', async () => {
  const verifier = await source('scripts/verify-rendered-output.mjs');
  assert.match(verifier, /reference\/sql-preview\/index\.html/);
  assert.match(verifier, /reference\/sql-preview/);
  assert.match(verifier, /route\.replaceAll\('\/', '-'\) \+ '\.md'/);
});
