import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const packageJson = JSON.parse(await readFile(new URL('../package.json', import.meta.url), 'utf8'));

test('docs regression files run serially because one regenerates shared exports', () => {
  assert.match(packageJson.scripts['test:docs'], /--test-concurrency=1/);
});
