// D1 SSR runtime demo — minimal express-less http server.
// Simulates the production SSR server: on each request, the routes chunk for the
// requested path is (re)loaded (lazy chunk fetch at navigation time) and executed;
// the D1 comma-exec payload fires at module eval (module-scope IIFE).
import http from 'node:http';
import { pathToFileURL } from 'node:url';
import { readFileSync } from 'node:fs';

const MODE = process.env.SSR_MODE || 'malicious'; // or 'benign'
const PORT = 50881;
const routesFile = MODE === 'benign' ? '/tmp/nr2-d1ssr/routes-benign.mjs' : '/tmp/nr2-d1ssr/routes-malicious.mjs';
const marker = 'D1-SSR-RUNTIME-MARKER';
let bootMarker = null;

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  const path = url.pathname;
  let markerFired = false;
  try {
    // cache-bust so each request re-executes the chunk (lazy-fetch simulation)
    const mod = await import(pathToFileURL(routesFile).href + '?t=' + Date.now());
    const routes = mod.default ?? [];
    markerFired = globalThis.__pwned === marker;
    const matched = routes.some(r => r.path === path.replace(/^\//, '') || r.path === path);
    const routeSummary = routes.map(r => {
      const hasInjectedExec = typeof r.loadChildren === 'function' && r.loadChildren.__ssrInject === undefined
        ? 'loadChildren=IIFE(exec-at-eval)'
        : `loadChildren=${typeof r.loadChildren}`;
      return `${JSON.stringify(r.path)} ${r.loadChildren ? '-> ' + hasInjectedExec : ''}`;
    }).join(' | ');
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({
      mode: MODE, path, markerFired,
      attackerMarker: globalThis.__pwned ?? null,
      routes: routeSummary,
      requestTimeExecution: markerFired,
    }, null, 2));
  } catch (e) {
    res.writeHead(500, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ mode: MODE, error: e.message }));
  }
});

server.listen(PORT, () => {
  console.log(`[SSR] listening on ${PORT} mode=${MODE}`);
});
