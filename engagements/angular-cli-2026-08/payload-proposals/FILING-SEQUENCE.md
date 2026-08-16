# FILING-SEQUENCE — angular-cli-2026-08 (Wave D D-R1 planner; operator decides, never the agent)

Sequence logic: severity × novelty × evidence-strength × doctrine-risk × co-discovery urgency.
Delta-first openings referenced from the payload drafts below.

## Ordered sequence (7 filings + 1 chain-context annex)

| # | Package | Severity | Delta-first opening (file) | Why here |
|---|---|---|---|---|
| 1 | **M3+D2 family report** (outputPath delete + cache purge; incl. case-guard root-delete, extract-i18n write, prerender route-escape amplifiers) | Medium / Medium | `humanized-M3-draft.md` + `humanized-D2-draft.md` + `WB-M3D2-filing-package.md` | Highest evidence-weight × NOVEL × low doctrine risk (write-side twice-fixed → the delete-side miss is compelling; #32873 disclosed-but-unfixed supports; #33312 cited). Chain C1/C2 context strengthens the impact story. |
| 2 | **E1-C1** i18n locale-key escape (webpack stack; members A2/A3/B/C/E/F) | Low-Med browser / **Medium 6.3 legacy-SSR** | `E1C1-filing-openings.md` (Opening A = SSR venue) | NOVEL; live runtime demos (browser + SSR-server execution, self-reproduce); venue-split severity is the filing's strength. Risk: config-trust doctrine likely applied — the SSR server-execution delta is the counter; cite #33073 adjacent. |
| 3 | **W1** win32 dist-tags injection (+ CI-token venue, version-check venue, poisoning) | Low-Med dev / 8.1 (HIGH — N6B-corrected) CI / conditional-High OIDC | `W1-filing-viability.md` + `humanized-W1-draft.md` | The zero-interaction CI-token delta (fork PR → RCE inheriting CI tokens) is the strongest counter to the won't-fix doctrine. Risks: execution rung environment-blocked (static-only argument + fixture), #32509/#32892 doctrine, foxllb co-credit cluster. |
| 4 | **D3** fork-guard ineffective | Low | `D3-filing-draft.md` | **Co-discovery urgency: #33632 OPEN in angular/components on the same guard class — file NOW (KP-D3), positioned after the top-severity items, never deferred past the next operator session.** Framing: control-ineffectiveness + org-wide robot-budget degradation (corrected numbers: issue_labels 7-10+AI-key, per-installation 5,000/hr, S1 120%/S5 200% exceed) + cash-burn. Risk: maintainers fix reactively → stale. |
| 5 | **M2** MCP roots-escape residual (ancestor-walk) | Low-Med | `M2` REPORT filing section | File-as-is per M2FD: lead with the residual re-PoC at the pin (NOVEL), cite the input-level fixes (34e1e0bb5/2b060630c/24fd8fce2) that are in the pin; run_target amplifier + C3 chain as CONTEXT, not core. Risk: triager sees "already fixed" — the residual demo must open. |
| 6 | **D1** `--route` codegen injection | Low-Med | `D1-filing-opening.md` + `D1-filing-viability.md` | Delta-first: validity + silence + persistence + SSR-runtime; lowest doctrine odds (family REJECTED #33074/#33076 under config-trust) — the counter is the exact-sink novelty + comma-exec + no-dedupe. Expect pushback; file last among findings. |
| 7 | **Chain-context annex** (not a filing) | — | C1 fixture (payload-proposals/chain-demos/), C4 evidence (findings/E1-C1/evidence/chain4/), C3 steering (findings/M2/evidence/steering-demo/) | C1 = the family narrative for M3+D2+E1-C1+W1 (cloned-repo delivery chain, fixture 9/9); C4 = E1-C1 evidence; C3 = M2 context; C2 = wire-2 demo spec (future); C5 = D3 watch-list. Operator may attach per finding or as one summary. |

## Per-filing risks

| # | Risk | Weight | Mitigation |
|---|---|---|---|
| 1 | Config-trust doctrine pushback (paths are dev-config) | Medium | Lead with the twice-fixed write family + the DELETE-side miss + case-guard root-delete on CI runners (macOS) |
| 2 | Config-trust doctrine applied; #33073 adjacent-class co-credit | Medium | SSR server-execution delta (attacker JS executes in the app server process) + mis-keyed-guard discriminator (ensureValidSubPath exists but is keyed wrongly) |
| 3 | Won't-fix doctrine (#32509/#32892); execution rung blocked; foxllb co-credit | HIGH | Zero-interaction CI-token delta (fork PR, no user interaction), manager-independent ng update reach, static argument + fixture; disclose cluster |
| 4 | Reactive maintainer fix → stale; #33632 reporter files first | HIGH (timing) | File within the next operator session; delta-first draft ready (D3-filing-draft.md) |
| 5 | "Already fixed upstream" dismissal | Medium | Open with the pin re-PoC (MARKER-ATTACKER-GUIDE-2 returned at the pin; negative control rejected) |
| 6 | REJECTED-family precedent (#33074/#33076 not-a-vuln) | HIGH | Delta-first: exact sink novel + comma-exec executes + production SSR runtime + persistence (no-dedupe) |
| 7 | Filing as a chain reads as alarmist | Low | Attach per finding as context; never as the core claim |

## Cross-cutting

- Sequence is severity-ordered with two exceptions forced by reality: M3+D2 first (strongest evidence × NOVEL × low doctrine risk — the "sure thing"), D3 moved up to #4 (co-discovery race), D1 last (lowest odds).
- W1 Windows E2E (fixture) remains the single environment-blocked rung — if a Windows host appears before the operator session, run it and W1's risk drops.
- All 7 packages gates CLEAR (re-verified Wave B); chain demos self-reproduce; credential scan clean.
