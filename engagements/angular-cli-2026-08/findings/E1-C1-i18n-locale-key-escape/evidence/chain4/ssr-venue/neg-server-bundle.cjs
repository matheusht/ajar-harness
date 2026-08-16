// Negative control: benign locale data (the real @angular/common fr.js shape) — no attacker marker
const fs = require('node:fs');
const B = '/tmp/c4a/node_modules/@babel';
const { transformAsync } = require(B + '/core');
async function loadLocaleData(p, opt) {
  const content = await fs.promises.readFile(p, 'utf8');
  const r = await transformAsync(content, { filename: p, inputSourceMap: false, babelrc: false, configFile: false,
    presets: [[require.resolve(B + '/preset-env'), { targets: { esmodules: true } }]], minified: false, compact: false, comments: true });
  return r.code;
}
(async () => {
  const benign = '// benign locale data\nconst frData = {locale:"fr"};';
  fs.writeFileSync('/tmp/ssr-venue/benign-locale.js', benign);
  const code = await loadLocaleData('/tmp/ssr-venue/benign-locale.js', true);
  const out = `globalThis.$localize=Object.assign(globalThis.$localize||{},{locale:"fr"});\n${code};\nconsole.log('[NEG-CONTROL] server boot — no attacker marker expected');\nprocess.exit(0);`;
  fs.writeFileSync('/tmp/ssr-venue/server-neg.js', out);
  console.log('[NEG] benign bundle built');
})();
