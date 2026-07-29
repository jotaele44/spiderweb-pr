import { readFileSync, readdirSync, statSync } from 'node:fs';
import { extname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
const repositoryRoot = resolve(root, '../..');
const targets = [resolve(root, 'src'), resolve(repositoryRoot, 'desktop')];
const forbidden = [
  /\bfr24\b/i,
  /flightradar/i,
  /aircraft\s+catalog/i,
  /\bflight\s+log\b/i,
  /review\s+queue/i,
  /from\s+['"][^'"]*skywatcher/i,
];
const allowedExtensions = new Set(['.ts', '.tsx', '.js', '.mjs', '.py', '.html']);
const failures = [];

function visit(path) {
  for (const name of readdirSync(path)) {
    const child = join(path, name);
    const stat = statSync(child);
    if (stat.isDirectory()) {
      visit(child);
      continue;
    }
    if (!allowedExtensions.has(extname(name))) continue;
    const source = readFileSync(child, 'utf8');
    for (const pattern of forbidden) {
      if (pattern.test(source)) {
        failures.push(`${relative(repositoryRoot, child)}: ${pattern}`);
      }
    }
  }
}

for (const target of targets) visit(target);
if (failures.length) {
  console.error('Spiderweb runtime boundary violations:');
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exit(1);
}
console.log('Spiderweb runtime boundary: clean');
