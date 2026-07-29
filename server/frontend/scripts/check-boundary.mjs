import { readFileSync, readdirSync, statSync } from 'node:fs';
import { extname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
const repositoryRoot = resolve(root, '../..');
const desktopServer = resolve(repositoryRoot, 'desktop/app_server.py');
const catalogPath = resolve(repositoryRoot, 'configs/layer_catalog.yaml');
const targets = [
  resolve(root, 'src'),
  resolve(repositoryRoot, 'desktop'),
  resolve(repositoryRoot, 'server/backend/gis_app.py'),
  catalogPath,
  resolve(repositoryRoot, 'scripts/build_layer_catalog.py'),
];
const forbidden = [
  /\bfr24\b/i,
  /flightradar/i,
  /aircraft\s+catalog/i,
  /\bflight\s+log\b/i,
  /review\s+queue/i,
  /from\s+['"][^'"]*skywatcher/i,
  /from\s+server\.backend\.main\s+import\s+app/i,
];
const allowedExtensions = new Set([
  '.ts',
  '.tsx',
  '.js',
  '.mjs',
  '.py',
  '.html',
  '.json',
  '.yaml',
  '.yml',
]);
const failures = [];

function visit(path) {
  if (!statSync(path).isDirectory()) {
    inspect(path);
    return;
  }
  for (const name of readdirSync(path)) {
    const child = join(path, name);
    const stat = statSync(child);
    if (stat.isDirectory()) {
      visit(child);
      continue;
    }
    inspect(child);
  }
}

function inspect(path) {
  if (!allowedExtensions.has(extname(path))) return;
  const source = readFileSync(path, 'utf8');
  for (const pattern of forbidden) {
    const offendingLine = source.split(/\r?\n/)
      .find((line) => pattern.test(line) && !line.includes('boundary-exclusion'));
    if (offendingLine) {
      failures.push(`${relative(repositoryRoot, path)}: ${pattern}`);
    }
  }
}

for (const target of targets) visit(target);
const desktopSource = readFileSync(desktopServer, 'utf8');
if (!/from\s+server\.backend\.gis_app\s+import\s+app/.test(desktopSource)) {
  failures.push('desktop/app_server.py: canonical GIS runtime import missing');
}
const catalogSource = readFileSync(catalogPath, 'utf8');
for (const pattern of [
  /^\s*-\s+id:\s*flight_activity\s*$/im,
  /^\s*domain:\s*flights\s*$/im,
  /^\s*-\s+layer_id:\s*flights\s*$/im,
]) {
  if (pattern.test(catalogSource)) {
    failures.push(`configs/layer_catalog.yaml: ${pattern}`);
  }
}
if (failures.length) {
  console.error('Spiderweb runtime boundary violations:');
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exit(1);
}
console.log('Spiderweb runtime boundary: clean');
