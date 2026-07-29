import { readFileSync, readdirSync, statSync } from 'node:fs';
import { extname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
const repositoryRoot = resolve(root, '../..');
const desktopServer = resolve(repositoryRoot, 'desktop/app_server.py');
const runtimeTargets = [
  resolve(root, 'src'),
  resolve(repositoryRoot, 'desktop'),
  resolve(repositoryRoot, 'server/backend/gis_app.py'),
  resolve(repositoryRoot, 'scripts/build_layer_catalog.py'),
  resolve(repositoryRoot, 'scripts/build_pin_registry.py'),
];
const configurationTargets = [resolve(repositoryRoot, 'configs')];
const forbidden = [
  /\bfr24\b/i,
  /flightradar/i,
  /aircraft\s+catalog/i,
  /\bflight\s+log\b/i,
  /review\s+queue/i,
  /from\s+['"][^'"]*skywatcher/i,
  /from\s+server\.backend\.main\s+import\s+app/i,
];
const forbiddenCatalogEntries = [
  /(?:^|[\s{"'])id["']?\s*:\s*["']?flight_activity(?:["'\s,}]|$)/im,
  /(?:^|[\s{"'])domain["']?\s*:\s*["']?flights(?:["'\s,}]|$)/im,
  /(?:^|[\s{"'])layer_id["']?\s*:\s*["']?flights(?:["'\s,}]|$)/im,
  /(?:^|[\s{"'])pin_group["']?\s*:\s*["']?flight_activity(?:["'\s,}]|$)/im,
  /(?:^|[\s{"'])pin_class["']?\s*:\s*["']?flights(?:["'\s,}]|$)/im,
  /(?:^|[\s{"'])pin_layer["']?\s*:\s*["']?flights(?:["'\s,}]|$)/im,
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

function inspectConfiguration(path) {
  if (!allowedExtensions.has(extname(path))) return;
  const source = readFileSync(path, 'utf8');
  for (const pattern of forbiddenCatalogEntries) {
    if (pattern.test(source)) {
      failures.push(`${relative(repositoryRoot, path)}: ${pattern}`);
    }
  }
}

function visitConfiguration(path) {
  if (!statSync(path).isDirectory()) {
    inspectConfiguration(path);
    return;
  }
  for (const name of readdirSync(path)) {
    const child = join(path, name);
    const stat = statSync(child);
    if (stat.isDirectory()) {
      visitConfiguration(child);
      continue;
    }
    inspectConfiguration(child);
  }
}

for (const target of runtimeTargets) visit(target);
for (const target of configurationTargets) visitConfiguration(target);
const desktopSource = readFileSync(desktopServer, 'utf8');
if (!/from\s+server\.backend\.gis_app\s+import\s+app/.test(desktopSource)) {
  failures.push('desktop/app_server.py: canonical GIS runtime import missing');
}
if (failures.length) {
  console.error('Spiderweb runtime boundary violations:');
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exit(1);
}
console.log('Spiderweb runtime boundary: clean');
