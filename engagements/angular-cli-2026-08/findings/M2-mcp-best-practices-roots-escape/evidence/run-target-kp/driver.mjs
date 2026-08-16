// Driver: real GenericTargetStrategy + serializeOptions from pin source, driven
// with a mock context whose executeNgCommand mirrors the source-verified
// LocalWorkspaceHost (resolveNgCommand -> spawn shell:false, cwd only).
import { GenericTargetStrategy, serializeOptions } from '/tmp/kp-m2rt/kp-m2rt.mjs';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { join, resolve, dirname } from 'node:path';
import { accessSync, constants } from 'node:fs';

const WS = '/tmp/kp-m2rt/ws';

// (a) serializeOptions: absolute path VALUE passes verbatim; keys regex-only
const opts = {
  fileReplacements: [{ replace: 'src/main.ts', with: '/etc/passwd' }], // absolute, outside roots
  tsConfig: '/tmp/evil/tsconfig.json',                                   // absolute, unconstrained
  browser: '/etc/hosts',                                                 // absolute, unconstrained
  outputPath: '/tmp/outside/dist',                                       // absolute write target
  '--injected': 'x" y & z'                                               // key with dashes ok; value raw
};
const serialized = serializeOptions(opts);
console.log('SERIALIZED-ARGS:', JSON.stringify(serialized, null, 0));

// (b) resolveNgCommand semantics (source-verified at host.ts:124-150): createRequire(cwd/package.json)
const workspaceRequire = createRequire(join(WS, 'package.json'));
const pkgJsonPath = workspaceRequire.resolve('@angular/cli/package.json');
const pkgJson = workspaceRequire(pkgJsonPath);
const binPath = typeof pkgJson.bin === 'string' ? pkgJson.bin : pkgJson.bin['ng'];
const ngJsPath = resolve(dirname(pkgJsonPath), binPath);
console.log('RESOLVED-NG:', ngJsPath);

// mock host.executeNgCommand mirroring LocalWorkspaceHost.executeNgCommand (spawn shell:false, cwd)
async function mockExecuteNgCommand(args, options = {}) {
  const r = spawnSync(process.execPath, [ngJsPath, ...args], { cwd: options.cwd ?? WS, shell: false, encoding: 'utf8' });
  return { logs: (r.stdout + r.stderr).split('\n').filter(Boolean) };
}

// (c) run GenericTargetStrategy.execute with the free-form options
const ctx = { host: { executeNgCommand: mockExecuteNgCommand } };
const input = {
  targetName: 'build',
  projectName: 'app',
  workspacePath: WS,
  configuration: undefined,
  options: opts,
};
const result = await new GenericTargetStrategy().execute(input, ctx);
console.log('STRATEGY-STATUS:', result.status);
console.log('CHILD-ARGV (verbatim values reach the child process):');
for (const l of result.logs) console.log(' ', l);

// (d) builder-side fileReplacements semantics (options.ts:208-222): path.join(workspaceRoot, absolute) = absolute
const workspaceRoot = WS;
const replacementWith = pathJoin(workspaceRoot, '/etc/passwd');
console.log('FILE-REPLACEMENT path.join(ws, absolute):', replacementWith, '| isAbsolute:', replacementWith.startsWith('/'));
try { accessSync(replacementWith, constants.F_OK); console.log('ACCESS-CHECK: /etc/passwd exists -> passes (file read would follow)'); }
catch { console.log('ACCESS-CHECK: missing'); }

function pathJoin(root, p) { return join(root, p); }
