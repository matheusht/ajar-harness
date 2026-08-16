## N-J — W1 CI-variant filing brief (fork-PR CI-token venue)

**Component of the W1 filing: the CI venue, one mechanism, two entry paths, one honest gap.**

**Venue summary.** A fork PR to a repo whose CI runs `ng add`/`ng update` on a `windows-latest` runner (e2e/scaffolding jobs, boilerplate/sample repos) carries the malicious `.yarnrc`/`.npmrc` in the checkout — a **silent registry redirect with no validation** (PM-native precedence; `ng update` has no registry flag at all). The metadata fetch fires the injection **before any confirmation** (add path: `loadPackageInfoTask` at add/cli.ts:221 precedes `confirmInstallationTask` at :227 — the non-TTY abort never prevents the already-executed fetch; update path: no confirmation gate exists). The injected cmd.exe runs under the ng CLI process env (`host.ts:150-165`: `{...process.env, ...options.env}` + win32 joined-string `shell:true`), so it inherits the workflow step env.

**Token inventory (verified, E2-R7/KP-W1 precision).** On a fork-PR-triggered `pull_request` job: **read-scoped `GITHUB_TOKEN`** (repo default permissions — code read, issue/PR ops the repo grants), **`ACTIONS_RUNTIME_TOKEN`/`ACTIONS_RUNTIME_URL`** (always present — artifacts/caches), and **`ACTIONS_ID_TOKEN_REQUEST_TOKEN`/`URL`** when the job has `permissions: id-token: write` (OIDC → short-lived cloud-provider token). Arbitrary repo secrets (incl. the robot key) are **not** in the step env unless explicitly mapped (the robot key stays in-process in the action — C5A). Exfil path: the attacker registry server (outbound HTTP default-allowed).

**Severity.** Fork-PR CI venue: `AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H` — **no user interaction** (attacker-triggered via PR), 8.1 base by the UI:N delta; **conditional High** when the ID-token/OIDC branch is present. Dev-machine venue unchanged (CVSS 7.5, filed Low-Medium under the maintainer won't-fix doctrine — #32509/#32892 citations stay visible; the opening leads with the zero-interaction delta).

**Shape.** Primary attacker-triggered venue: e2e/scaffolding CI jobs running `ng new`/`ng add` on PR content (real in boilerplate/sample repos and framework e2e suites). General app repos running `ng update` on PR checkouts are rarer but real; dependency-update **bot** runs are a different attacker model (bot token, not fork-triggered) and are excluded. Bounds: yarn-classic-only on the `ng add` metadata-fetch path; the `ng update` path is **manager-independent** (npm default — `getRegistryManifest` is the generic method, `npm view --json` on win32); numeric runner-version paths semver-bounded; POSIX array-spawn safe; `ng update` without packages does not fire.

**Execution rung (the one gap).** Physical cmd.exe execution is **environment-blocked** (no Windows host in-lab). Mechanism hops are all source-verified; the W1 run bundle (`payload-proposals/W1-windows-runbundle/`: registry stub + `run-e2e.ps1` + expected markers + result template — operator-ready, method-2 local) and the wire-2 private-repo CI demo (operator-gated) close it. **Filing decision (operator):** the CI venue files as part of W1 (amplifier framing) or as a separate entry — the brief supports either; the recommended sequence keeps W1 first (attacker-triggered, secret-bearing env).

```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "N-J W1 CI-variant filing brief produced (~430 words) sourced entirely from the on-file W1 REPORT CHAINSTORM AMPLIFIER + WAVE-B PRECISION ADDITIONS sections (verified via sed): venue summary (pre-gate ordering add/cli.ts:221/227, env inheritance host.ts:150-165), token inventory (read-scoped GITHUB_TOKEN, runtime tokens, OIDC condition), severity (8.1 (HIGH, UI:N — per the harness calculator; supersedes the earlier 5.6 figure) base, conditional High, doctrine citations), shape + bounds (e2e/scaffolding primary, bot-excluded, yarn-classic add vs manager-independent update), execution-rung status (environment-blocked; run bundle + wire-2 path named). No scope widened; read-only lane, no files modified."
    }
  ],
  "changedFiles": [],
  "testsAddedOrUpdated": [],
  "commandsRun": [
    {
      "command": "grep + sed over findings/W1-yarn-classic-disttags-win32/REPORT.md (CHAINSTORM AMPLIFIER + WAVE-B sections)",
      "result": "passed",
      "summary": "All brief facts traced verbatim to the on-file REPORT sections (ordering anchors, token inventory, severity vector, shape/bounds, execution-rung status)"
    }
  ],
  "validationOutput": [
    "Brief under the 500-word cap (~430 words); delta-first opening consistent with the doctrine section; every claim carries its on-file source anchor"
  ],
  "residualRisks": [
    "Execution rung remains environment-blocked (no Windows host) — the brief states this as the single gap; the wire-2 private-repo demo remains operator-gated",
    "Live org CI-shape prevalence not measured (no wire access) — the e2e/scaffolding shape is documented as the primary venue from repo-pattern analysis"
  ],
  "noStagedFiles": true,
  "diffSummary": "No files modified — read-only records-writer lane; the brief is returned inline for the parent to drop into the W1 filing bundle (payload-proposals/)",
  "reviewFindings": [
    "no blockers: brief facts all resolve against the W1 REPORT; severity framing consistent with KP-W1/W1-FD; the operator decides the file-as-part-vs-separate-entry question"
  ],
  "manualNotes": "Parent: save to payload-proposals/W1-CI-variant-brief.md; pair with the W1-windows-runbundle/ operator package when the operator runs the E2E."
}
```
