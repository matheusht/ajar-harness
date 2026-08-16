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

