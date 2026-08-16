/**
 * ws1b.spec.mjs — operator deliverable: safety-contract test suite for the
 * `update-models` GitHub Action (angular/dev-infra, pinned 04230133d395dfb032d782b8e63b4fcbbd406aa5).
 *
 * Engagement context (lane D3, authorized white-box, Google OSS VRP):
 *   - lib/main.ts parses the Gemini deprecations page and rewrites every matched model
 *     token VERBATIM into every .ts/.yml/.yaml file in the repo (glob dot:true, incl.
 *     workflows).
 *   - The ONLY input filter is `replacement.includes('gemini')`; the needle (old model)
 *     is entirely unfiltered. No test coverage exists for this tool.
 *   - Proven in D3: TS literal breakout (computed-key async IIFE -> PWNED.txt, `node --check`
 *     PASSES), YAML new-job injection (duplicate/inserted key, last-wins), and the checked-in
 *     bundle's glob ignore list differs from source (node_modules is NOT excluded in production).
 *
 * What this suite asserts (the fail-closed contract the WS1a fix must satisfy):
 *   1. Normal parse + rewrite of a known model pair.
 *   2. Page-structure change -> clean no-op / fail-closed (no writes).
 *   3. Injection payloads (quote-breakout, computed-key IIFE, YAML key injection, template
 *      backticks, extreme length, missing `gemini-` prefix, braces/backticks) must each be
 *      rejected or safely escaped -> target files remain byte-identical.
 *   4. Glob/scope: node_modules (real AND symlinked) never rewritable; .git/dist excluded;
 *      workflow ymls rewritable ONLY when legitimately targeted by a safe replacement.
 *   5. Rewritten TS must survive `node --check` (and `tsc --noEmit` when a tsc binary is
 *      configured via TSC_BIN).
 *
 * IMPORTANT: this suite executes the DEPLOYED artifact (`.github/local-actions/update-models/
 * main.js` — what action.yml actually runs), NOT lib/main.ts. On the pinned commit the bundle
 * is vulnerable, so the injection/scope tests FAIL by design: their failure transcript is the
 * vulnerability evidence. After the WS1a hardening lands, the same suite must be fully green.
 *
 * Run standalone:
 *   node --test --test-reporter=spec /tmp/ws1b.spec.mjs
 *   (override the bundle path with UPDATE_MODELS_BUNDLE=... if the clone lives elsewhere)
 *
 * In-repo wiring (BUILD.bazel jasmine_test pattern) is documented at the bottom of this file
 * and in the accompanying report.
 *
 * @license
 * Copyright Google LLC — MIT-style license (see LICENSE at angular.io).
 * Engagement deliverable, read-only vs the target tree; scratch confined to /tmp.
 */

import {describe, it, before, after} from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync, symlinkSync, existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';

/** The deployed artifact (what action.yml runs). Override via UPDATE_MODELS_BUNDLE. */
const MAIN = process.env.UPDATE_MODELS_BUNDLE ??
  '/Users/matheusvsky/Documents/trab/llm-redteam-harness/upstream/dev-infra' +
    '/.github/local-actions/update-models/main.js';

/** Side-effect marker the computed-key IIFE payload tries to create. */
const MARKER = path.join(tmpdir(), 'ws1b-PWNED.txt');

/** Deprecations-page HTML with a single model pair (4 cells, tds[3] = replacement). */
function htmlFor(replacement, model = 'gemini-1.5-pro') {
  return [
    '<html><body><table><tbody><tr>',
    `<td><code>${model}</code></td>`,
    '<td>Deprecated</td>',
    '<td>2026-01-01</td>',
    `<td><code>${replacement}</code></td>`,
    '</tr></tbody></table></body></html>',
  ].join('');
}

/** HTML that structurally resembles the page but carries no parseable replacement rows. */
function htmlNoRows() {
  return '<html><body><h1>Gemini API deprecations</h1><p>No tables today.</p></body></html>';
}

/** HTML whose rows all carry colspan (parser skips them). */
function htmlColspanRows() {
  return [
    '<html><body><table><tbody>',
    '<tr><td colspan="4">Gemini 1.5 Pro deprecated</td></tr>',
    '</tbody></table></body></html>',
  ].join('');
}

/**
 * Run the REAL deployed bundle in a child process against a scratch fixture repo.
 * `fetch` is stubbed via an --import preload that overrides globalThis.fetch.
 * Returns {exit, stdout, stderr, files} where files maps fixture path -> post-run content.
 */
function runTool({html, files = {}, pre, fetchMode = 'ok'}) {
  const dir = mkdtempSync(path.join(tmpdir(), 'ws1b-fx-'));
  try {
    for (const [name, content] of Object.entries(files)) {
      const p = path.join(dir, name);
      mkdirSync(path.dirname(p), {recursive: true});
      writeFileSync(p, content);
    }
    if (pre) {
      pre(dir);
    }
    let fetchBody;
    if (fetchMode === 'http500') {
      fetchBody = `new Response('Internal Server Error', {status: 500})`;
    } else if (fetchMode === 'throw') {
      fetchBody = `(() => { throw new Error('network down'); })()`;
    } else {
      fetchBody = `new Response(${JSON.stringify(html)}, {status: 200, headers: {'content-type': 'text/html'}})`;
    }
    writeFileSync(
      path.join(dir, 'preload.mjs'),
      `globalThis.fetch = async () => ${fetchBody};\n`,
    );
    const res = spawnSync(
      process.execPath,
      ['--import', path.join(dir, 'preload.mjs'), MAIN],
      {cwd: dir, encoding: 'utf-8', timeout: 60_000},
    );
    const outFiles = {};
    for (const name of Object.keys(files)) {
      try {
        outFiles[name] = readFileSync(path.join(dir, name), 'utf-8');
      } catch {
        outFiles[name] = undefined;
      }
    }
    return {exit: res.status, stdout: res.stdout ?? '', stderr: res.stderr ?? '', files: outFiles};
  } finally {
    rmSync(dir, {recursive: true, force: true});
  }
}

/** Top-level YAML keys, cheap structural fingerprint (no yaml dependency needed). */
function yamlTopLevelKeys(yaml) {
  const keys = [];
  for (const line of yaml.split('\n')) {
    const m = /^([A-Za-z0-9_.-]+):/.exec(line);
    if (m) {
      keys.push(m[1]);
    }
  }
  return keys;
}

const TS_FIXTURE_DQ = 'const models = ["gemini-1.5-pro"];\n';
const TS_FIXTURE_COMPUTED_KEY =
  'const map = {\n' + "  ['gemini-1.5-pro']: true,\n" + '};\n';
const YML_FIXTURE = [
  'name: CI',
  'on: [push]',
  'jobs:',
  '  build:',
  '    runs-on: ubuntu-latest',
  '    container:',
  '      image: gemini-1.5-pro',
  '',
].join('\n');

before(() => {
  rmSync(MARKER, {force: true});
  if (!existsSync(MAIN)) {
    throw new Error(
      `update-models bundle not found at ${MAIN}. Point UPDATE_MODELS_BUNDLE at the clone's ` +
        `.github/local-actions/update-models/main.js`,
    );
  }
  // eslint-disable-next-line no-console
  console.log(
    '\n[ws1b] bundle under test: ' + MAIN + '\n' +
    '[ws1b] EXPECTED on the pinned commit: injection/scope contract tests FAIL (vulnerable ' +
    'bundle). Those failures are the vulnerability evidence; this suite is the regression ' +
    'gate for the WS1a hardening fix.\n',
  );
});

after(() => {
  rmSync(MARKER, {force: true});
});

describe('update-models rewrite tool — 1) normal parse + rewrite', () => {
  it('rewrites a known model pair in .ts and .yml, respecting word boundaries', () => {
    const files = {
      'models.ts':
        "const a = 'xgemini-1.5-pro';\n" +
        "const b = 'gemini-1.5-pro-v2';\n" +
        "const c = 'gemini-1.5-pro2';\n" +
        "const d = 'gemini-1.5-pro';\n",
      'config.yml': 'model: gemini-1.5-pro\n',
    };
    const r = runTool({html: htmlFor('gemini-2.0-flash'), files});
    assert.equal(r.exit, 0, `tool must exit 0 on a normal run:\n${r.stdout}\n${r.stderr}`);
    // Safe occurrence rewritten in both file types.
    assert.match(r.files['models.ts'], /const d = 'gemini-2\.0-flash';/);
    assert.match(r.files['config.yml'], /model: gemini-2\.0-flash/);
    // Word-boundary guards: prefix/suffix variants must remain untouched.
    assert.match(r.files['models.ts'], /const a = 'xgemini-1\.5-pro';/);
    assert.match(r.files['models.ts'], /const b = 'gemini-1\.5-pro-v2';/);
    assert.match(r.files['models.ts'], /const c = 'gemini-1\.5-pro2';/);
  });

  it('rewrites multiple pairs from a multi-row table', () => {
    const html =
      '<html><body><table><tbody>' +
      '<tr><td><code>gemini-1.5-pro</code></td><td>x</td><td>y</td>' +
      '<td><code>gemini-2.0-flash</code></td></tr>' +
      '<tr><td><code>gemini-1.0-pro</code></td><td>x</td><td>y</td>' +
      '<td><code>gemini-2.0-flash-lite</code></td></tr>' +
      '</tbody></table></body></html>';
    const files = {'models.ts': "const m = ['gemini-1.5-pro', 'gemini-1.0-pro'];\n"};
    const r = runTool({html, files});
    assert.equal(r.exit, 0);
    assert.match(r.files['models.ts'], /'gemini-2\.0-flash'/);
    assert.match(r.files['models.ts'], /'gemini-2\.0-flash-lite'/);
    assert.doesNotMatch(r.files['models.ts'], /gemini-1\.[05]-pro'/);
  });
});

describe('update-models rewrite tool — 2) page structure change fails closed', () => {
  const probe = 'const models = ["gemini-1.5-pro"];\n';

  it('no-ops cleanly when the page has no tbody rows (structure change)', () => {
    const r = runTool({html: htmlNoRows(), files: {'models.ts': probe}});
    assert.equal(r.exit, 0, `structure change must not fail the job:\n${r.stdout}${r.stderr}`);
    assert.match(r.stdout, /No model replacements/);
    assert.equal(r.files['models.ts'], probe, 'file must be untouched');
  });

  it('no-ops cleanly when all rows carry colspan', () => {
    const r = runTool({html: htmlColspanRows(), files: {'models.ts': probe}});
    assert.equal(r.exit, 0);
    assert.match(r.stdout, /No model replacements/);
    assert.equal(r.files['models.ts'], probe, 'file must be untouched');
  });

  it('no-ops when the replacement lacks "gemini" (only input filter)', () => {
    const r = runTool({html: htmlFor('flash-2.0'), files: {'models.ts': probe}});
    assert.equal(r.exit, 0);
    assert.match(r.stdout, /No model replacements/);
    assert.equal(r.files['models.ts'], probe, 'file must be untouched');
  });

  it('fails the job (exit 1) on HTTP 500 and writes nothing', () => {
    const r = runTool({fetchMode: 'http500', files: {'models.ts': probe}});
    assert.equal(r.exit, 1, `network failure must setFailed (exit 1):\n${r.stdout}${r.stderr}`);
    assert.match(r.stdout + r.stderr, /Failed to fetch|Error fetching/);
    assert.equal(r.files['models.ts'], probe, 'file must be untouched');
  });

  it('fails the job (exit 1) when fetch throws and writes nothing', () => {
    const r = runTool({fetchMode: 'throw', files: {'models.ts': probe}});
    assert.equal(r.exit, 1, `fetch throw must setFailed (exit 1):\n${r.stdout}${r.stderr}`);
    assert.equal(r.files['models.ts'], probe, 'file must be untouched');
  });
});

describe('update-models rewrite tool — 3) injection payloads must fail validation or be safely escaped', () => {
  // Contract: a replacement outside the strict safe shape `^gemini-[a-z0-9][a-z0-9._-]*$`
  // must be rejected/escaped so the target file stays byte-identical (fail-closed).
  const assertSafe = (name, replacement, files) => {
    const r = runTool({html: htmlFor(replacement), files});
    assert.equal(
      r.files[Object.keys(files)[0]],
      files[Object.keys(files)[0]],
      `[${name}] file must remain byte-identical (replacement rejected or safely escaped). ` +
        `Actual rewrite happened; stdout:\n${r.stdout}`,
    );
    return r;
  };

  it('TS quote-breakout payload (double-quoted literal) must not reach the file', () => {
    const payload = 'gemini-2.0-flash"; (async()=>{await import(\'node:fs\')})(); "';
    assertSafe('quote-breakout', payload, {'models.ts': TS_FIXTURE_DQ});
  });

  it('computed-key IIFE payload must not execute and must not reach the file', () => {
    // This is the D3 PoC shape: on the vulnerable bundle the rewritten object literal is
    // syntactically VALID (node --check passes) and executing it runs the IIFE.
    const payload =
      "gemini-2.0-flash']: (async()=>{const {writeFileSync}=await import('node:fs');" +
      `writeFileSync(${JSON.stringify(MARKER)},'pwned')})(), ['`;
    const files = {'models.ts': TS_FIXTURE_COMPUTED_KEY};
    const r = runTool({html: htmlFor(payload), files});
    assert.equal(
      r.files['models.ts'],
      TS_FIXTURE_COMPUTED_KEY,
      `[computed-key] file must remain byte-identical. Actual rewrite:\n${r.files['models.ts']}`,
    );
    // Even if a fix allowed a rewrite, executing the output must never create the marker.
    if (r.files['models.ts'] !== TS_FIXTURE_COMPUTED_KEY) {
      const dir = mkdtempSync(path.join(tmpdir(), 'ws1b-exec-'));
      try {
        writeFileSync(path.join(dir, 'm.mjs'), r.files['models.ts']);
        rmSync(MARKER, {force: true});
        const res = spawnSync(process.execPath, [path.join(dir, 'm.mjs')], {
          encoding: 'utf-8',
          timeout: 10_000,
        });
        assert.equal(res.status, 0, `rewritten file must remain executable-valid:\n${res.stderr}`);
        assert.equal(existsSync(MARKER), false, 'rewritten output must have no side effects');
      } finally {
        rmSync(dir, {recursive: true, force: true});
        rmSync(MARKER, {force: true});
      }
    }
  });

  it('newline + YAML key injection must not reach the file', () => {
    const payload =
      'gemini-2.0-flash\n' +
      '  evil-job:\n' +
      '    runs-on: ubuntu-latest\n' +
      '    steps:\n' +
      '      - run: echo WS1B-YAML-PWNED';
    const files = {'ci.yml': YML_FIXTURE};
    const beforeKeys = yamlTopLevelKeys(YML_FIXTURE);
    const r = assertSafe('yaml-key-injection', payload, files);
    // Structural fingerprint: same top-level keys, no new job key at any indent.
    assert.deepEqual(yamlTopLevelKeys(r.files['ci.yml']), beforeKeys);
    assert.doesNotMatch(r.files['ci.yml'], /evil-job/);
  });

  it('backtick/template-literal payload must not reach the file', () => {
    const payload = 'gemini-2.0-flash`; const x = 1; //';
    assertSafe('backtick', payload, {'models.ts': TS_FIXTURE_DQ});
  });

  it('extremely long value must not reach the file', () => {
    const payload = 'gemini-' + 'a'.repeat(100_000);
    assertSafe('extreme-length', payload, {'models.ts': TS_FIXTURE_DQ});
  });

  it('value without the gemini- prefix (but containing "gemini") must not reach the file', () => {
    // "gemini2-flash" passes the current `includes('gemini')` filter yet has no `gemini-` prefix.
    assertSafe('no-prefix', 'gemini2-flash', {'models.ts': TS_FIXTURE_DQ});
    assertSafe('no-prefix-2', 'mygemini-2.0', {'models.ts': TS_FIXTURE_DQ});
  });

  it('value with braces/backticks must not reach the file', () => {
    const payload = 'gemini-2.0-flash${process.env.HOME}';
    assertSafe('braces', payload, {'models.ts': TS_FIXTURE_DQ});
    const payload2 = '{gemini-2.0-flash}';
    assertSafe('braces-2', payload2, {'models.ts': TS_FIXTURE_DQ});
  });
});

describe('update-models rewrite tool — 4) glob/scope assertions', () => {
  const SAFE = 'gemini-2.0-flash';

  it('node_modules (real directory) is never rewritable', () => {
    const files = {
      'pkg/node_modules/dep/models.ts': "const dep = 'gemini-1.5-pro';\n",
      'pkg/app.ts': "const app = 'gemini-1.5-pro';\n",
    };
    const r = runTool({html: htmlFor(SAFE), files});
    assert.equal(r.exit, 0);
    assert.match(r.files['pkg/app.ts'], /gemini-2\.0-flash/, 'non-node_modules file should be rewritten');
    assert.match(
      r.files['pkg/node_modules/dep/models.ts'],
      /gemini-1\.5-pro/,
      'files under node_modules must never be rewritten (deployed bundle violates this: ' +
        'its ignore list is ["**/", "**/dist/**", "**/.git/**"] instead of the source\'s ' +
        '["**/node_modules/**", ...])',
    );
  });

  it('node_modules reachable only through a symlink is never rewritable', () => {
    const files = {
      'pkg/node_modules/dep/models.ts': "const dep = 'gemini-1.5-pro';\n",
      'pkg2/app.ts': "const app = 'gemini-1.5-pro';\n",
    };
    const pre = (dir) => {
      symlinkSync(path.join(dir, 'pkg', 'node_modules'), path.join(dir, 'pkg2', 'node_modules'), 'dir');
    };
    const r = runTool({html: htmlFor(SAFE), files, pre});
    assert.equal(r.exit, 0);
    assert.match(
      r.files['pkg/node_modules/dep/models.ts'],
      /gemini-1\.5-pro/,
      'files reachable only via a node_modules path (incl. symlinks) must never be rewritten',
    );
  });

  it('.git and dist are excluded from the rewrite scope', () => {
    const files = {
      '.git/objects/models.ts': "const g = 'gemini-1.5-pro';\n",
      'dist/models.ts': "const d = 'gemini-1.5-pro';\n",
      'src/models.ts': "const s = 'gemini-1.5-pro';\n",
    };
    const r = runTool({html: htmlFor(SAFE), files});
    assert.equal(r.exit, 0);
    assert.match(r.files['src/models.ts'], /gemini-2\.0-flash/);
    assert.match(r.files['.git/objects/models.ts'], /gemini-1\.5-pro/, '.git must stay excluded');
    assert.match(r.files['dist/models.ts'], /gemini-1\.5-pro/, 'dist must stay excluded');
  });

  it('workflow yml is rewritable ONLY when legitimately targeted by a safe replacement', () => {
    const workflow = [
      'name: CI',
      'on: [push]',
      'jobs:',
      '  build:',
      '    runs-on: ubuntu-latest',
      '    container:',
      '      image: gemini-1.5-pro',
      '',
    ].join('\n');
    // Legitimately targeted: contains the deprecated model, safe replacement -> rewrite allowed.
    const legit = runTool({html: htmlFor(SAFE), files: {'.github/workflows/ci.yml': workflow}});
    assert.equal(legit.exit, 0);
    assert.match(legit.files['.github/workflows/ci.yml'], /image: gemini-2\.0-flash/);
    // Untargeted workflow: no deprecated model -> byte-identical.
    const untouched = [
      'name: CI',
      'on: [push]',
      'jobs:',
      '  build:',
      '    runs-on: ubuntu-latest',
      '',
    ].join('\n');
    const r2 = runTool({
      html: htmlFor(SAFE),
      files: {'.github/workflows/ci.yml': untouched},
    });
    assert.equal(r2.files['.github/workflows/ci.yml'], untouched);
    // Injection payload targeting the workflow -> fail-closed, byte-identical.
    const payload =
      'gemini-2.0-flash\n' +
      '  evil-job:\n' +
      '    runs-on: ubuntu-latest\n' +
      '    steps:\n' +
      '      - run: echo WS1B-YAML-PWNED';
    const r3 = runTool({
      html: htmlFor(payload),
      files: {'.github/workflows/ci.yml': workflow},
    });
    assert.equal(
      r3.files['.github/workflows/ci.yml'],
      workflow,
      `injected workflow must remain byte-identical:\n${r3.files['.github/workflows/ci.yml']}`,
    );
  });

  it('dot:true keeps hidden files/dirs in scope (documented current behavior)', () => {
    const files = {'.ng-dev/models.ts': "const m = 'gemini-1.5-pro';\n"};
    const r = runTool({html: htmlFor(SAFE), files});
    assert.equal(r.exit, 0);
    assert.match(r.files['.ng-dev/models.ts'], /gemini-2\.0-flash/);
  });
});

describe('update-models rewrite tool — 5) rewritten TS must remain syntactically safe', () => {
  it('rewritten TS passes node --check', () => {
    const files = {
      'models.ts':
        "const MODEL = 'gemini-1.5-pro';\n" +
        'export function isDeprecated(m: string): boolean {\n' +
        "  return m === MODEL;\n" +
        '}\n',
    };
    const r = runTool({html: htmlFor('gemini-2.0-flash'), files});
    assert.equal(r.exit, 0);
    assert.match(r.files['models.ts'], /gemini-2\.0-flash/);
    const dir = mkdtempSync(path.join(tmpdir(), 'ws1b-syntax-'));
    try {
      const rewritten = path.join(dir, 'models.ts');
      writeFileSync(rewritten, r.files['models.ts']);
      const res = spawnSync(process.execPath, ['--check', rewritten], {encoding: 'utf-8'});
      assert.equal(res.status, 0, `node --check must pass on rewritten TS:\n${res.stderr}`);
    } finally {
      rmSync(dir, {recursive: true, force: true});
    }
  });

  it('rewritten TS passes tsc --noEmit when a tsc binary is provided (TSC_BIN)', () => {
    const tscBin = process.env.TSC_BIN;
    if (!tscBin) {
      // eslint-disable-next-line no-console
      console.log('[ws1b] TSC_BIN not set — tsc leg skipped. Use the repo-native tsc via bazel ' +
        '(//.github/local-actions/update-models:test) or `npx -p typescript tsc --noEmit`.');
      return;
    }
    const files = {
      'models.ts':
        "const MODEL: string = 'gemini-1.5-pro';\n" +
        'export function isDeprecated(m: string): boolean {\n' +
        '  return m === MODEL;\n' +
        '}\n',
    };
    const r = runTool({html: htmlFor('gemini-2.0-flash'), files});
    assert.equal(r.exit, 0);
    const dir = mkdtempSync(path.join(tmpdir(), 'ws1b-tsc-'));
    try {
      const rewritten = path.join(dir, 'models.ts');
      writeFileSync(rewritten, r.files['models.ts']);
      const res = spawnSync(tscBin, ['--noEmit', '--skipLibCheck', rewritten], {encoding: 'utf-8'});
      assert.equal(res.status, 0, `tsc --noEmit must pass on rewritten TS:\n${res.stdout}${res.stderr}`);
    } finally {
      rmSync(dir, {recursive: true, force: true});
    }
  });
});

/**
 * In-repo wiring (BUILD.bazel jasmine_test pattern) — port `ws1b.spec.mjs` to
 * `.github/local-actions/update-models/test/update-models.spec.ts` following repo convention:

   load("//tools:defaults.bzl", "jasmine_test", "ts_project")

   ts_project(
       name = "test_lib",
       testonly = True,
       srcs = glob(["test/*.ts"]),
       tsconfig = "//.github/local-actions:tsconfig",
       deps = [
           "//.github/local-actions/update-models:node_modules/@actions/core",
           "//.github/local-actions/update-models:node_modules/@types/jasmine",
           "//.github/local-actions/update-models:node_modules/@types/node",
           "//.github/local-actions/update-models:lib",
       ],
   )

   jasmine_test(
       name = "test",
       data = [
           ":test_lib",
           ":main",          # the deployed bundle under test
           "//.github/local-actions/update-models:test_fixtures",  # scratch fixtures
       ],
   )

   bazel test //.github/local-actions/update-models:test

 * Notes for the operator:
 *  - Add "@types/jasmine" to .github/local-actions/update-models/package.json (the local-actions
 *    tsconfig already declares types: ["node", "jasmine"]).
 *  - The jasmine port keeps the same assertions; the child-process harness (spawnSync + fetch
 *    preload + scratch fixtures under $(mktemp)) is portable as-is. Fixture data can also be
 *    declared as ts_project data files if hermeticity is preferred.
 */
