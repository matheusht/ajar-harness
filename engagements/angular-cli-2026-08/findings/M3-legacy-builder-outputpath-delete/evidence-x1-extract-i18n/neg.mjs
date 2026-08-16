import { isSubDirectory } from '/Users/matheusvsky/Documents/trab/llm-redteam-harness/upstream/angular-cli/packages/angular/build/src/utils/path.ts';
const WS = '/tmp/extract-poc/ws';
console.log('isSubDirectory(ws, evil-out):', isSubDirectory(WS, '/tmp/extract-poc/evil-out/messages.xlf'), '(false => application builder would THROW at index.ts:284)');
console.log('isSubDirectory(ws, in-workspace):', isSubDirectory(WS, '/tmp/extract-poc/ws/dist/messages.xlf'), '(true => contained)');
