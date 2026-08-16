# cascades.md — angular-cli-2026-08

Every survivor gets both questions, and both are logged even when the answer is nothing.

- **Q1** — does the same behaviour appear elsewhere in the repo?
- **Q2** — does its ORIGIN enable a different attack?

Q2 over-reports on a first pass. Review every Q2 before recording a new kind.

## Attribution ledger — dev-infra root causes

This engagement consumes `angular/dev-infra`. A root cause that resolves into dev-infra is
**dev-infra`s finding, not this one** (scope.md, the Attribution boundary section). Record it here and move on; do not open a
finding package for it.

| Candidate | Root cause resolves to | Attributed to | Recorded |
|---|---|---|---|
| dev-infra.yml `labels` + `post_approval_changes` on `pull_request_target` with `ANGULAR_ROBOT_PRIVATE_KEY` (no repo-level fork guard) | the pinned dev-infra actions' internal fork discrimination (labels/post-approval-changes at 04230133) | angular-dev-infra-2026-08 (F3/R8/V1 family already held there) | 2026-08-14 |
| issue_labels job with `GOOGLE_GENERATIVE_AI_KEY` on `issues` events | dev-infra issue-labeling action internals | angular-dev-infra-2026-08 | 2026-08-14 |
| assistant-to-the-branch-manager `ANGULAR_ROBOT_PRIVATE_KEY` (fork guard present: `fork == false` — wiring correct) | n/a (wiring correct; action internals = dev-infra) | note only | 2026-08-14 |
| post_approval_changes googlers-org installation-token fetch + review logic per event (E12) | dev-infra action internals (04230133) | angular-dev-infra-2026-08 | 2026-08-15 |
| issue_labels Gemini cost-abuse on attacker-authored issues (E12) | dev-infra action internals (04230133); CORRECTED E1-R6/L12: no P1 found in the dev-infra visible records under that wording — operator to eyeball dev-infra plan.md §11 before relying; item is advisory-grade | angular-dev-infra-2026-08 | 2026-08-15 |
| | | | |

## Cascades

| Survivor | Q1 result | Q2 result | New kind? |
|---|---|---|---|
| M2 MCP best-practices roots-escape | same `createRequire`/raw-fs pattern: projects.ts package.json walk-up (root-bounded), doc-search fetch (no AbortSignal), ai-tutor static file — no other raw-fs escape found | origin = module-resolution semantics of `createRequire` (ancestor walk) — enables reading any ancestor node_modules' declared guide when roots are narrow | no (sibling-checked; same family as 34e1e0bb5) |
| M3 legacy deleteOutputDir | sibling builders: server/index.ts:236 same call; app-shell/prerender/ng-packagr builders use the same shared utility — check each caller's validation; new application builder validated | origin = shared `deleteOutputDir` resolving before checking — any future caller inherits the hole; fix belongs in the utility | no (extends 8358805d3 family) |
| D2 cache clean deletion | sibling sinks: `rm` with uncontained workspace-config path (cache clean); M3's deleteOutputDir (builders) — same family, different utility | origin = workspace-config values reaching destructive fs ops without containment | no (same family as M3) |
| D1 route codegen injection | sibling codegen sinks: `59e5e967a` fix family (refactor-jasmine-vitest); component selector (blocked by class validation); any other schematic option interpolated raw into generated source | origin = template interpolation without escaping — the 59e5e967a fix was one instance | no (extends codegen family) |
| HIGH-1 fork-guard | same `github.event.repository.fork` pattern in dev-infra's own workflows; downstream branch-manager.yml (dev-infra repo) | attribution split: the guard line is angular-cli's wiring (in scope); the merge-evaluation workflow internals are dev-infra's | D3 (promoted); E5 bounded (dispatch inputs value-bounded); E12 verifying repeatability |
| D2/purge amplifier | `purgeStaleBuildCache` — 9 builder entrypoints call the same uncontained `getCacheBasePath`; deletion fires on every default local build | origin = shared `getCacheBasePath` chokepoint (cache/utilities.ts + normalize-cache.ts) — containing it once fixes cache clean + every builder purge | amplifier folded into D2 (E0-R2/E2, KP-D2 SURVIVES) |
| W1 dist-tags win32 | npm/yarn-modern descriptors skip the dist-tag-value path (no requiresManifestVersionLookup) — yarn-classic unique; POSIX safe | origin = unvalidated registry VALUE reaching a shell string (win32) | **W1 PROMOTED (finding #6)** |
| M2 re-poisoning | version-specific guide re-read every call (only bundled cached) — durable session-wide | origin = no memoization on the attacker-influenceable path | amplifier folded into M2 (E6) |
| M2-family resolveNgCommand | createRequire ancestor walk in host.ts:124-140 (security-intent refactor 240936daf) — real-but-capped ≈zero delta | origin = createRequire ancestor semantics (same as M2) | cascade note in M2 (E8) |
| L5-SITE-1 shell:true package-manager task | repo-init fixed to array spawn; host.ts array spawn; only this task remains shell-string | origin = shared schematics task API — third-party schematics could carry metachars; capped by by-design exec | pattern candidate (command-construction) |
| Algolia key obfuscation (doc-search constants) | only one instance in-tree; dev-infra F13 used the same decryptable-blob pattern with a REAL secret | origin = client-side-obfuscation habit — flags where real secrets could hide | pattern candidate (encrypted-credential-in-repo) |
| | | | |

## Deep phase E1-R2 attribution rows (2026-08-15)

| # | Root cause | Resolves into | Evidence | Attribution |
|---|---|---|---|---|
| 8 | branch-manager robot-token budget consumption pattern + no-concurrency evaluation semantics (status-reporter-only, asserts disabled) | dev-infra branch-manager action (04230133) | L3 lane (E1-R2), per-event call counts vs 5,000 req/hr budget | dev-infra |
| 9 | trigger sets (pull_request_target types incl. labeled) + missing concurrency groups in assistant/labels/issue_labels workflows + the fork-guard expression | angular-cli .github/workflows | L3 lane (E1-R2) | angular-cli |
| 10 | pr.yml lint job: lockfile-substitution exec of ng-dev deps (fork PR can substitute ng-dev versions; runs as untrusted job today — dev-infra supply-chain surface) | dev-infra ng-dev machinery (04230133) | L6a lane (E1-R4) | dev-infra |

## Chainstorm E2-R5 attribution rows (2026-08-15)

| # | Root cause | Resolves into | Evidence | Attribution |
|---|---|---|---|---|
| 11 | branch-manager action dispatch gating + evaluation semantics (merge-label-gated dispatch; status-reporter-only; asserts disabled) + robot-budget consumption pattern + no-concurrency evaluation | dev-infra branch-manager action (04230133) | C5 lanes (E2-R5); D3 REPORT E12-correction block; lib/main.ts:101-117 | dev-infra |
| 12 | fork-guard expression + trigger sets + missing concurrency groups in assistant/labels/issue_labels workflows (the ENABLING defect for robot-key exposure) | angular-cli .github/workflows | C5 lanes (E2-R5); D3 REPORT defect section | angular-cli |
| 13 | labels/post_approval_changes/issue_labels action internals: ungated budget consumption, googlers-org installation-token fetch, AI-key usage per event | dev-infra actions (04230133) | C5 lanes (E2-R5); cascades rows 1/2/4/5 already record the pieces | dev-infra |
| 14 | FUTURE watch: a dev-infra action version that reads untrusted checkout content would turn the E12 flood into robot-key exfiltration | dev-infra action internals (future risk; enabler = angular-cli row 12) | C5 lanes (E2-R5); D3 remediation/future-reuse notes | dev-infra (watch) |
| 15 | #33479 RCE-sibling precedent (PR-triggered ng serve RCE class, fixed at pin) | angular-cli codebase (the fix is in-repo) | C2G (E2-R2) | context note (not an attribution row) |
