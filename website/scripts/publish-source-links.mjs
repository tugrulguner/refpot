import { posix } from 'node:path';
const pages = new Map([
 ['docs/package-contract.md','/package-contract/'],
 ['docs/usage.md','/package/'],
 ['docs/package-recommendation.md','/status/'],
 ['ROADMAP.md','/project/roadmap/'],
 ['benchmarks/package-performance/RESULTS.md','/project/package-performance/'],
 ['benchmarks/random-updates/README.md','/project/benchmarks/'],
]);
// Keep literal examples untouched, including unmatched and unequal-length fences.
export function mapMarkdownProse(markdown, transform) {
 let fence = null;
 return (markdown.match(/[^\n]*\n|[^\n]+$/g) ?? []).map(line => {
  if (fence) {
   const close = /^ {0,3}(`+|~+)[ \t]*(?:\r?\n)?$/.exec(line);
   if (close && close[1][0] === fence.marker && close[1].length >= fence.length) fence = null;
   return line;
  }
  const open = /^ {0,3}(`{3,}|~{3,})([^\n]*)/.exec(line);
  if (open && !(open[1][0] === '`' && open[2].includes('`'))) {
   fence = { marker: open[1][0], length: open[1].length };
   return line;
  }
  let cursor = 0, output = '';
  for (const match of line.matchAll(/(?<!`)(`+)(?!`)(.*?)\1(?!`)/g)) {
   output += transform(line.slice(cursor, match.index)) + match[0];
   cursor = match.index + match[0].length;
  }
  return output + transform(line.slice(cursor));
 }).join('');
}
// Resolve in the original repository file's context, not its generated URL.
export function publishSourceLinks(markdown, sourcePath, revision) {
 if(!/^[a-f0-9]{40}$/.test(revision)) throw new Error('A pinned repository revision is required.');
 return mapMarkdownProse(markdown, prose => prose.replace(/(!?)\[([^\]\n]*)\]\(([^\s)]+)\)/g, (match,image,label,target)=>{
  if(/^(?:[a-z][a-z\d+.-]*:|\/|#)/i.test(target)) return match;
  const [,path,suffix='']=/^([^?#]*)(.*)$/.exec(target);
  const resolved=posix.normalize(posix.join(posix.dirname(sourcePath),path));
  if(resolved.startsWith('../')) throw new Error(`Repository link escapes source root: ${target}`);
  const href=image
   ? `https://raw.githubusercontent.com/tugrulguner/refpot/${revision}/${resolved}${suffix}`
   : `${pages.get(resolved) ?? `https://github.com/tugrulguner/refpot/blob/${revision}/${resolved}`}${suffix}`;
  return `${image}[${label}](${href})`;
 }));
}
