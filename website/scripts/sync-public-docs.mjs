import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';
const root = new URL('../', import.meta.url);
const roadmap = await readFile(new URL('../../ROADMAP.md', import.meta.url), 'utf8');
const roadmapPage = new URL('src/content/docs/project/roadmap.md', root);
await mkdir(dirname(roadmapPage.pathname), { recursive: true });
await writeFile(roadmapPage, '---\ntitle: Roadmap\ndescription: Canonical RefPot research milestones, generated from the repository roadmap.\n---\n\n' + roadmap.replace(/^# [^\n]*\n/, '') + '\n[Download the canonical roadmap as Markdown](/docs/project-roadmap.md).\n');
const mappings = [
  ['src/content/docs/status.md', 'public/docs/status.md'],
  ['src/content/docs/design-direction.md', 'public/docs/design.md'],
  ['src/content/docs/performance-method.md', 'public/docs/performance-method.md'],
];
for (const [source, destination] of mappings) {
  const canonical = await readFile(new URL(source, root), 'utf8');
  const target = new URL(destination, root);
  await mkdir(dirname(target.pathname), { recursive: true });
  await writeFile(target, canonical.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, ''));
}
await writeFile(new URL('public/docs/project-roadmap.md', root), roadmap);
await writeFile(new URL('public/docs/project-readme.md', root), await readFile(new URL('../../README.md', import.meta.url)));
