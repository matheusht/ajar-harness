# NEXT-PHASE TERMINAL — OPERATOR ACTION LIST (2026-08-15, final)

Engagement: angular-cli-2026-08 · Kernel: 72 events · 7 findings (all gates CLEAR) · Campaign: 180 chainstorm + 64 Wave-D + 56 next-phase (N1-N7) subagent slots executed; N8 = this synthesis.

---

## 1. FILE — ordered sequence (all 7 packages READY; delta-first openings on file)

| # | Package | Severity (final) | Key delta / doctrine counter | Ref |
|---|---|---|---|---|
| 1 | **M3+D2 family** | Medium / Medium | DELETE-side miss in a twice-fixed write family; case-guard root-delete (macOS CI); #32873 disclosed-but-unfixed; byte-identical at main (N1H) | `payload-proposals/FILING-SEQUENCE-final.md`; drafts `humanized-M3/D2`; `WB-M3D2-filing-package.md` |
| 2 | **E1-C1** (incl. members E+F) | Low-Med browser / **6.3 Medium legacy-SSR** | SSR server-execution delta (boot-time, N1D real-pipeline E2E) vs the config-trust doctrine; mis-keyed-guard discriminator; CSP caveat (member F) | `E1C1-filing-openings.md`; `E1C1-venue-split-record-brief.md`; evidence/chain4/{ssr-e2e-real,member-e,member-f} |
| 3 | **W1** (incl. CI-token + version-check venues, package.json poisoning) | Low-Med dev / **8.1 HIGH CI-venue (UI:N, harness-calculator; supersedes the earlier 5.6)** | Zero-interaction fork-PR → RCE inheriting CI tokens (read-scoped GITHUB_TOKEN + runtime token + OIDC when granted); version-check = EARLIEST entry point (checkCLIVersion first, N2D); manager-independent update reach | `W1-CI-variant-brief.md`; `W1-filing-package.md`; `W1-windows-runbundle/`; **decide: file the CI venue as a SEPARATE entry (N7A recommended)** |
| 4 | **D3** | Low | Co-discovery race: #33632 OPEN + **#33653 pending class-fix (components)** — the class is being fixed upstream; the angular-cli instance is unfixed at main. **FILE NOW, never deferred past the next operator session.** Lead with quantified org-wide robot-budget degradation (issue_labels 7-10 + AI-key; per-installation 5,000/hr; S1 120% / S5 200% exceed) + cash-burn | `D3-filing-draft.md`; `D3-filing-package.md`; `payload-proposals/d3-budget-math/` |
| 5 | **M2** residual (ancestor-walk) | Low-Med | FILE-NOW; open with the pin re-PoC (MARKER-ATTACKER-GUIDE-2 at the pin; out-of-roots negative rejected); run_target amplifier + C3 chain = CONTEXT ONLY; cite #32766 (OWASP MCP-01, won't-fix doctrine) + the stealth-shape counter (N4C) | `M2-filing-package.md`; M2 REPORT filing section; evidence/steering-demo/shape-B/ |
| 6 | **D1** | Low-Med | Corrected boot-time SSR timing (NOT per-request — over-claim risk); app-trust scoping; comma-exec validity; REJECTED-family framing (#33074/#33076) | `D1-filing-opening.md`; `D1-SSR-timing-correction.md`; `D1-filing-viability.md` |
| 7 | **Chain-context annex** (NOT a filing) | — | C1 narrative for 1-3; C4 = E1-C1 evidence; C3 = M2 context (capability-fusion re-label, DR3-03); C2 = wire-2 spec; C5 = D3 watch-list | `chain-demos/README.md`; plan.md §12 |

**Decision inputs on file:** `N-M-severity-decision-briefs.md` (E1-C1 6.3 vs 8.1 calculator-variant; W1 CI-venue separate entry; Actions-minute quantification).

## 2. RUN — W1 Windows E2E (closes the single evidence-grade gap)

- Bundle ready: `payload-proposals/W1-windows-runbundle/` (RUN-BUNDLE.md + run-e2e.ps1 + registry stub + expected-markers + result template).
- Verdict lines: **EXECUTION-OBSERVED** (marker pre-confirmation; negatives A/B clean) → the W1 rung CLOSED; **BLOCKED (<exact reason>)** otherwise.
- Expected quirk (N2A): `npm view`/`npm install` E404 on the malicious dist-tags value — EXPECTED; the CLI reads the packument raw.
- Corepack: yarn 1 must be installed explicitly on the host.
- Operator handoff message: `W1-windows-handoff-message.md`.

## 3. CONFIRM — wire-2 (only if pursued; both acts operator-gated at the moment of the act)

- **Chain 2 private-fork CI demo** (macOS runner: case-guard root-delete + config-as-data purge): spec `chain2-wire2-spec.md`; gating doc `wire2-gating-doc.md` (G1: FRESH confirmation; cleanup `gh repo delete chain2-cisabot --yes`; confirmation-text template included).
- No standing approval counts — reaffirm fork/workflow/payload/cleanup per act.

## 4. RECORD-MEMORY (operator authority)

- Payload ready: `pattern-candidates-disposition.md` — **PC-1..PC-12** (verified; PC-3 deferred — cross-engagement ref; operator decision) + **PC-13..17** (Wave D) + **PC-18..20** (N7: stealth-shape channel, boot-time SSR execution, baseHref emitRaw).
- Command: `tools/run-engagement.py record-memory --engagement engagements/angular-cli-2026-08 --disposition pattern-candidates-disposition.md` (operator-signed; async authority request first).

## 5. CLEANUP — execute the ledger at closure

- 31 rows in `cleanup.md`. **The single real credential: `/tmp/deepsec-scan-cli/opencode-key` (67B) — `rm -P` at closure (cleanup.md:10).**
- Large items: `/tmp/deepsec` (1.9 GB tool), `/tmp/deepsec-scan-cli` (962 MB), all `/tmp/*-poc`, `/tmp/nr2-*`, `/tmp/n1*`, `/tmp/kp-*`, `/tmp/c2shape`, `/tmp/c1cd` etc. (all ledgered; evidence copies retained in findings/ + payload-proposals/).
- Credential scan across the engagement: **CLEAN** (only parser-variable false positives).

## 6. STALE CLOSE-REQUEST — disposition

- Exactly one authority request on file: `authority/requests/auth-close-cli-2026-08-15.action.json` (close-lane, **pending_authority**, issued for the phase-2 close).
- **It is stale/superseded** — the engagement continued through cascading, deep, chainstorm, and next phases. Operator options: (a) `resolve-authority` with reason "superseded — engagement continued" (recommended before any new authority action), or (b) leave it; it is the ONLY request and blocks nothing.

## 7. WATCH — D3 timing (operationalized)

- Recurring: track **#33632** (OPEN, components, same guard-defect class) and **#33653** (pending class-fix PR, components). If the components fix lands and the guard is NOT swept into angular/cli, the D3 sub-claim survives unchanged; if swept reactively, the guard+budget sub-claims go historical and the forward condition (file-read in the action) is the survivor.
- Watch spec: `payload-proposals/next-phase-handoff-summary.md` + D3 REPORT CHAINSTORM NOVELTY UPDATE.

## 8. POST-FILING / OPTIONAL

- W1 version-check valid-dist-tag negative control run (N2G partial).
- Composite marker fix (DR3-03 — empty-secret tautology; re-labeled capability-fusion).
- Current-main re-verification is DONE (N1H/DR3-04 — all four items unchanged at main); re-run before filing if significant time passes.

## 9. RECORDS NOTE

- **One stale mention to fix before the operator reads the sequence doc:** `payload-proposals/FILING-SEQUENCE-final.md` row 3 still reads "5.6 CI" — the N6B correction raised the W1 CI venue to **8.1 HIGH** (also mirrored in `W1-CI-variant-brief.md` and `W1-filing-package.md`, both already corrected).
- rounds.md N1..N7 rows carry verdict text; plan.md §12/§14/§15 applied; cascades 15 rows; kernel 72 events contiguous.
