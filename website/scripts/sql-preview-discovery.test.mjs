import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const root = new URL('../', import.meta.url);
const source = async path => readFile(new URL(path, root), 'utf8');

test('query-reuse review becomes unchecked roadmap experiments with source links', async () => {
  const canonical = await source('../ROADMAP.md');
  const section = text => text.split('### Next experiments from the maintained-query reuse review')[1]
    ?.split('### Core architectural questions and evidence')[0];
  const expected = section(canonical);
  assert.ok(expected);
  assert.doesNotMatch(expected, /\[x\]/i);
  assert.equal((expected.match(/\*\*Exit:\*\*/g) || []).length, 3);
  for (const marker of ['discussion_r4580395244', 'discussion_r4580395252',
    'held-out', 'retained metadata', 'final-candidate validation', 'prior-art review']) {
    assert.ok(expected.includes(marker), marker);
  }
  const hosted = await source('src/content/docs/project/roadmap.md');
  assert.equal(section(hosted), expected);
});

test('experimental SQL preview has a canonical generated page and Markdown export', async () => {
  const generator = await source('scripts/sync-public-docs.mjs');
  assert.match(generator, /slug: 'reference\/sql-preview'[\s\S]*?source: '\.\.\/\.\.\/docs\/sql-preview\.md'/);
  assert.match(generator, /title: 'Experimental SQL preview'/);
});

test('SQL preview source links resolve to its public route', async () => {
  const links = await source('scripts/publish-source-links.mjs');
  assert.match(links, /\['docs\/sql-preview\.md','\/reference\/sql-preview\/'\]/);
});

test('the homepage and onboarding state what the published SQL preview can do', async () => {
  const [home, quick, status, design, method] = await Promise.all([
    'index.mdx', 'package.md', 'status.md', 'design-direction.md', 'performance-method.md',
  ].map(path => source(`src/content/docs/${path}`)));
  assert.match(home, /## Try a reservation rule[\s\S]*?from refpot\.sql import Database, SQLError[\s\S]*?CREATE ASSERTION[\s\S]*?## A first database/);
  assert.match(quick, /## Choose an API[\s\S]*?refpot\.sql\.Database[\s\S]*?refpot\.Database/);
  for (const text of [home, status, design]) assert.match(text, /\b0\.1\.2\b/);
  for (const text of [home, quick, status, design, method, await source('public/llms.txt')]) {
    assert.doesNotMatch(text, /\bNo SQL\b|SQL and (?:the )?ORM are (?:later )?planned|SQL and ORM are design direction|remains an acceptance (?:target|gate)|is an acceptance target/i);
  }
});

test('SQL preview is discoverable with a minimum supported version', async () => {
  const [sidebar, header, llms] = await Promise.all([
    source('astro.config.mjs'), source('src/components/FamilyHeader.astro'), source('public/llms.txt'),
  ]);
  assert.match(sidebar, /slug: 'reference\/sql-preview'/);
  assert.match(header, /href="\/reference\/sql-preview\/"[^>]*>Experimental SQL preview<\/a>/);
  assert.match(llms, /\/reference\/sql-preview\//);
  assert.match(llms, /included in version 0\.1\.2/);
  assert.match(llms, /requires RefPot 0\.1\.2 or later/);
  assert.doesNotMatch(llms, /SQL and ORM are shipped/i);
});

test('persistent SQL preview exports retain the bounded unpublished contract', async () => {
  for (const path of ['src/content/docs/reference/sql-preview.md', 'public/docs/reference-sql-preview.md']) {
    const text = await source(path);
    for (const phrase of ['Database(path=None, *, mode="overlay", agent=None)', '64 MiB', '128 MiB',
      'all changed bags', 'before the handle is exposed', 'does not checkpoint',
      'included in version 0.1.2', 'requires RefPot 0.1.2 or later', 'examples/sql_persistence.py']) {
      assert.ok(text.includes(phrase), `${path}: missing ${phrase}`);
    }
    assert.doesNotMatch(text, /has no persistence|no durable storage/);
  }
});

test('read-only agent exports preserve shared API, disclosure and qualification limits', async () => {
  for (const path of ['src/content/docs/reference/sql-preview.md', 'public/docs/reference-sql-preview.md']) {
    const text = await source(path);
    for (const phrase of ['execute(query, parameters=(), *, explain=False, agent=False)',
      'disclose_schema=True', 'trusted caller Python', 'refusal preserves that transaction',
      'not a total wall-clock deadline', 'not an independent billing guarantee',
      'not establish M2 completion', 'examples/sql_agent.py', 'ClarificationRequired.questions']) {
      assert.ok(text.includes(phrase), `${path}: missing ${phrase}`);
    }
    assert.doesNotMatch(text, /my_trusted_generator|db\.ask\(/);
  }
});

test('definition evolution exports retain atomicity and scope', async () => {
  for (const path of ['src/content/docs/reference/sql-preview.md', 'public/docs/reference-sql-preview.md']) {
    const text = await source(path);
    for (const phrase of ['ALTER MATERIALIZED VIEW', 'same output column names and order',
      'transitive', 'old or new', 'older preview binaries', 'examples/sql_evolution.py']) {
      assert.ok(text.includes(phrase), `${path}: missing ${phrase}`);
    }
  }
});

test('rendered-output verification inventories the page and Markdown export', async () => {
  const verifier = await source('scripts/verify-rendered-output.mjs');
  assert.match(verifier, /reference\/sql-preview\/index\.html/);
  assert.match(verifier, /reference\/sql-preview/);
  assert.match(verifier, /route\.replaceAll\('\/', '-'\) \+ '\.md'/);
});
