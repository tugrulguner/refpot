import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';
const root = new URL('../', import.meta.url);
const roadmap = await readFile(new URL('../../ROADMAP.md', import.meta.url), 'utf8');
const roadmapPage = new URL('src/content/docs/project/roadmap.md', root);
await mkdir(dirname(roadmapPage.pathname), { recursive: true });
await writeFile(roadmapPage, '---\ntitle: Roadmap\ndescription: Canonical RefPot research milestones, generated from the repository roadmap.\n---\n\n' + roadmap.replace(/^# [^\n]*\n/, '') + '\n[Download the canonical roadmap as Markdown](/docs/project-roadmap.md).\n');
const packageContract = await readFile(new URL('../../docs/package-contract.md', import.meta.url), 'utf8');
const packagePage = packageContract.replace(/^# [^\n]*\n/, '')
  .replaceAll('(package-recommendation.md)', '(/package/)')
  .replaceAll('(../ROADMAP.md)', '(/project/roadmap/)')
  .replaceAll('(../benchmarks/random-updates/README.md)', '(https://github.com/tugrulguner/refpot/tree/main/benchmarks/random-updates)');
await writeFile(new URL('src/content/docs/package-contract.md', root), '---\ntitle: Package contract\nslug: package-contract\ndescription: Exact capabilities and boundaries of the unreleased RefPot source-build preview.\n---\n' + packagePage);
const mappings = [
  ['src/content/docs/status.md', 'public/docs/status.md'],
  ['src/content/docs/design-direction.md', 'public/docs/design.md'],
  ['src/content/docs/performance-method.md', 'public/docs/performance-method.md'],
  ['src/content/docs/package-contract.md', 'public/docs/package-contract.md'],
  ['src/content/docs/package.md', 'public/docs/package.md'],
];
for (const [source, destination] of mappings) {
  const canonical = await readFile(new URL(source, root), 'utf8');
  const target = new URL(destination, root);
  await mkdir(dirname(target.pathname), { recursive: true });
  await writeFile(target, canonical.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, ''));
}
await writeFile(new URL('public/docs/project-roadmap.md', root), roadmap);
await writeFile(new URL('public/docs/project-readme.md', root), await readFile(new URL('../../README.md', import.meta.url)));
await writeFile(new URL('public/docs/package-recommendation.md', root), await readFile(new URL('../../docs/package-recommendation.md', import.meta.url)));
await writeFile(new URL('public/docs/package-contract-source.md', root), await readFile(new URL('../../docs/package-contract.md', import.meta.url)));
