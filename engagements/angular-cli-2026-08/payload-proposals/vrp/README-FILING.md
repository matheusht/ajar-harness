# Google OSS VRP — FILING PACKAGE (angular-cli, 2026-08-15)

Operator submits at bughunters.google.com/open-source-security. Everything below is prepared; the operator re-authors the greeting/sign-off and any personal details, then files. **Do not mention the harness, the lab, or this engagement structure in any submission.**

## Filing sequence (recommended, with dependencies)

| # | Report | Severity | Why this order |
|---|---|---|---|
| 1 | VRP-E1C1-i18n-locale.md | 4.0 / 6.3 (SSR venue) | Fully demonstrated end to end, NOVEL, lowest duplicate risk |
| 2 | VRP-W1-disttags-win32.md | 7.5 dev / **8.1 CI venue** | Highest severity; the repro kit ships with it so triagers run it on their Windows machines |
| 3 | VRP-M3-outputpath.md + VRP-D2-cache-clean.md | Medium ×2 | Same family framing (shared chokepoint); can file as one or two reports |
| 4 | VRP-D3-fork-guard.md | Low | **Time-sensitive**: class co-discovered (#33632) with a pending class fix (#33653); file before the sweep |
| 5 | VRP-M2-mcp-roots.md | Low-Medium | Residual channel; cite #32766 doctrine + the stealth-shape counter |
| 6 | VRP-D1-route-codegen.md | Low-Medium | Cite the rejected family #33074/#33076; delta framing |

## Contents

- `VRP-*.md` - the seven humanized reports + the consolidated novelty statement.
- `pocs/` - per-finding repro kits:
  - `M3-outputpath/` - compiled deleteOutputDir PoCs + the case-guard demo (control throws, variant deletes root).
  - `D2-cache-clean/` - the purge PoC (real-CLI run recorded in the finding).
  - `W1-disttags/W1-windows-runbundle/` - **the one-command Windows repro kit** (`w1-repro-triager.ps1` + registry stub + fixture). This is how the PoC reaches a Windows environment: the triager runs it on their machine. The kit README explains the pass condition.
  - `M2-mcp-roots/` - the pin re-PoC (server + stdio client) + the steering demo (incl. the stealth shape-B evidence).
  - `D1-route/` - the comma-exec PoC + the SSR runtime demo.
  - `D3-fork-guard/` - the workflow + the budget-math scenarios (S1 120% / S5 200% exceed the 5,000/hr budget).
  - `E1C1-i18n/` - self-reproducing chain4 demos (demo.cjs, check4dot.mjs, neg.cjs, ssr-venue, ssr-e2e-real, member-e/f) + the materialized @babel closure note (re-run `npm`-free: the drivers resolve locally).

## Before each submission (the operator checklist)

1. Re-check the D3 state: `#33632` / `#33653` (one GitHub search).
2. Re-check "verified unfixed at main" for the filed finding (the reports carry the 2026-08-15 verification date; if a fix landed, reframe to historical).
3. Re-read the humanized report once, in the form, per the voice discipline (no em-dashes, straight quotes, first person, honest caps).
4. Attach the PoC kit (zip the `pocs/<finding>/` dir) or inline the single command for W1.
5. Sign with the operator handle; do not fabricate test accounts or dates.

## Notes from the duplicate lesson (F13)

- Every report opens with the delta vs the disclosed/rejected prior art, not the mechanism.
- The novelty statement (VRP-NOVELTY-STATEMENT.md) is the triage-prep: cite the cluster, state the duplicate risk per finding.
- Severity honesty: the venue splits (E1-C1 4.0/6.3, W1 7.5/8.1) are documented; file the honest vector and mention the variant in the report body, not in the CVSS field.
