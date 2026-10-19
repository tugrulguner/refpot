import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { publishSourceLinks, mapMarkdownProse } from './publish-source-links.mjs';
const root = new URL('../', import.meta.url);
const repositoryRoot = new URL('../../', import.meta.url);
// Pin canonical source history, so website-only commits do not churn derived docs.
const revision = execFileSync('git', ['log', '-1', '--format=%H', '--', 'README.md', 'ROADMAP.md', 'docs', 'benchmarks', 'skills', 'CONTRIBUTING.md'], { cwd: repositoryRoot, encoding: 'utf8' }).trim();
const publish = (content, source) => publishSourceLinks(content, source, revision);
const rewriteProse = (content, rewrite) => mapMarkdownProse(content, prose => rewrite(prose)
  .replaceAll('https://github.com/tugrulguner/refpot/blob/main/', `https://github.com/tugrulguner/refpot/blob/${revision}/`)
  .replaceAll('https://github.com/tugrulguner/refpot/tree/main/', `https://github.com/tugrulguner/refpot/tree/${revision}/`));
const roadmap = await readFile(new URL('../../ROADMAP.md', import.meta.url), 'utf8');
const roadmapPage = new URL('src/content/docs/project/roadmap.md', root);
await mkdir(dirname(roadmapPage.pathname), { recursive: true });
await writeFile(roadmapPage, '---\ntitle: Roadmap\ndescription: Canonical RefPot research milestones, generated from the repository roadmap.\n---\n\n' + publish(roadmap.replace(/^# [^\n]*\n/, ''), 'ROADMAP.md') + '\n[Download the canonical roadmap as Markdown](/docs/project-roadmap.md).\n');
const sourceContract = await readFile(new URL('../../docs/package-contract.md', import.meta.url), 'utf8');
const usage = await readFile(new URL('../../docs/usage.md', import.meta.url), 'utf8');
const splitSections = (source) => {
  const sections = new Map();
  let heading = '';
  for (const line of source.split(/\r?\n/)) {
    if (line.startsWith('## ')) { heading = line.slice(3).trim(); sections.set(heading, []); }
    if (heading) sections.get(heading).push(line);
  }
  return sections;
};
const sources = { contract: splitSections(sourceContract), usage: splitSections(usage) };
const guideRegistry = [
  { slug: 'build/crud', title: 'CRUD', description: 'Insert, read, update and delete records with the experimental RefPot Python API.', source: 'usage', sections: ['CRUD'] },
  { slug: 'build/transactions', title: 'Transactions and rollback', description: 'Use explicit RefPot transactions and verify rollback behavior in the experimental alpha.', source: 'usage', sections: ['Transactions'] },
  { slug: 'build/persistence', title: 'Persistence and checkpointing', description: 'Reopen RefPot databases and manage checkpoints within the documented alpha persistence limits.', source: 'usage', sections: ['Persistence'] },
  { slug: 'build/errors', title: 'Errors and ownership', description: 'Handle RefPot errors and understand database ownership restrictions in the experimental alpha.', source: 'usage', sections: ['Errors and ownership'] },
  { slug: 'reference/api', title: 'Python API reference', description: 'Reference for RefPot records, Python operations, ownership rules and current alpha boundaries.', source: 'contract', sections: ['Records and operations', 'Python API', 'Ownership and concurrency', 'Performance and maturity'] },
  { slug: 'internals/recovery', title: 'Storage and recovery internals', description: 'Understand RefPot on-disk behavior, ownership and recovery boundaries with scoped package evidence.', source: 'contract', sections: ['Ownership and concurrency', 'On-disk behavior', 'Performance and maturity'] },
];
for (const page of guideRegistry) {
  const prerequisites = page.source === 'usage' ? usage.split('\n## ')[0].replace(/^# [^\n]*\n/, '').trim() + '\n\n' : '';
  const selectedContent = rewriteProse(prerequisites + page.sections.map(name => {
    const section = sources[page.source].get(name);
    if (!section) throw new Error(`Missing canonical section ${page.source}: ${name}`);
    const selected = section.join('\n');
    return page.source === 'usage' ? selected.replace(/^## [^\n]*\n/, '').replace(/^### /gm, '## ') : selected;
  }).join('\n\n'), prose => prose
    .replaceAll('(package-recommendation.md)', '(/status/)')
    .replaceAll('(../ROADMAP.md)', '(/project/roadmap/)')
    .replaceAll('(../benchmarks/random-updates/README.md)', '(https://github.com/tugrulguner/refpot/tree/main/benchmarks/random-updates)'));
  const content = publish(selectedContent, page.source === 'usage' ? 'docs/usage.md' : 'docs/package-contract.md');
  const route = page.slug.replaceAll('/', '-');
  const sourcePath = new URL(`src/content/docs/${page.slug}.md`, root);
  await mkdir(dirname(sourcePath.pathname), { recursive: true });
  const download = new URL(`public/docs/${route}.md`, root);
  await mkdir(dirname(download.pathname), { recursive: true });
  await writeFile(download, `${content.trimEnd()}\n`);
  const guideLink = `\n\n[Download this page as Markdown](/docs/${route}.md)\n`;
  await writeFile(sourcePath, `---\ntitle: ${page.title}\ndescription: ${JSON.stringify(page.description)}\n---\n\n${content}${guideLink}`);
}
const manuals = [
  { slug: 'project/benchmarks', title: 'Historical benchmark results', source: '../../benchmarks/random-updates/README.md', prefix: '../../docs/evidence.md' },
  { slug: 'project/package-performance', title: 'Package performance results', source: '../../benchmarks/package-performance/RESULTS.md' },
  { slug: 'project/contributing', title: 'Contributing to RefPot', source: '../../CONTRIBUTING.md' },
  { slug: 'reference/agent-guide', title: 'Using RefPot with a coding agent', source: '../../skills/refpot-database/SKILL.md' },
];
for (const manual of manuals) {
  const source = await readFile(new URL(manual.source, import.meta.url), 'utf8');
  let content = source.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, '').trimStart().replace(/^# [^\n]*\n/, '').trim();
  if (manual.prefix) {
    const prefix = await readFile(new URL(manual.prefix, import.meta.url), 'utf8');
    content = publish(prefix.replace(/^# [^\n]*\n/, '').trim(), relative(fileURLToPath(repositoryRoot), fileURLToPath(new URL(manual.prefix, import.meta.url)))) + '\n\n## Retained experimental report\n\n' + content;
  }
  content = rewriteProse(content, prose => prose.replaceAll('(../../docs/assets/refpot-benchmark.png)', '(/refpot-benchmark.png)')
    .replaceAll('(../../docs/assets/refpot-benchmark.svg)', '(/refpot-benchmark.svg)')
    .replaceAll('(benchmarks/package-performance/verify_evidence.py)', '(https://github.com/tugrulguner/refpot/blob/main/benchmarks/package-performance/verify_evidence.py)')
    .replaceAll('(benchmarks/package-performance/evidence/frozen-harness.py)', '(https://github.com/tugrulguner/refpot/blob/main/benchmarks/package-performance/evidence/frozen-harness.py)')
    .replaceAll('(benchmarks/package-performance/recovery_fixture.py)', '(https://github.com/tugrulguner/refpot/blob/main/benchmarks/package-performance/recovery_fixture.py)')
    .replaceAll('(evidence/frozen-harness.py)', '(https://github.com/tugrulguner/refpot/blob/main/benchmarks/package-performance/evidence/frozen-harness.py)')
    .replaceAll('(evidence/manifest.json)', '(https://github.com/tugrulguner/refpot/blob/main/benchmarks/package-performance/evidence/manifest.json)')
    .replaceAll('(AUDIT.md)', '(https://github.com/tugrulguner/refpot/blob/main/benchmarks/random-updates/AUDIT.md)')
    .replaceAll('(reproduce.py)', '(https://github.com/tugrulguner/refpot/blob/main/benchmarks/random-updates/reproduce.py)')
    .replaceAll('(data/raw-records.tar.gz)', '(https://github.com/tugrulguner/refpot/tree/main/benchmarks/random-updates/data)'));
  content = publish(content, relative(fileURLToPath(repositoryRoot), fileURLToPath(new URL(manual.source, import.meta.url))));
  const download = manual.slug.replaceAll('/', '-') + '.md';
  const path = new URL(`src/content/docs/${manual.slug}.md`, root);
  await mkdir(dirname(path.pathname), { recursive: true });
  await writeFile(path, `---\ntitle: ${manual.title}\ndescription: Canonical RefPot guidance and evidence with explicit scope.\n---\n\n${content}\n\n[Download this page as Markdown](/docs/${download})\n`);
  await writeFile(new URL(`public/docs/${download}`, root), `${content}\n`);
}
const packagePage = rewriteProse(sourceContract.replace(/^# [^\n]*\n/, ''), prose => prose
  .replaceAll('(package-recommendation.md)', '(/package/)')
  .replaceAll('(../ROADMAP.md)', '(/project/roadmap/)')
  .replaceAll('(../benchmarks/random-updates/README.md)', '(https://github.com/tugrulguner/refpot/tree/main/benchmarks/random-updates)')
  .replaceAll('(../benchmarks/package-performance/RESULTS.md)', '(/project/package-performance/)')
  .replaceAll('(../benchmarks/package-performance/README.md)', '(https://github.com/tugrulguner/refpot/tree/main/benchmarks/package-performance)'));
await writeFile(new URL('src/content/docs/package-contract.md', root), '---\ntitle: Package contract\nslug: package-contract\ndescription: Exact capabilities and boundaries of the experimental RefPot alpha.\n---\n' + packagePage);
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
