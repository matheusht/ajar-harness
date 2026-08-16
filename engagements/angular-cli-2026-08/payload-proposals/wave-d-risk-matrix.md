# NEXT-PHASE RISK MATRIX — angular-cli-2026-08, chainstorm Wave D input (planner, read-only)

Scope: the next deeper escalation phase's planned lanes (per plan.md §13(c) residue list + Wave-B outcomes).
Risk classes: **BF** = build failure · **EB** = environment block · **GR** = gate rejection · **WG** = wire-gate (operator-gated / out-of-lab).
Each row: planned lane → top risks → mitigation → overall exposure.

| # | Planned lane | Risk class | Specific risks | Mitigation | Exposure |
|---|---|---|---|---|---|
| N1 | **W1 Windows E2E** (run WINDOWS-E2E-FIXTURE.md on a Windows host; closes the cmd.exe execution rung AND the C2D CI-token venue) | EB, WG | **EB:** no Windows layer in-lab (no wine/qemu/Windows VM; Docker is Linux-only — verified) — the fixture cannot run here; **WG:** any remote Windows runner is a third-party system (scope §9 wires); **GR:** if filed with the execution rung open, a triager may demand the run | Split the rung: (a) operator-run fixture on any local Windows host (no wires) — the primary path; (b) static-only argument already complete in the REPORT (3-hop walkthrough + trigger ordering) as the fallback; (c) keep the CI-token venue as a conditional amplifier until the run lands | **HIGH (EB is absolute in-lab)** — mitigation = operator-host path |
| N2 | **Wire-2 CI demo (Chain 2)** — private-repo Actions run on macOS proving the case-guard root-delete + config-as-data purge | WG, GR | **WG:** fresh operator confirmation required AT THE ACT (documented contract); runner billing/isolation/ephemerality semantics unobservable in-lab; **GR:** a demo that uses the org's own CI resources without cleanup = policy violation | Wire-2 spec is written (payload-proposals/chain2-wire2-spec.md): private fork repo, macOS runner, no secrets, full cleanup ledger; run ONLY on operator sign-off; in-lab fallback = the c2shape demo already demonstrates 3/3 hops with compiled modules | **HIGH (WG)** — gated by a single operator decision |
| N3 | **Real desktop-client chain demo (Chain 3 closing branch)** — an actual shell-less MCP client following the steered instruction | EB, WG, GR | **EB:** no desktop client in the lab; **WG:** installing Claude/ChatGPT desktop + wiring the MCP server = third-party system contact; **GR:** the H2 follow estimate is self-assessed (INT2) — a reviewer may reject it as non-evidence; the blind test (M2POC) showed CONDITIONAL-FOLLOW (agent must decide to follow; splits on the tsConfig cross-check) | Keep the claim scoped: mechanical chain LIVE (steering-demo/), H2 = estimated-follow with the honest limitation stated; the closing branches are (a) an unprepared-agent in-lab harness run (no third-party systems — the pi runtime is local) or (b) documented deployment evidence; do NOT promote the shell-less trigger beyond armed-but-unconfirmed until one closes | **MEDIUM** (mechanism live; only the agent-follow hop is open) |
| N4 | **E1-C1 legacy-SSR venue E2E** — full legacy server-bundle build with malicious locale content executing in a real SSR server | BF, GR | **BF:** full `ng build` webpack E2E was never spun up in-lab (the venue proof used compiled modules + a replicated server bundle — ssr-venue/ demo); a full build could surface unrelated toolchain failures; **GR (record drift, FOUND):** the E1-C1 REPORT is internally inconsistent — front-matter (line 5) still says "HIGH (legacy-SSR venue)" while the venue-split section (line 45) says MEDIUM 6.3 after the Wave-B ECKP correction; gates still pass (G5 reads finding.json, which carries the browser vector) but a filing reviewer will flag the contradiction | Fix the front-matter line to match the 6.3 correction BEFORE filing (one-line edit); the ssr-venue/ runtime demo (server-main.js, ATTACKER-EXEC marker, benign negative) is the venue evidence without a full build; a full-build E2E is optional hardening, not a prerequisite | **MEDIUM** (record drift = immediate fix; build E2E = optional) |
| N5 | **D3 filing timing** — file now per the #33632 co-discovery window analysis; delta-first writeup (quantified robot-budget first) | GR, WG | **GR:** the delta-first draft (D3-filing-draft.md) must open with the quantified budget consumption (7-10 + AI-key per issue event; per-INSTALLATION org-wide budget; S1 120% / S5 200% exceed) and cite #33632; a mechanism-first writeup risks doctrine dismissal; **GR:** fix-sweep staleness — if the components fix (#33632) is swept into angular-cli before filing, the guard sub-claim becomes historical; **WG:** filing is operator-only by contract | Draft is prepared (payload-proposals/D3-filing-draft.md); the window analysis (D3ME) says file BEFORE the next operator session; re-check #33632 status at filing time; the E12-correction + cash-burn sub-claim survive independently of the token-budget math | **MEDIUM** (time-sensitive, not build-blocked) |
| N6 | **Current-main re-verification for M3 + E1-C1** — post-pin fixes: bd413b0eb/#33312 (M3 write path), #33859/#33866 (E1-C1 i18n inliner refactors) | EB, BF, GR | **EB:** no wire access — current main is UNOBSERVABLE in-lab; re-verification requires a fresh pin update (operator) or web access; **BF:** re-pinning the upstream clone + rebuilding risks the same Java-downloader timeout as before (distdir workaround needed); **GR:** filing M3/E1-C1 against a stale pin while main may already contain the fixes would be a credibility failure | The pin's state is fully documented (delete-path + case-guard + SSR venue verified AT the pin); the filing must state "verified at pin d827ba9005; main-state unverified in-lab" OR the operator updates the pin first; the distdir workaround is recorded in the lab script | **HIGH (EB)** — operator decision: fresh pin vs filing-with-stale-pin-statement |
| N7 | **Chain 5 watch-list (5 triggers)** — dev-infra action file-read; new fork-guard pattern uses; concurrency additions; robot-key scope changes; #33632 resolution | EB, GR | **EB:** the watch-list needs periodic web/API checks (no wire in-lab) — it is a standing process, not a one-shot lane; **GR:** D3's forward-condition claim must stay future-conditional (the file-read precondition is verified ABSENT at the pin) | The 5 triggers are enumerated in the D3 REPORT + C5D; watch-list maintenance is operator-side (or a scheduled web lane when wires are allowed); no finding change is needed until a trigger fires | **LOW** (process, not deliverable) |
| N8 | **Operator severity decisions** — E1-C1 venue-split record (6.3 vs 8.1 calculator-variant vs separate finding), W1 CI-variant severity (Medium?), C2D Actions-minute-burn quantification | GR | **GR:** inconsistent severity records between REPORT/finding.json/payloads are the #1 reviewer-visible defect class (the E1-C1 front-matter line is a live example); the 7.3 vs 6.3 vs 8.1 spread across rounds.md/plan.md §12/REPORT must be reconciled | One consolidated severity decision sheet per finding before filing; the 6.3 vector (AV:L/AC:H/PR:N/UI:R/S:U/C:H/I:H/A:H) is the Wave-B kill-pair recommendation; the 8.1 (AV:N/UI:N) is recorded as a calculator variant for the operator to choose; finding.json stays the source of truth for gates | **MEDIUM** (record discipline) |
| N9 | **Chain matrix maintenance** — re-verify plan.md §12 rows vs Wave D outcomes; keep the per-shape capability table (composite-as-single-scenario remains killed) | GR | **GR:** stale matrix cells (a §12 row still reading a pre-Wave-D verdict) are record-drift; the INT6/KP-INT over-claim discipline must persist (X4 single-scenario = killed) | Matrix updates happen at each round funnel (established pattern); the per-shape table is the honest artifact; no new composite claims without their kill-pair | **LOW** |
| N10 | **Per-finding filing package finalization** — M3+D2 one-family report (M3FD recommendation), M2 residual file-as-is (M2FD), W1 delta-first opening (W1FD), E1-C1 members E+F (baseHref member F demo pending) | BF, GR | **BF:** member F's compiled demo (augment-index-html emitRaw) was recommended but not yet built — build it before filing E1-C1 (esbuild-bundle + malicious baseHref → emitted index.html); **GR:** the M3+D2 one-report merge must not double-count (M3RV verified lane-consistent; the case-guard is M3-only, the CI-wipe is D2-primary) | Build the member-F demo in the next round (bundling pattern is established); follow the M3FD composition (one family report, both Medium); the filing openings are drafted (payload-proposals/D1-filing-opening.md, E1C1-filing-openings.md, W1 venue-split block in REPORT) | **MEDIUM** (one build item, one composition discipline) |

## Cross-cutting risk summary

1. **Environment blocks are the dominant class** (N1 absolute, N6 high) — both resolve to OPERATOR actions (a local Windows host; a fresh pin), not to more lab work.
2. **Wire-gates (N2, N3, N6) are the second class** — every one has a documented in-lab fallback or a written spec; none is silently bypassable, and none should be (contract).
3. **Gate rejection via record drift is the only fully agent-side risk** (N4, N8) — the E1-C1 front-matter vs section severity contradiction is LIVE and must be fixed before any filing; the 7.3/6.3/8.1 spread across records must be reconciled on one decision sheet.
4. **No planned lane has an unmitigated build-failure risk** — the bundling pattern (tree esbuild + compiled modules) is proven across ~15 PoCs this session; full-build E2Es are optional hardening, never prerequisites.
5. **The single highest-risk artifact remains W1's execution rung** (N1) — every other lane's risk is medium-or-lower because its evidence is already on file.

## Acceptance notes

- Risk classes verified against the current environment (node v25.9.0, tree esbuild present, NO wine/Windows layer, deepsec target workspace present, wire-2 operator-gated in the records).
- The E1-C1 front-matter HIGH vs section MEDIUM 6.3 contradiction is a NEW record-level finding surfaced by this planner (findings/E1-C1-i18n-locale-key-escape/REPORT.md:5 vs :45) — fix before filing.
- No files modified (read-only planner lane); no commands beyond inspection.

```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "Risk matrix returned for 10 planned next-phase lanes (N1-N10) with per-lane risk classes (BF/EB/GR/WG), specific risks, mitigations, and overall exposure, grounded in: plan.md §13(c) residue list (read), the chain verdicts (rounds.md E2-R1..R10 rows), Wave B outcomes (E2-B parts 1-3), and live environment checks (node v25.9.0; tree esbuild present; NO wine/Windows layer — absolute EB for N1; wire-2 operator-gated items confirmed on file). New record-level finding surfaced: E1-C1 REPORT.md:5 front-matter 'HIGH (legacy-SSR venue)' contradicts the :45 venue-split section 'MEDIUM 6.3' (Wave-B ECKP correction) — flagged under N4/N8 as a live gate-rejection risk with the one-line fix."
    }
  ],
  "changedFiles": [],
  "testsAddedOrUpdated": [],
  "commandsRun": [
    {
      "command": "node --version + ls upstream/angular-cli/node_modules/.bin/esbuild + which wine/wine64 + ls /tmp/deepsec-scan-cli/angular-cli",
      "result": "passed",
      "summary": "node v25.9.0, esbuild present, no wine/Windows layer, deepsec target workspace present — the EB/WG grounding for N1/N2/N6"
    },
    {
      "command": "grep plan.md §13(c) residue list + rounds.md E2 rows + findings/E1-C1 REPORT severity lines",
      "result": "passed",
      "summary": "10 planned lanes enumerated from the residue list; the E1-C1 front-matter-vs-section severity contradiction verified on file (lines 5 and 45)"
    }
  ],
  "validationOutput": [
    "Risk classes verified against the actual environment and records; environment blocks (N1 absolute, N6 high) dominate and both resolve to operator actions; wire-gates (N2/N3/N6) all have documented in-lab fallbacks; the only fully agent-side risk is record drift (N4/N8) with one LIVE example (E1-C1 severity lines); no planned lane has an unmitigated build failure — the compiled-module bundling pattern is proven across the session's PoCs"
  ],
  "residualRisks": [
    "The E1-C1 front-matter severity line (:5) must be reconciled with the section (:45) before filing — the gates pass regardless (G5 reads finding.json), so this is a filing-review risk, not a gate risk",
    "W1's execution rung stays environment-blocked; the operator-host Windows path is the only way to close it",
    "Current-main states for M3/E1-C1 are unobservable without a wire or a fresh pin — the stale-pin statement must be explicit in any filing until the operator updates it",
    "Member F (baseHref emitRaw) compiled demo not yet built — scheduled for the next round before the E1-C1 filing"
  ],
  "noStagedFiles": true,
  "diffSummary": "Read-only planner lane: risk matrix for the next escalation phase returned inline; no engagement files modified",
  "reviewFindings": [
    "no blockers",
    "info: the E1-C1 front-matter severity line (REPORT.md:5) still reads HIGH while the venue-split section (:45) reads MEDIUM 6.3 after the Wave-B correction — one-line fix, apply before filing",
    "info: all wire-gated lanes (N2 wire-2 CI demo, N3 desktop-client demo, N6 current-main re-verification) have documented in-lab fallbacks or operator paths — none blocked agent-side",
    "info: the M3+D2 one-family-report merge (M3FD) is lane-consistent (M3RV: no double-counting; case-guard M3-only, CI-wipe D2-primary)"
  ],
  "manualNotes": "Wave D planner output. The matrix is the input for the D-R1 next-phase plan: N4's one-line E1-C1 severity fix and N10's member-F demo are the two agent-buildable items; N1/N2/N6 are operator-gated by nature; N5 (D3 filing) is time-sensitive. Recommendation: apply the E1-C1 severity-line fix and build the member-F demo in the first D-R2 execution round."
}
```
