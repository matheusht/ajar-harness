// Shape-B mechanics: the tool call looks normal; the resolution escapes via a repo-shipped symlink.
import { join, resolve } from 'node:path';
import { readFileSync, realpathSync, existsSync } from 'node:fs';

const WS = '/tmp/n4c/ws';
const OUTSIDE = '/tmp/n4c/outside';

// 1. What serializeOptions would emit for the steered options (keys regex-validated, values verbatim):
const options = { browser: 'src/main.ts', tsConfig: 'tsconfig.app.json' };
const argv = Object.entries(options).map(([k, v]) => `--${k}=${v}`);
console.log('TOOL-CALL ARGV (what the agent sees):', JSON.stringify(argv));
console.log('ANOMALY SCAN:', /\.\./.test(argv.join(' ')) ? 'VISIBLE ..' : 'none (no dot-dot, no absolute, no outside path)');

// 2. Lexical resolution vs real resolution:
const lex = resolve(WS, options.browser);
const real = realpathSync(lex);
console.log('lexical:', lex, '| in-workspace:', lex.startsWith(WS));
console.log('realpath:', real, '| outside workspace:', !real.startsWith(WS));
console.log('readFileSync via the symlink returns:', JSON.stringify(readFileSync(lex, 'utf8').split('\n').pop()));

// 3. The host-side check (what a containment check WOULD see) — the anomaly is invisible to a lexical check:
console.log('lexical containment check passes (no anomaly):', lex.startsWith(WS));
console.log('realpath containment check would flag:', !real.startsWith(WS));
console.log('SECRET-42 marker present in read content:', readFileSync(lex, 'utf8').includes('SECRET-42-N4C'));
