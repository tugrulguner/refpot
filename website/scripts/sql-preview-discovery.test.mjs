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

test('persistent SQL preview exports retain the bounded unpublished contract', async () => {
  for (const path of ['src/content/docs/reference/sql-preview.md', 'public/docs/reference-sql-preview.md']) {
    const text = await source(path);
    for (const phrase of ['Database(path=None, *, mode="overlay")', '64 MiB', '128 MiB',
      'all changed bags', 'before the handle is exposed', 'does not checkpoint',
      'not included in the currently published 0.1.2 package', 'examples/sql_persistence.py']) {
      assert.ok(text.includes(phrase), `${path}: missing ${phrase}`);
    }
    assert.doesNotMatch(text, /has no persistence|no durable storage/);
  }
});

test('rendered-output verification inventories the page and Markdown export', async () => {
  const verifier = await source('scripts/verify-rendered-output.mjs');
  assert.match(verifier, /reference\/sql-preview\/index\.html/);
  assert.match(verifier, /reference\/sql-preview/);
  assert.match(verifier, /route\.replaceAll\('\/', '-'\) \+ '\.md'/);
});
