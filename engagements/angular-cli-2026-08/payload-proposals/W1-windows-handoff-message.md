All bundle artifacts verified on disk. Here is the **W1 Windows-run operator handoff**.

---

## HANDOFF — W1 Windows E2E (closes the single evidence-grade rung)

**Artifact:** `engagements/angular-cli-2026-08/payload-proposals/W1-windows-runbundle/RUN-BUNDLE.md` (self-contained: `registry-server.cjs` + `malrepo` fixtures + `run-e2e.ps1` + `expected-markers.md` + `result-report-template.md`) + the full workspace fixture at `.../runbundle/ws2/` (angular.json + `projects/demo/`). All anchors re-verified at pin `d827ba9005` (host.ts:150-157 win32 joined-string `shell:true`; factory.ts:99-107 yarn-classic major<2; add/cli.ts:221 fetch BEFORE :227 confirmation).

### What to run (operator-owned Windows host — method-2 local, **no wire trip**)

1. **Preconditions** (all must hold or the run is INVALID, not negative):
   - Windows host (any 10/11/Server); Node ≥18; PowerShell 5+.
   - **yarn 1.x on PATH — `yarn --version` must print a 1.x value.** Yarn 2+ silently disables the value path (yarn-modern) → invalid run. Corepack: if yarn isn't installed, use `npm i -g yarn` (installs 1.x) and do NOT let corepack intercept.
   - CLI: build from the pin source (`d827ba9005b86b23d05ee7c62c0823367aa245c1`) OR note in the result that a released (post-pin) CLI was used — the injection-shape lines are pin-verified, so a post-pin CLI weakens the "at the pin" claim.
2. **Extract** the bundle + `ws2/` fixture into a clean dir (e.g. `C:\w1e2e\`).
3. **Start the registry stub:** `node registry-server.cjs 4873` (default = malicious `dist-tags.latest = '1.0.0" & echo PWNED > %TEMP%\w1-poc & "'`; `benign` arg = negative control).
4. **Run the trigger** (from the fixture dir): `powershell -ExecutionPolicy Bypass -File run-e2e.ps1` — it checks `yarn --version`, runs `ng add w1-poc-pkg --skip-confirmation`, checks the marker, stops the registry. (`--skip-confirmation` only skips the install gate; the injection fires in the metadata fetch BEFORE it — the script comments say so.)
5. **Check the markers** (expected-markers.md, 8 items): `GET /w1-poc-pkg` in the registry log · **`%TEMP%\w1-poc` EXISTS** · marker appeared BEFORE install/confirmation output · prompt shows the tag NAME (`w1-poc-pkg@latest`), not the value.
6. **Negative controls:** A — restart the registry with `benign`, re-run → marker ABSENT. B — same fixture on Linux/macOS → marker ABSENT (array-spawn). C (optional, manager-independent update path) — `.npmrc`-redirected repo + `ng update w1-poc-pkg@latest` → marker PRESENT.

### What to send back (fill `result-report-template.md`)

- Host OS/version, node version, **yarn version**, CLI build (pin / released).
- Registry mode (MALICIOUS/BENIGN) · marker present? (YES/NO, path) · **marker appeared pre-confirmation?** · install trail order · the exact `ng add` prompt line (paste) · registry-log excerpt (the `GET` lines) · negative-control results A/B/C · cleanup confirmation (marker deleted, registry stopped).
- Verdict line: `EXECUTION-OBSERVED` / `BLOCKED (<exact reason>)`.

### Triage paths (what each outcome means)

| Outcome | Meaning | Action |
|---|---|---|
| **EXECUTION-OBSERVED** (marker pre-confirmation; negatives A/B clean; C optional) | W1 rung CLOSED — the chain is execution-confirmed; the CI-token venue (fork-PR → cmd.exe inherits GITHUB_TOKEN/ACTIONS_RUNTIME_TOKEN/OIDC, source-verified) upgrades to execution-confirmed | W1 filing upgrades from static-only to demonstrated; record `attempt-w1-004-exec` in the kernel; update the W1 REPORT staleness section + FILING-COVER |
| **Marker ABSENT on a VALID run** (yarn 1.x confirmed, `GET /w1-poc-pkg` logged, correct CLI) | Genuine anomaly — mechanism did not fire on that Windows variant (cmd escaping differences, quote-wrap behavior) | **Do not file as-is** — return the full env + log; opens a kill-pair hypothesis on the win32 quote-wrap escaping; W1 claim re-scope decision |
| **INVALID RUN** (yarn 2+, no GET logged, wrong CLI, registry not reachable) | Precondition failure, NOT a negative | Re-run with the checklist; no record impact |
| **Marker PRESENT but AFTER the install trail** | Fires but post-gate — the pre-gate timing claim is the one to verify | Still a finding; adjust the ordering claim + note; send the sequence evidence |
| **Benign control ALSO fires** (marker in negative A) | Fixture defect (registry stub or fs interaction), not a W1 result | Hold; report; the parent debugs the stub before any verdict |

**Boundary note:** this run is method-2 local (an operator-owned machine; no wire) — no fresh confirmation needed. The only operator-gated wire act remains the private-fork CI demo (`payload-proposals/chain2-wire2-spec.md`). The dir also still holds the N1-C blind-harness leftovers (`guide-instr-*.md`, `tool-output.txt`, `VERDICT.md`) — harmless, moved to `/tmp/n1c-separate/` at closure.

---

```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "Read payload-proposals/W1-windows-runbundle/RUN-BUNDLE.md in full (167 lines: registry-server.cjs with malicious/benign modes + 404-fast poisoned-URL behavior, malrepo fixtures, run-e2e.ps1 with preconditions + marker check + cleanup, expected-markers.md 8-item checklist, result-report-template.md) and verified on disk: RUN-BUNDLE.md, ws/ + ws2/ fixtures (angular.json + projects/demo/src/main.ts), plus the N2A corrections (npm-E404 and corepack/yarn-1 notes, 2 matches) applied. Produced the exact operator handoff: what to run (preconditions incl. yarn-1 rule + pin-source CLI caveat; registry stub + run-e2e.ps1 + 8 markers + negatives A/B/C), what to send back (result-report-template fields incl. prompt line + registry log + versions + cleanup), and 5 triage paths (EXECUTION-OBSERVED / ABSENT-on-valid-run / INVALID-run / post-gate / benign-fires) with per-path actions incl. the attempt-w1-004-exec recording and the no-wire boundary statement."
    }
  ],
  "changedFiles": [],
  "testsAddedOrUpdated": [],
  "commandsRun": [
    {
      "command": "find payload-proposals/W1-windows-runbundle -type f + head RUN-BUNDLE.md + sed -n '80,167p' RUN-BUNDLE.md",
      "result": "passed",
      "summary": "bundle contents verified: RUN-BUNDLE.md self-contained (server script, fixtures, ps1, markers, template), ws2 full fixture present, blind-harness leftovers identified"
    },
    {
      "command": "grep -ci 'E404|corepack|yarn 1' RUN-BUNDLE.md + find ws/ ws2/",
      "result": "passed",
      "summary": "N2A operational corrections present (2 matches); ws2 fixture complete (angular.json + projects/demo)"
    }
  ],
  "validationOutput": [
    "Handoff message covers: preconditions (yarn 1.x mandatory — invalid-run rule; pin-source CLI caveat), run steps (registry stub -> run-e2e.ps1 -> 8 markers -> negatives A/B/C), return payload (template fields: versions, mode, marker, ordering, prompt line, log excerpt, cleanup), and 5 triage paths with concrete actions"
  ],
  "residualRisks": [
    "Physical Windows execution still required — the operator must supply the host (no Windows layer in-lab)",
    "run-e2e.ps1 / expected-markers.md / result-report-template.md exist only inline inside RUN-BUNDLE.md (not split into separate files) — the operator extracts from the doc or the parent splits them first",
    "A released (post-pin) CLI weakens the at-the-pin claim if the pin-source build is not used"
  ],
  "noStagedFiles": true,
  "diffSummary": "Read-only handoff lane: no engagement files modified; the complete operator handoff message (run / return / triage) returned inline",
  "reviewFindings": [
    "no blockers: bundle verified complete and self-contained; pre-gate ordering anchors (:221/:227) re-confirmed; the five triage paths cover every run outcome",
    "note: the dir holds N1-C blind-harness leftovers (guide-instr-*.md, tool-output.txt, VERDICT.md) — mislabeled but harmless; already cleanup-listed (moved to /tmp/n1c-separate/)"
  ],
  "manualNotes": "The parent may optionally split run-e2e.ps1 / expected-markers.md / result-report-template.md into separate files in the runbundle dir for the operator's convenience; not required for the handoff."
}
```
