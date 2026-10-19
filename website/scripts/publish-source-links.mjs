import { posix } from 'node:path';
const pages = new Map([
 ['docs/package-contract.md','/package-contract/'],
 ['docs/usage.md','/package/'],
 ['docs/package-recommendation.md','/status/'],
 ['ROADMAP.md','/project/roadmap/'],
 ['benchmarks/package-performance/RESULTS.md','/project/package-performance/'],
 ['benchmarks/random-updates/README.md','/project/performance/'],
]);
// Resolve in the original repository file's context, not its generated URL.
export function publishSourceLinks(markdown, sourcePath, revision) {
 if(!/^[a-f0-9]{40}$/.test(revision)) throw new Error('A pinned repository revision is required.');
 return markdown.replace(/(!?)\[([^\]\n]*)\]\(([^\s)]+)\)/g, (match,image,label,target)=>{
  if(/^(?:[a-z][a-z\d+.-]*:|\/|#)/i.test(target)) return match;
  const [,path,suffix='']=/^([^?#]*)(.*)$/.exec(target);
  const resolved=posix.normalize(posix.join(posix.dirname(sourcePath),path));
  if(resolved.startsWith('../')) throw new Error(`Repository link escapes source root: ${target}`);
  const href=image
   ? `https://raw.githubusercontent.com/tugrulguner/refpot/${revision}/${resolved}${suffix}`
   : `${pages.get(resolved) ?? `https://github.com/tugrulguner/refpot/blob/${revision}/${resolved}`}${suffix}`;
  return `${image}[${label}](${href})`;
 });
}
