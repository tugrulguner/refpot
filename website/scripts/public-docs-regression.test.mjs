import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
const root=new URL('../',import.meta.url);
execFileSync(process.execPath,['scripts/sync-public-docs.mjs'],{cwd:root});
test('generated recovery and API evidence links resolve to real public destinations',async()=>{
 for(const name of ['internals/recovery','reference/api']){
  const text=await readFile(new URL(`src/content/docs/${name}.md`,root),'utf8');
  assert.ok(text.includes('(/project/package-performance/)'),'measured results must use their published page');
  assert.doesNotMatch(text,/\]\(\.\.\/benchmarks\/package-performance\//);
 }
});
test('rendered roadmap does not retain repository-relative destinations',async()=>{
 const text=await readFile(new URL('src/content/docs/project/roadmap.md',root),'utf8');
 assert.doesNotMatch(text,/\]\((?:docs\/|benchmarks\/)/);
 assert.ok(text.includes('(/package-contract/)'));
 assert.match(text,/https:\/\/github\.com\/tugrulguner\/refpot\/blob\/[a-f0-9]{40}\/docs\/releasing\.md/);
});
test('roadmap exports preserve proposed unified query examples and all planned milestones',async()=>{
 const canonical=await readFile(new URL('../ROADMAP.md',root),'utf8');
 const download=await readFile(new URL('public/docs/project-roadmap.md',root),'utf8');
 const page=await readFile(new URL('src/content/docs/project/roadmap.md',root),'utf8');
 assert.equal(download,canonical);
 const code=text=>[...text.matchAll(/```python\n([\s\S]*?)\n```/g)].map(match=>match[1]);
 assert.deepEqual(code(page),code(canonical));
 assert.equal(code(page).length,1);
 assert.match(code(page)[0],/db\.execute\(query=/);
 assert.match(code(page)[0],/agent=True/);
 assert.match(page,/Proposed API, not available in the published package/);
 const agenda='## Deterministic engine and usability are the primary design agenda';
 assert.ok(page.includes(agenda));
 assert.ok(page.indexOf(agenda)<page.indexOf('## One query interface'));
 assert.match(page,/with agents completely disabled/);
 assert.deepEqual([...page.matchAll(/^## (M\d+)\./gm)].map(match=>match[1]),Array.from({length:10},(_,i)=>`M${i}`));
 assert.doesNotMatch(page.split('## M0.')[1],/- \[x\]/);
});
test('published evidence uses existing pinned source objects, not mutable main links',async()=>{
 const destinations=new Set();
 for(const name of ['project/benchmarks','project/package-performance','internals/recovery','reference/api']){
  const text=await readFile(new URL(`src/content/docs/${name}.md`,root),'utf8');
  assert.doesNotMatch(text,/\]\(https:\/\/github\.com\/tugrulguner\/refpot\/(?:blob|tree)\/main\//);
  for(const match of text.matchAll(/https:\/\/github\.com\/tugrulguner\/refpot\/(?:blob|tree)\/([a-f0-9]{40})\/([^\s)#?]+)/g)) destinations.add(`${match[1]}:${decodeURIComponent(match[2])}`);
 }
 assert.ok(destinations.size>0);
 for(const object of destinations) execFileSync('git',['cat-file','-e',object],{cwd:new URL('../',root)});
});
test('different practical guides have topic-specific metadata',async()=>{
 const descriptions=[];
 for(const name of ['crud','transactions','persistence','errors']){
  const text=await readFile(new URL(`src/content/docs/build/${name}.md`,root),'utf8');
  descriptions.push(/^description: (.+)$/m.exec(text)?.[1]);
 }
 assert.equal(new Set(descriptions).size,4);
});
