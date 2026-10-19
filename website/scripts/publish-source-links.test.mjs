import test from 'node:test';
import assert from 'node:assert/strict';
import { publishSourceLinks } from './publish-source-links.mjs';
const revision='a'.repeat(40);
test('resolves source-relative page, asset and evidence URLs without losing fragments',()=>{
 assert.equal(publishSourceLinks('[Results](../benchmarks/package-performance/RESULTS.md#scope)','docs/package-contract.md',revision),'[Results](/project/package-performance/#scope)');
 assert.equal(publishSourceLinks('![Chart](../../docs/assets/chart.png?download=1)','benchmarks/example/README.md',revision),`![Chart](https://raw.githubusercontent.com/tugrulguner/refpot/${revision}/docs/assets/chart.png?download=1)`);
 assert.equal(publishSourceLinks('[Source](script.py#L2)','benchmarks/example/README.md',revision),`[Source](https://github.com/tugrulguner/refpot/blob/${revision}/benchmarks/example/script.py#L2)`);
});
test('preserves absolute and local-page links',()=>{
 const text='[A](https://example.org/a) [B](#heading) [C](/package/) [D](mailto:hello@example.org)';
 assert.equal(publishSourceLinks(text,'README.md',revision),text);
});
test('rejects unpinned revisions and links outside the repository',()=>{
 assert.throws(()=>publishSourceLinks('[A](a)','README.md','main'));
 assert.throws(()=>publishSourceLinks('[A](../../outside)','README.md',revision));
});
