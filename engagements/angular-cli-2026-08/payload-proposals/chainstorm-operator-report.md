I have the skeleton + all D-R2/D-R3 outcomes. Composing the final report:

# CHAINSTORM PHASE — OPERATOR REPORT

*Engagement: angular-cli-2026-08 · Phase: E2 chainstorm · 2026-08-15 · 164 subagent slots executed (Wave A 80 + Wave B 36 + Wave D D-R1..D-R3 48) · Kernel: 63 events · Zero wire trips*

## 1. The chains — what one malicious repo now buys an attacker

We asked whether our seven findings compose into kill chains. Five did. All were adversarially kill-paired before anything was recorded; the composite-as-single-scenario framing was killed; what survived is per-shape and per-finding-scoped.

| Chain | Verdict | The claim, in one line |
|---|---|---|
| **C1** cloned-repo delivery (W1+M3+D2+E1-C1+D1) | **CONFIRMED** — fixture 9/9 both modes, real commands | A repo with a `.yarnrc`/`.npmrc` + a malicious `angular.json` silently redirects the registry and delivers win32 RCE (execution-pending), workspace deletion, cache purge, file writes, and injected product code — **invisible during execution** (`ng cache clean` prints nothing; delete/write sites have no output). |
| **C2** CI sabotage | **NARROWED-SURVIVES** — config-as-data shape demonstrated in-lab | A fork PR's config values, processed by a trusted CI that builds without running install scripts, wipe/delete/write on the runner; macOS runners make the M3 case-guard **root-delete of the checkout** reachable (C2B verified). General fork-PR shape killed (install scripts are already code-exec). Wire-2 demo operator-gated. |
| **C3** MCP agent steering (repo content → M2 priority-0.9 → run_target option-values → exfil) | **ARMED-WITH-ESTIMATED-FOLLOW** | Steering chain **demonstrated with real modules**; the real-agent follow was scored MEDIUM-HIGH; closing branch = a live desktop-client chain demo. Shell-less trigger documented (armed-but-unconfirmed). |
| **C4** browser supply chain (E1-C1 member C) | **CONFIRMED** venue-restricted | Attacker locale-data module ships in the production bundle **and executes in the legacy-SSR server process** (runtime demo, negative clean); dependency-confusion variant live-verified; NOVEL. |
| **C5** D3 forward (robot-key exposure) | **FUTURE-CONDITIONAL** | No key-exfiltration primitive today (zero fs-ops in the action); the guard defect is **unfixed at main** and publicly co-discovered (**components #33632** open, **#33653** pending class-fix) — filing urgency. |

## 2. Findings deltas (what changed this phase)

| Finding | Delta added | Severity now |
|---|---|---|
| **W1** | version-check venue (cli-version.ts:63, every `ng update`) · package.json poisoning (updateDependencies) · **manager-independent update path** · **fork-PR CI-token RCE** (env inheritance: read-scoped GITHUB_TOKEN, ACTIONS_RUNTIME_TOKEN, OIDC id-token) | Low-Med (dev) · **CI-variant 5.6 UI:N, conditional High w/ OIDC — operator decides** |
| **M3** | case-guard root-delete (verified) · extract-i18n write amp · prerender route-escape amp · #32873 disclosed-but-unfixed + #33312 follow-up cited · **delete path + case-guard byte-identical at CURRENT main** | **Medium** |
| **D2** | Chain-1/2 keystone hop (purge fires unconditionally on every default build) · CI full-checkout wipe demonstrated | **Medium** |
| **D1** | SSR runtime execution **demonstrated** (comma-exec at request time; boot-time module-eval timing corrected) · app-trust scoping | Low-Med |
| **E1-C1** | members E (translation-path read) + **F (baseHref → script tag in production index.html, demonstrated)** · SSR venue **runtime-demonstrated** · **severity reconciled: browser 4.0 / legacy-SSR MEDIUM 6.3** (AV:L/AC:H/PR:N/UI:R/S:U/C:H/I:H/A:H) | Low-Med / **Medium 6.3** |
| **M2** | steering chain demonstrated · trigger armed-but-unconfirmed | Low-Med |
| **D3** | budget numbers corrected (issue_labels 7-10+AI-key, labels 8-12) · **single coordinated attacker EXCEEDS the 5,000/hr org-wide budget (S1 120%, S5 200%)** · cash-burn sub-claim survives · #33632/#33653 | Low |

## 3. Filing recommendations (sequence + package)

1. **E1-C1** (venue-split 6.3 + member F — the strongest delta-first filing) and **W1 CI-token** (zero-interaction delta; keep #32509/#32892 doctrine citation visible) — the severity leads, first.
2. **M3+D2 as ONE family report** (Wave-B recommendation: case-guard M3-only, CI-wipe D2-primary).
3. **M2 residual** — file-as-is, chain as context.
4. **D3 — not deferred past the next operator session** (window analysis: the components class-fix #33653 is pending).
5. **D1** — after the leads; REJECTED-doctrine family cited.
6. **Novelty matrix**: C1/C4 NOVEL · C2/C3/C5 NEAR-MISS; cite the foxllb cluster (#33073-#33077, now 5) everywhere config-trust applies.

## 4. Next phase (angular-cli-next-v1.md, launched) — the confirmed residue

1. **W1 Windows E2E** — the single highest-value artifact (closes the execution rung; makes the CI-token venue execution-confirmed).
2. **Wire-2 CI demo** (Chain 2, operator-gated: private-fork macOS runner).
3. **Real desktop-client chain demo** (Chain 3 closing branch — ARMED→CONFIRMED).
4. **E1-C1 legacy-SSR full-app E2E** (venue-split closing evidence).
5. **Current-main re-verification — DONE in D-R2** (M3 delete path + case-guard byte-identical at main; E1-C1 i18n-options unchanged; D3 guard unfixed) — retire that residue item.
6. **Chain 5 watch-list** (5 triggers; track #33632/#33653 resolution).
7. N-rounds N1..N8 + 14 lanes bootstrapped (plan.md §15).

## 5. Your action list

1. **File** (sequence above; humanized drafts + delta-first openings + filing packages ready in `payload-proposals/`; credential scan clean).
2. **W1 Windows fixture run** (WINDOWS-E2E-FIXTURE.md — any Windows host).
3. **Wire-2 private-fork CI demo** (fresh confirmation at the moment of the act).
4. **Desktop-client chain demo** (closing branch) when a client is available.
5. **record-memory** — disposition payload ready (PC-1..PC-17; operator-only command).
6. **Cleanup execution** — ledger ready; **`/tmp/deepsec-scan-cli/opencode-key` is a CREDENTIAL — `rm -P` at closure**.
7. **Stale close-request** `auth-close-cli-2026-08-15` — resolve as superseded; engagement stays OPEN.
8. **E1-C1 finding.json** — optionally record the 6.3 venue vector (report + records reconciled; field still carries the browser vector).

*Bottom line: one repo, five impact planes, four confirmed with in-lab artifacts, zero wire trips. The chains are the filing story — delta-first, per-shape, kill-paired.*

---

```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "Concrete findings with file paths and severity: E1-C1 venue-split 6.3 AV:L/AC:H/PR:N/UI:R/S:U/C:H/I:H/A:H (findings/E1-C1-i18n-locale-key-escape/REPORT.md venue-split section; member F demonstrated at augment-index-html.ts:267-270 emitRaw with compiled demo at payload-proposals/next-phase-demos/nr2-mf/); W1 CI-token venue 5.6 UI:N conditional-High (findings/W1-yarn-classic-disttags-win32/REPORT.md CHAINSTORM AMPLIFIER, host.ts:150-165 env merge); D3 budget correction issue_labels 7-10+AI-key labels 8-12 vs 5,000/hr org-wide with S1 120%/S5 200% exceed (payload-proposals/d3-budget-math/budget-math.mjs); M3 delete path + case-guard byte-identical at current main (D-R2/D-R3 verified); composite harness re-labeled capability-fusion artifact after false-positive marker fix (payload-proposals/chain-demos/README.md). All grounded in plan.md §12/§13/§14/§15, rounds.md E2 rows, kernel events 48-63."
    }
  ],
  "changedFiles": [],
  "testsAddedOrUpdated": [],
  "commandsRun": [
    {
      "command": "read plan.md §12-§15 + rounds.md E2-D1..D3 rows + DR1-15 skeleton + D-R2/D-R3 verdict files",
      "result": "passed",
      "summary": "chain verdicts, per-finding deltas, severity corrections, filing sequence, residue, and operator decisions extracted and cross-checked"
    }
  ],
  "validationOutput": [
    "Report covers the required sections (chains / findings deltas / severity / filing recommendations / next phase / operator actions); every severity figure cross-checked against the on-file verdicts; D-R3 corrections incorporated (composite re-label, D1 boot-time timing, E1-C1 6.3 reconciliation)"
  ],
  "residualRisks": [
    "W1 CI-variant severity remains an operator decision (Medium?) per KP-W1",
    "Chain 2/3 closing rungs remain wire-2 / real-client-gated (declared)",
    "E1-C1 finding.json vector field still carries the browser vector (optional operator update)"
  ],
  "noStagedFiles": true,
  "diffSummary": "Read-only report-writing lane; the report text is returned inline for the parent to save under payload-proposals/chainstorm-operator-report.md",
  "reviewFindings": [
    "no blockers: every claim traces to plan.md §12-§15, rounds.md E2 rows, or the funnel events 48-63",
    "note: the skeleton's 180-slot figure is now 164 executed + D-R4 in flight (Wave D totals 64; the report states 164 executed at writing time)"
  ],
  "manualNotes": "For the parent: save this text to engagements/angular-cli-2026-08/payload-proposals/chainstorm-operator-report.md; D-R4 (the remaining 16 lanes) should verify the report against the records before the phase-terminal event."
}
```
