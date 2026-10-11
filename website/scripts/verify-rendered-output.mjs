import { readFile, readdir } from 'node:fs/promises';
import assert from 'node:assert/strict';
const root = new URL('../dist/', import.meta.url);
const routes = ['index.html', 'package/index.html', 'package-contract/index.html', 'status/index.html', 'design/index.html', 'performance-method/index.html', 'project/roadmap/index.html', '404.html'];
for (const route of routes) {
  const html = await readFile(new URL(route, root), 'utf8');
  assert.equal((html.match(/<h1\b/g) ?? []).length, 1, `${route}: one H1`);
  for (const destination of ['https://modepot.io/', 'https://github.com/tugrulguner/refpot', 'https://discord.gg/u3AANZr6RG', 'https://tugrul.modepot.io/']) assert.ok(html.includes(destination), `${route}: ${destination}`);
  assert.equal((html.match(/posthog\.init\(/g) ?? []).length, 1, `${route}: one PostHog initialization`);
  for (const setting of ["api_host:'https://us.i.posthog.com'", "person_profiles:'identified_only'", 'capture_pageview:true', 'capture_pageleave:true', 'disable_session_recording:true', "dom_event_allowlist:['click']", "element_allowlist:['a','button']"]) assert.ok(html.includes(setting), `${route}: ${setting}`);
  assert.ok(html.includes('rel="alternate" type="text/plain" href="/llms.txt"'));
  assert.ok(html.includes('https://refpot.modepot.io/social-card.png?v=offwhite-1'));
  const blocks = [...html.matchAll(/<script[^>]*type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/g)];
  assert.equal(blocks.length, 1);
  const data = JSON.parse(blocks[0][1]);
  for (const type of ['SoftwareSourceCode', 'WebSite']) assert.ok(data['@graph'].some(entry => entry['@type'] === type));
  assert.doesNotMatch(JSON.stringify(data), /"(?:installUrl)"/);
  assert.deepEqual(data['@graph'][0].programmingLanguage, 'Python');
  assert.deepEqual(data['@graph'][0].runtimePlatform, 'Python 3.11–3.14');
  assert.deepEqual(data['@graph'][0].license, 'https://spdx.org/licenses/MIT.html');
  assert.doesNotMatch(html, /pypi\.org|href="\/(?:quickstart|playground)\//i);
  // Every advertised local destination must exist in the emitted artifact.
  for (const [, href] of html.matchAll(/href="(\/[^"#?]*)[^" ]*"/g)) {
    if (href.startsWith('//') || href === '/') continue;
    const file = href.endsWith('/') ? href.slice(1) + 'index.html' : href.slice(1);
    await readFile(new URL(file, root));
  }
}
const actualHtml=[];
async function walk(dir) { for (const item of await readdir(dir,{withFileTypes:true})) { const url=new URL(item.name+(item.isDirectory()?'/':''),dir); if(item.isDirectory()) await walk(url); else if(item.name.endsWith('.html')) actualHtml.push(url); } }
await walk(root);
assert.equal(actualHtml.length, routes.length, 'Unexpected HTML layout must join verification scope');
const png = await readFile(new URL('social-card.png', root));
assert.equal(png.subarray(1,4).toString(),'PNG');
assert.equal(png.readUInt32BE(16),1200); assert.equal(png.readUInt32BE(20),630);
for (const file of ['robots.txt','llms.txt','sitemap-index.xml','sitemap-0.xml','refpot-mark.svg','refpot-lockup.png','refpot-execution.png','refpot-package.png','refpot-package.svg']) assert.ok((await readFile(new URL(file, root))).length);
for (const [source, output] of [['status.md','status.md'],['design-direction.md','design.md'],['performance-method.md','performance-method.md'],['package-contract.md','package-contract.md'],['package.md','package.md']]) {
  const canonical = (await readFile(new URL('../src/content/docs/'+source, import.meta.url),'utf8')).replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/,'');
  assert.equal(await readFile(new URL('docs/'+output,root),'utf8'),canonical);
}
assert.equal(await readFile(new URL('docs/project-roadmap.md',root),'utf8'),await readFile(new URL('../../ROADMAP.md',import.meta.url),'utf8'));
assert.equal(await readFile(new URL('docs/project-readme.md',root),'utf8'),await readFile(new URL('../../README.md',import.meta.url),'utf8'));
assert.equal(await readFile(new URL('docs/package-recommendation.md',root),'utf8'),await readFile(new URL('../../docs/package-recommendation.md',import.meta.url),'utf8'));
assert.equal(await readFile(new URL('docs/package-contract-source.md',root),'utf8'),await readFile(new URL('../../docs/package-contract.md',import.meta.url),'utf8'));
const llms=await readFile(new URL('llms.txt',root),'utf8');
assert.match(llms,/acceptance target only/); assert.match(llms,/no PyPI release/); assert.match(llms,/package-contract/);
console.log(`Verified ${routes.length} HTML layouts, one PostHog initialization each, canonical destinations, PNG dimensions, discovery and nine same-source Markdown exports.`);

for (const [source, copy] of [["../../docs/assets/refpot-lockup.svg","refpot-lockup.svg"],["../../docs/assets/refpot-execution.svg","refpot-execution.svg"],["../../docs/assets/refpot-package.svg","refpot-package.svg"]]) assert.equal((await readFile(new URL(source, import.meta.url))).toString(), (await readFile(new URL(copy, root))).toString());
assert.deepEqual(await readFile(new URL('../../docs/assets/refpot-package.png', import.meta.url)), await readFile(new URL('refpot-package.png', root)));
for (const route of routes) { const html=await readFile(new URL(route,root),"utf8"); assert.ok(html.includes("/refpot-mark.svg?v=offwhite-1")); assert.ok(html.includes("social-card.png?v=offwhite-1")); if(route==="index.html") { assert.ok(html.includes("/refpot-lockup.png?v=offwhite-1")); assert.ok(html.includes("/refpot-execution.png?v=offwhite-1")); } }
