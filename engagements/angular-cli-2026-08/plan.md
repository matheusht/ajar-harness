# plan.md — angular-cli-2026-08

## 0. Reading order (governs this file)

`CLAUDE.md` → `scope.md` → `program-policy.md` → `goal-prompts/angular-cli-longrun-v1.md` →
`recon-signals.md` → `rounds.md`. This file holds the working plan, proof strategies, and the
operator decision points. Append-only ledger of decisions lives in the kernel (`events.jsonl`).

## 1. Calibration (recorded pre-run, see progress.md)

Mature, CodeQL-scanned Google monorepo. Honest prior: solid core; realistic yield in the
supply-chain and CI surfaces, plus the NEW MCP server surface (recent fixes prove the team is still
catching misses there). Two SCC lanes (release/publish + CI) are the top-value targets; PV is a
secondary lane. The dev-infra attribution boundary applies to `.ng-dev/`/`dev-infra.yml` root
causes (→ cascades.md, not findings here).

## 2. Proof strategy — Lane A (release and publish path) — **OPEN**

*What counts as proof to a Google triager:* a runnable PoC showing attacker-influenced content (a
malicious dependency, a poisoned lockfile, a workspace/version choice the attacker controls)
placing attacker code or a wrong artifact into a published `@angular/*` package — or into a
developer machine via the CLI's fetch-and-execute paths — with the exact trust transition named
and a negative control that fails for the stated reason.

*Sub-conditions of "attacker code reaches a shipped artifact or dev machine":*
1. A1 — release tooling picks the artifact/dist-tag from a value an unprivileged contributor can
   influence (version bump PR, changelog data, package.json fields merged from PRs). Verify what
   `release`/`ng-dev release` in this repo consume (release config, versions.ts, `constants.bzl`,
   `MODULE.bazel`).
2. A2 — a dependency substitution: package.json/pnpm-lock resolver accepts a name/version the
   attacker controls (registry override, alias, workspace protocol, `file:`/`link:` deps in a
   publish path).
3. A3 — publish runs with attacker-influenced files (files whitelist, package.json `files`, npm
   ignore rules, git ignored files) so a wrong file ships.
4. A4 — `ng add`/`ng update` resolve a wrong package or skip an integrity check (schematic
   collection resolution, version satisfaction, downgrade acceptance, `--registry`, cache).
5. A5 — build-graph integrity: `MODULE.bazel.lock`/pnpm lock/goldens silently accept tampering at
   release time (no validation, or validation bypassed by a benign-looking field).

*What the lab must show:* the real publish/install path replicated against a local registry stub /
recording fixture (scope.md §8 method 2), with the attacker-controlled value injected at the
declared trust transition, and the shipped/installed artifact byte-different from the intended one
— plus the negative control.

- [x] sub-conditions enumerated (A1–A5)
- [ ] what a reviewer would accept as proof — stated (above)
- [ ] lab requirement stated (above)
- **status:** OPEN

## 3. Proof strategy — Lane B (CI / workflow compromise) — **OPEN**

*What counts as proof:* a workflow run (local replica via `act` or the repo's own runner harness —
scope.md §8 method 2) where fork-supplied content (PR head, PR metadata, issue body, comment) is
shown reaching a step with secrets/org access, or poisoning a cache/artifact a trusted path later
consumes — with the exact workflow and step named and a negative control.

*Sub-conditions:*
1. B1 — any workflow consumes untrusted PR content with secrets in scope (`pull_request_target`,
   `workflow_run` with `pull-requests: write`, `issue_comment`, `push` from forks).
2. B2 — a fork can poison a cache key the trusted path reads (cache key not scoped to
   repo/branch/ref, or key inputs attacker-influenced).
3. B3 — artifact upload/download between jobs without provenance distinction (fork artifacts
   consumed by trusted jobs).
4. B4 — release/publish workflow trust anchors (who can trigger, environment protection, tag
   filtering, `if: github.event` checks).
5. B5 — dev-infra consumed actions (`dev-infra.yml`) — attribution boundary: a defect in the
   action is dev-infra's finding; a defect in HOW this repo wires it (missing input, over-granted
   permission) is ours.

*What the lab must show:* `act` replica or the repo's test harness runs the named workflow with a
synthetic fork payload; the poisoned value demonstrably reaches the protected step; the negative
control (a clean payload) does not.

- [x] sub-conditions enumerated (B1–B5)
- [ ] reviewer-acceptable proof stated (above)
- [ ] lab requirement stated (above)
- **status:** OPEN

## 4. Round plan

- Round 0: blind — one family per hunter, 12 lanes (release/publish, CI workflows, lockfile/graph,
  ng add/update, schematics+tasks, devkit path/vfs, workspace+JSON schema, architect resolution,
  @angular/ssr, ngtools/webpack, MCP surface, registry auth). No candidate is killed on one pass.
- Round 1+: funnel survivors through verify → refute → gate → promote; ladder severity; cascade
  Q1/Q2 every survivor.
- Persistence mode per `engine/persistence.md` on any strong signal; kill discipline requires a
  new signal to reopen a family.

## 7. Cascading phase — composition matrix (per angular-cli-cascading-v1.md §8)

Cells: (finding × angle) with a one-line hypothesis and an owner round. Verdicts per
chainability.md §4: bounded / amplifier_found / new_finding_spun_off / needs_more_evidence / blocked.

| Cell | Hypothesis | Round |
|---|---|---|
| M2×A3 (composition) | Injected guide content steers the agent into run_target with file-replacements/output-path options → arbitrary read/write via the build path (agentic RCE) | E0-R1 |
| M3+D2×A3 (chokepoint) | All rm/deleteOutputDir/unlink sinks consuming workspace-config paths without containment — shared chokepoint widens both | E0-R1 |
| W32×cap (escalation §2.1) | Cloned-repo .npmrc registry / workspace schematics defaults / registry dist-tags values reach the win32 shell-string unquoted → cap removed | E0-R1 |
| D1×A3 (schematics defaults) | Workspace schematics defaults make every ng generate module emit the payload — amplification channel | E0-R1 |
| D3×A5 (fan-out) | Dispatch inputs repo/owner/pr/sha carry attacker-controlled values into dev-infra merge-evaluation | E0-R2 |
| M2×A2 (repeatability) | Agent re-poisoned on every get_best_practices call; symlink→exfil channel | E0-R2 |
| D1×A1/A6 (persistence+siblings) | Injected code survives regenerations; other schematics interpolate raw options | E0-R2 |
| MCP×A6 (raw-fs population) | Every raw-fs call in tools/ not mediated by the host (doc-search, projects.ts, devserver) | E0-R2 |
| M3/D2×A1 (persistence) | Watch-mode deletions, cache re-creation as file, symlink loops on retry | E0-R3 |
| D1×A5 (fan-out) | Generated routing file imported by library builds / publish path | E0-R3 |
| ng-update×A6 (siblings) | path.join(packagePath, external) sites; migration-collection escape family | E0-R3 |
| D3×A2/A4 (repeatability+reach) | Fork PR re-triggers secret-bearing jobs; labels/post_approval_changes wiring | E0-R3 |
| all | kill-pairs on every amplifier_found | E0-R4 |
| all | PoC verification + gate checks on spin-offs | E0-R5..R6 |
| all | kill-pairs round 2 (E10/E12/E9/E11) | E0-R5 (done: SURVIVES-narrow ×2, CONFIRMED, CORRECTED) |
| all | pre-kill-pair fold verification (E6/E7) + W1 fixture + D2 cross-check | E0-R6 (done: CORRECTED-narrowed / CONFIRMED-with-caps / CORRECTED / CORRECTED) |
| all | held-cap coverage sweep | E0-R7 (done: all caps HOLD) |
| all | report QA (6 findings) | E0-R8/R9 (done: D1/D3/M3 CORRECTED, D2/M2 ACCURATE, W1 CORRECTED, attribution CLEAN, records CORRECTED) |
| all | family-extension sweeps | E0-R10 (done: 4 SWEEP-COMPLETE) |
| all | final coverage sweep of held caps + report QA + records + close prep | E0-R7..R12 (all done — see §8 terminal table) |

## 5. Round log summary (2026-08-15, ~6h in)

- R0 blind (12 lanes) → R1 verification (M2+M3 PoCs) → R2 refutation (M3 ESCALATED) → R3 SCC deep
  push (ng add/update/laneA/aliases/spawn/MCP-chain — DRY with low caps) → R4 corners (capped).
- **FINDING CANDIDATES:** `unproven/M2-mcp-best-practices-roots-escape` (real-but-capped,
  Low-Medium — refuter R2-1) and `unproven/M3-legacy-builder-outputpath-delete` (confirmed-escalated,
  Medium — refuter R2-2; flagship application builder delete path + legacy siblings).
- **Covered-dry:** CI wiring (R2-6), aliases/resolution (R3-4), spawn sweep (R3-5), Lane A
  sub-conditions (R3-3), generators (R4-1), dev-server/writer/cache corners.
- **deepsec cross-scan (COMPLETE):** 408 files analyzed (31 API-errors), 82 findings (2 HIGH / 26
  MEDIUM / 1 HIGH_BUG / 53 BUG) — every finding adjudicated against pinned source: **+2 CONFIRMED
  (D1 route codegen injection, D2 cache-clean deletion), +1 real-but-capped (D3 fork guard),
  rest capped/held**. Finding candidates: M2, M3, D1, D2, D3 in `unproven/`.
- Kernel activation STILL pending operator (`signers/complete-initialization.zsh`); all kernel
  records (attempts M2/M3, hypotheses, observations) staged in `tmp/pending-records/` for replay on
  activation.

## 6. Operator decision points (filled as they arise)

- [ ] KERNEL ACTIVATION — re-run `! engagements/angular-cli-2026-08/signers/complete-initialization.zsh`
      (backtick fix applied; new frozen hashes; stale .sig moved aside). Kernel records are staged
      and will be appended on activation.
- [ ] M3 filing decision (Medium, data-loss primitive; operator re-authors the report if filing)
- [ ] M2 filing decision (Low-Medium; real-but-capped; marginal value — operator call)
- [ ] Funnel complete — operator reviews D1/D2/D3 + M2/M3 before any filing decision (all PoCs
      reproducible from the evidence dirs)


## 8. Cascading phase — TERMINAL COVERAGE TABLE (2026-08-15, 12 rounds × 4 subagents)

| Survivor | Terminal verdict (chainability §4) | Key adjudications |
|---|---|---|
| D1 route codegen | `amplifier_found` (folded, narrowed) | E10 production-SSR reach + R6-E7 no-dedupe persistence folded; E4 defaults channel **KILLED** (KP-D1: marginal ≈ 0 — npm lifecycle exec); title sibling sink **KILLED**; comma-exec PoC correction (KP-E10). Low-Medium, gates clear |
| D2 cache clean | `amplifier_found` (folded) | E2/KP-D2 **SURVIVES**: purgeStaleBuildCache ×9 entrypoints → unconditional deletion on every default local build; E9 durability; R10-D2: 8 consumers, 2 byte-identical getCacheBasePath copies = the chokepoint. Medium, gates clear |
| D3 fork guard | `amplifier_found` (folded, narrowed) | E12/KP-E12 **SURVIVES-narrowed**: unbounded event-stream × robot-key jobs + robot-token rate-limit pressure; spam sub-claim killed; E5 dispatch inputs bounded. Low, gates clear |
| M2 MCP roots | `amplifier_found` (folded, narrowed to note) | E6/R6-E6 re-poisoning persistence (no caching layers — persistence note, not capability); E8 resolveNgCommand sibling (≈0 delta). Low-Medium, gates clear |
| M3 outputPath delete | `bounded` (reach/durability notes folded) | E1 run_target caller (severity delta killed — agent has shell); E9 per-invocation; R10-M3 population sweep (3 shared-utility callers + unit-test rm covered-by-D2). Medium, gates clear |
| W1 dist-tags win32 | `new_finding_spun_off` → **PROMOTED (finding #6)** | KP-W1 SURVIVES (pre-gate pre-install invisible execution; yarn-only exact); Windows E2E fixture specified; CVSS 7.5. Low-Medium, gates clear |
| Held: L5 shell:true · doc-search · run_target options · ng-add silent-exec | `cap-holds` (R7 adversarial) | all four caps hold after targeted attacks; win32 quote-wrap family note (PC-9) recorded |
| H12 migration-collection | `bounded` (cap holds via install-exec) | E11 + KP-E11: migrateOnly/main-flow validation asymmetry = hardening note |

**Phase terminal:** one promoted spin-off (W1) + two surviving amplifiers (D2, D3) + M2/D1 narrow amplifiers + the remaining matrix fully bounded with demonstrated caps — success per the phase calibration. The engagement remains OPEN for the operator's filing decisions (6 findings), memory disposition (PC-1..PC-9 scrubbed + proposed), and any further phases.


## 9. Deep phase (per angular-cli-deep-v1.md, 2026-08-15, 12 rounds x 8 subagents) — LANES

| Lane | Direction | Owner rounds | Status |
|---|---|---|---|
| L1 | W1 Windows E2E (fixture execution; else static-only filing argument + exact blocker) | R1, R2 | **closed** (blocker exact: Darwin/arm64 no Windows layer; static-only filing argument complete in W1 REPORT) |
| L2 | Windows/APFS case-guard bypass on M3 deleteOutputDir (NEW escalation) | R1, R2 | **resolved** — verified with compiled production code (control throws, variant deletes root); folded as M3 amplifier #1; survived adversarial refutation (R1 L2a); case-folding remediation in M3 item 2 |
| L3 | D3 merge-queue wedge (dev-infra branch-manager.yml concurrency — attribution-aware) | R2 | **resolved** — queue-wedge KILLED (status-reporter only); robot-budget NARROWED-SURVIVES (per-event costs vs 5,000/hr; issue-reopen cycle); E12 corrected; folded into D3; 2 attribution rows |
| L4 | deepsec resume on 50 errored files + manual sweeps | R1-R3 | **resolved** — resume COMPLETE (451/451 analyzed, 16 findings); all adjudicated R3-R4 (1 promoted: E1-C1; rest folded/capped/refuted) |
| L5 | @angular/create + ng analytics sweep (R4-3 gap) | R2, R3 | **closed** — create CLEAN (7/7 angles); analytics CAPPED (1 privacy note H2) |
| L6 | scripts/ build tooling as CI surface (pr.yml admin validate/release build) | R3 | **closed** — CAPPED by untrusted-job boundary; future-reuse warning H14; cascades row 10 |
| L7 | D1 channel completeness (global→workspace→project schematics defaults) | R3 | **resolved** — all three levels verified; merged-options schema fix line applied to D1 |
| L8 | M2 x shell-less clients future-reach note | R3 | **resolved** — desktop-assistant population named as the concrete trigger; chain undemonstrated in-lab; trigger language refined in M2 |
| L9 | Novelty check for all 6 findings (GitHub issues/advisories/disclosures) | R1, R2 | **resolved** — M3 NOVEL, D2 NOVEL, D1 NEAR-MISS (#33074/76 REJECTED), W1 NEAR-MISS fix-bypass (#32509/#32892 doctrine), M2 residual NOVEL, D3 no disclosure; framing sections applied |
| L10 | Filing packaging (M3+D2 family report, W1 rung outcome, humanized reports, evidence inventory) | R5-R9 | **resolved** — bundle complete (payload-proposals/: FILING-COVER + 3 humanized drafts + dev-infra-handoff; credential scan CLEAN; evidence gaps closed) |
| L11 | Memory disposition + pattern promotions (PC-1..PC-9) | R9-R11 | **resolved** — pattern-candidates-disposition.md written (12 entries, winners.md format, PC-3 flagged for operator decision); record-memory run = operator-only |
| L12 | Cross-engagement handoff (googlers/Gemini evidence package for dev-infra) | R10 | **resolved** — payload-proposals/dev-infra-handoff.md written (4 items, F4 disposition, boundary statement); dev-infra records untouched |

**Phase terminal:** every lane has a verdict (resolved/closed/blocked/needs_more_evidence); six findings' reports are the most honest versions evidence supports.


## 10. Deep phase — hardening notes (recorded, NOT findings)

| # | Note | Source | Decision |
|---|---|---|---|
| H1 | SSR route-tree.ts:210 decodeURIComponent throws URIError on malformed %-encoding (e.g. /%zz) → 500 in default Express deployments (live-verified with compiled RouteTree; no crash; custom adapters may hang) | X2 (E1-R2) | remediation line: try/catch decodeURIComponent → no-match/400; add test |
| H2 | ng analytics C1: workspace angular.json `cli.analytics` string silently enables telemetry without a prompt (analytics.ts:100-118), incl. CI, with attacker-chosen uid sent as cid/uid — privacy note, no victim data, no injection | L5b (E1-R2) | hardening note for maintainers |
| H3 | @angular/create: P2 cosmetic (--package-manager startsWith match broader than exact flag) + require.resolve unanchored across hoisting modes | L5a (E1-R2) | hardening notes only; surface otherwise CLEAN |
| H4 | MCP onpush-zoneless-migration: code-snippet echo into assistant instructions (same-trust, dev-invoked) + sampling path-ranking z-validated (bounded) — regression guard: future MCP tools must keep using the restricted host | L4a (E1-R1) | M2 remediation audit line |
| H5 | URIError/stack-in-dev info leak via Express default handler (NODE_ENV unset) — minor | X2 (E1-R2) | fold into H1 |
| H6 | SSR malformed-input robustness family: route-tree URIError (H1) + Host-header 500 (validation.ts createRequestUrl order; crash refuted — log-only handlers; deepsec MEDIUM overstated) + request.ts same class — combined remediation: URL.canParse guard on host before construction; try/catch decodeURIComponent → 400 | A5/X2 (E1-R2/R3) | combined hardening family; NOT findings (Low, 500-only, no amplification) |
| H7 | devkit schema registry: prototype pollution via constructor/prototype chain (NOT __proto__ — ajv skips direct keys; live PoC /tmp/a6/test-pp-ctor.mjs) + $ref arbitrary HTTP GET (remote schema poisoning + hang DoS live; redirects REJECTED status>=300 — deepsec corrected) — both CAPPED for angular-cli (code-exec-equivalent schema channel); devkit remediation: _set fragment sanitization + $ref allowlist/private-IP block/timeout/size cap | A6 (E1-R3) | hardening notes with devkit lines |
| H8 | architect: job-registry arbitrary module load (library-API only, nil in-repo reach) + builders-manifest raw-check/normalized-join mismatch (live-proven; config-trust already code-exec) — V4 candidate CAPPED with evidence; remediation: name-shape validation in get(), check path.normalize(manifest path) | A7 (E1-R3) | hardening notes; V4 → capped |
| H9 | MCP host glob guard: `[.][.]`/`\\.\\` encodings bypass the includes('..') + base realpath layers (live-proven) BUT reach capped (constant '**/*.ts' patterns; reads re-checked) — regression guard: first future tool with attacker-influenceable glob pattern inherits root escape; fix: expand+realpath-validate matches, reject backslash/char-class encodings; host_spec.ts tests | A1 (E1-R3) | hardening note; L4a positive control stands with caveat |
| H10 | doc-search: redirect/scheme/port re-validation + content-fetch timeout/size/content-type caps + Algolia in-repo obfuscated key rotation hazard (search-only today; R7 cap VERIFIED holds — deepsec MEDIUM downgraded) | A2 (E1-R3) | 3 hardening notes |
| H11 | SSR redirect family: XFP multi-value raw reflection + dev-path bypass (response-integrity Low; open-redirect REFUTED — redirectTo uses post-nav PlatformLocation; deepsec #1 mechanism error) | A4 (E1-R3) | hardening H-A/B/C; no finding |
| H12 | run_target promotion trigger (shell-less client) + completion.ts RC-consent Low candidate (A8 item 5: forceAutocomplete bypasses isTTY, askConfirmation non-TTY default-true) | A3/A8 (E1-R3) | trigger documented in M2; E1-C2 operator-bar |
| H13 | devserver robustness family (all three deepsec items CAPPED-by-trust, mechanisms real): unbounded ng serve spawn (agent-controlled, delta≈0 vs run_target) + Infinity timeout accepted (requires stale-entry precondition) + findAngularJsonDir boundary walk throws (single-call availability, agent-controlled) — combined remediation: lifecycle cleanup on MCP-server exit, stale-entry recovery/re-spawn, timeout schema bounds (int().min().finite()), boundary-tolerant walk | L6c (E1-R4) | H-note; no finding |
| H14 | L6a scripts/ CI surface: CAPPED by untrusted-job boundary (3 exec primitives for fork PRs in lint job — lodash.template of PR-controlled .ejs, scripts rewrite, lockfile substitution; none carry secrets/GITHUB_TOKEN) — FUTURE-REUSE WARNING: adding admin validate/templates to any pull_request_target workflow = token-steal primitive; snapshots SNAPSHOT_BUILDS_GITHUB_TOKEN in git clone argv (main-only, minor); documentation guard H-L6a-1 | L6a (E1-R4) | H-note + cascades row 10 (ng-dev attribution) |
| H15 | E1-C2 (completion RC-consent): consent defect REAL but preconditioned on NG_FORCE_AUTOCOMPLETE=true (completion.ts:129-131 bypasses isTTY; askConfirmation non-TTY default-true; also skips duplicate-append guard); write-target bug (.zsh_profile + .profile bashism breaks POSIX-sh login) = actionable maintainer defect — Low; remediation: force-path must respect TTY/CI/global-install/duplicate guards; fix zsh candidates to .zshenv/.zprofile + POSIX-safe fallback | L8 (E1-R4) | H-note per L8 recommendation (operator bar: not a finding) |
| H16 | terminal escape-sequence via registry metadata in ng add (display-only; OSC 52/prompt-spoofing; same registry precondition as W1) — sibling note in W1; remediation: strip control chars from registry-derived display strings | L6b (E1-R4) | W1 sibling note; no standalone finding |
| H17 | cache/info hang variant (symlink cycle, no visited-set; self-inflicted; display-only traversal) — folded into D2; lstat+cycle/depth guards in the shared walk | L6b (E1-R4) | D2 note; zero delta |


## 11. Deep phase — TERMINAL COVERAGE (2026-08-15, 12 rounds × 8 subagents = 96 slots)

| Lane | Verdict (chainability §5 vocabulary) | One-line result |
|---|---|---|
| L1 W1 Windows E2E | `closed` (wire-gate) | Blocker exact (Darwin/arm64, no Windows layer); static-only filing argument complete in W1 REPORT |
| L2 case-guard bypass (M3) | `resolved` (escalation) | Compiled-module PoC: control throws, case-variant deletes workspace root; M3 amplifier #1; survived 7-variant refutation |
| L3 D3 merge-queue wedge | `resolved` | Queue-wedge KILLED (status-reporter only); robot-budget NARROWED-SURVIVES (per-event costs vs 5,000/hr); E12 corrected; D3 fold + 2 attribution rows |
| L4 deepsec resume | `resolved` | 451/451 files analyzed (50-errored resume COMPLETE); 16 findings adjudicated → 1 promoted (E1-C1), rest folded/capped/refuted |
| L5 create + analytics | `closed` | create CLEAN (7/7 angles); analytics CAPPED (H2 privacy note) — R4-3 gap closed |
| L6 scripts/ CI surface | `closed` | CAPPED by untrusted-job boundary; future-reuse warning H14; cascades row 10 |
| L7 D1 channels | `resolved` | Three-level defaults verified; merged-options schema fix line applied to D1 |
| L8 M2 shell-less | `resolved` | Desktop-assistant population named as the concrete trigger; chain undemonstrated in-lab; trigger language in M2 |
| L9 novelty | `resolved` | M3 NOVEL, D2 NOVEL, D1 NEAR-MISS (REJECTED family), W1 NEAR-MISS fix-bypass (doctrine), M2 residual NOVEL, D3 no disclosure, E1-C1 NOVEL |
| L10 filing packaging | `resolved` | Bundle complete: FILING-COVER + humanized drafts + evidence inventory; credential scan CLEAN |
| L11 memory disposition | `resolved` | pattern-candidates-disposition.md (12 entries); record-memory run operator-only |
| L12 cross-engagement | `resolved` | dev-infra-handoff.md written; 4 advisory-grade items; dev-infra records untouched |

**Phase outcome:** 1 new finding promoted (E1-C1, finding #7, webpack-stack i18n locale-key escape, Low-Medium, NOVEL);
2 material finding widenings folded (W1 ng-update entry manager-independent; M3 amplifier #3 prerender route-escape);
M3 case-guard escalation resolved; W1 Windows E2E rung closed-with-reason; deepsec resume fully adjudicated;
6 hardening-note families + 11 individual notes recorded; 7 findings all gates CLEAR; kernel 45 events / 24 attempts /
7 hypotheses closed; filing bundle + memory disposition + dev-infra handoff prepared for the operator.
**Phase-terminal: COVERAGE achieved — every lane has a verdict; the seven findings' reports are the most honest
versions the evidence supports. The engagement remains OPEN for operator decisions (filing, memory, cleanup,
any further phases).**


## 12. Chainstorm phase (per angular-cli-chainstorm-v1.md, 2026-08-15) — CHAIN MATRIX + WAVES

**Wave A — chains (10 rounds x 8 subagents = 80 slots):** R1 Chain 1 cloned-repo delivery (W1+M3+D2+E1-C1+D1) · R2 Chain 2 CI sabotage · R3 Chain 3 MCP agent steering (D1->M2->run_target) · R4 Chain 4 browser supply chain (E1-C1 member C) · R5 Chain 5 D3 forward (robot-key exposure) · R6 integration · R7 kill-pairs · R8 cascading · R9 demos+evidence · R10 chain records.

**Wave B — per-finding lanes (36 = 6 lanes x 6 subagents):** W1 · M3+D2 · D1 · E1-C1 · M2 · D3 — each 6: mechanism-extension / channel-sweep / kill-pair / PoC-build / filing-delta / reviewer.

**Wave D — next-phase handoff (64 = 4 rounds x 16):** D-R1 next-phase plan from confirmed residue · D-R2 execute highest-value lanes · D-R3 kill-pairs+verify · D-R4 synthesis+records+terminal.

| Chain | Status | Verdict | Key evidence |
|---|---|---|---|
| C1 cloned-repo delivery | **CONFIRMED** | mechanism-complete + fixture 9/9 (both modes) | payload-proposals/chain-demos/ (chain1 fixture: registry-server + malrepo + run-chain1, 9/9 both modes re-run N4A); W1 cmd.exe hop execution-pending (Windows; runbundle operator-ready) |
| C2 CI sabotage | **NARROWED-SURVIVES** | config-as-data shape survives; fork-PR shape killed (install = code-exec); macOS case-guard root-delete VERIFIED; W1-on-Windows = CI-token RCE (env inheritance, source-verified) | wire-2 spec in payload-proposals; C2D/C2E/C2H verdicts |
| C3 MCP agent steering | **ARMED-WITH-MECHANICALLY-PROVEN-STEALTH-SHAPE** (N4C: unprepared real agent FOLLOWED the stealth shape — traversal hidden via a repo symlink; the visible-anomaly shape is refused) | steering demo LIVE (priority-0.9 content -> run_target option-values -> out-of-roots exfil); H2 real-agent follow scored MEDIUM-HIGH | findings/M2/evidence/steering-demo/ (+ shape-B/ N4C closing-branch run) + INT2 verdict + N1C/N2F verdicts |
| C4 browser supply chain | **CONFIRMED (venue-restricted)** | bundle demo LIVE (5-dot + 4-dot dependency-confusion); executes in client bundle AND legacy SSR server process; NOVEL | findings/E1-C1/evidence/chain4/ |
| C5 D3 forward | **FUTURE-CONDITIONAL** | no key-exposure today (zero fs-ops); guard defect UNFIXED at pin AND main (N1H verified) + co-discovered (#33632 OPEN; #33653 pending class-fix); 5-trigger watch-list | C5A/C5E/C5H verdicts; cascades rows 11-15 |
| COMPOSITE X1-X4 | **capability-fusion artifact — NOT new security evidence (DR3-03 KILLED-NARROWED: a false-positive marker was found and the one-run composite adds nothing beyond the individual chains); per-chain verdicts unaffected; re-labeled in chain-demos/README** | INT4 matrix; INT6 honest framing; DR3-03 kill-pair; composite README re-label | — |

# CAS-RECORDS — plan.md section 13 draft: CHAIN CASCADING SUMMARY (chainstorm phase E2, 2026-08-15)

## 13. Chainstorm phase — CHAIN CASCADING SUMMARY (per finding) + CHAIN-TO-FINDING MAP + NEXT-PHASE RESIDUE

### (a) Per-finding chain-cascading summary — what the chains added to each finding

| Finding | Gained from the chains | Severity state | Citations added | Evidence added |
|---|---|---|---|---|
| **W1** yarn-classic/ng-update dist-tags win32 injection | CI-token amplifier (E2-R2/C2D, kill-pair SURVIVES-NARROWED E2-R7/KP-W1): fork PR on a Windows CI shape → cmd.exe inherits the step env (read-scoped GITHUB_TOKEN by default, ACTIONS_RUNTIME_TOKEN/URL, OIDC id-token when granted; robot key NOT in env — C5A); primary attacker-triggered venue = e2e/scaffolding jobs running ng add/ng update on PR content; bot-run updates excluded (different attacker model). Manager-independent ng-update entry (FS-W1/E1-R8) is the CI venue's reach. Doctrine section (won't-fix, #32892 rejected). | Low-Medium (base); **CI-variant severity (Medium?) = operator filing decision** (KP-W1) | #32509, #32678, #32892, 85e3ce2e0a, foxllb cluster #33074-#33077 | WINDOWS-E2E-FIXTURE.md (unchanged); update-resolver-amp/ evidence; Chain 1 fixture hop H1 (registry fetch + injection carrier constructed) |
| **M3** outputPath deletion | Case-guard root-delete verified as the Chain 2 macOS hop (E2-R2/C2B, 2 reproductions); delete/prerender hops in the Chain 1 fixture (H2/H6); CI-reach: purge/delete fire silently in CI (Chain 2 config-as-data shape); **follow-up fix #33312/bd413b0eb (2026-06-04, main-only, write-path) + delete-guard proposal #32873 disclosed-but-unfixed — current-main re-verification required before filing** | Medium (base); case-guard amplifier keeps Medium; write-variant amplifiers #2/#3 at Low | 8358805d3, #32986, #32873 (NEW), #33312/bd413b0eb (NEW) | evidence-caseguard/, evidence-x1-extract-i18n/, Chain 1 fixture H2/H6 |
| **D2** cache-path deletion | purgeStaleBuildCache = the **keystone unconditional hop** of Chain 1/2 (fires on every default build; kill-pair KP-C2 confirmed it is NOT niche); chain-invisibility (no output line at `ng cache clean`) is the delivery-enabler for the whole chain | Medium (unchanged) | #22851, #33321 (existing) | Chain 1 fixture H3 (purge deleted the stale sibling dir) |
| **D1** route codegen | The defaults channel (no `--route` flag, global/workspace schematics defaults) is the Chain 1 product-code-persistence leg (fixture H5: payload in the emitted routing module); SSR/production reach = the persistence delta (ships to the dev's deployed app) | Low-Medium (unchanged) | #33074/#33076 (disclosed+REJECTED framing), 59e5e967a family | Chain 1 fixture H5 |
| **E1-C1** i18n locale-key bypass | **SEVERITY RAISED to venue-split (E2-R7/KP-E1C1, then corrected E2-B2/ECKP):** browser venue Low-Medium 4.0 (unchanged); **legacy-SSR venue MEDIUM 6.3** (CVSS:3.1/AV:L/AC:H/PR:N/UI:R/S:U/C:H/I:H/A:H — honest preconditions per the Wave-B kill-pair correction; the earlier MEDIUM 6.3 (wave-B corrected) figure used the remote/no-interaction vector and is superseded) — inline-path dataPath and entry-path findLocaleDataPath both land attacker-authored JS in the server bundle (server/index.ts:139+202-208 → i18n-inlining.ts:45 → process-bundle prepend), executing in the SSR Node process (RCE-equivalent in the app runtime). Chain 4 CONFIRMED venue-restricted; malicious-dependency delivery shape survives the kill-pair (committed-node_modules delivery KILLED empirically — npm install prunes); 4-dot depth exact (3-dot bounded, 5-dot killed) | **venue-split: browser Low-Med / legacy-SSR MEDIUM 6.3 (finding.json still carries the browser vector — operator to decide separate record)** | #33073 (foxllb adjacent family — CSS url() class), #33074/#33076, #33740, #33859/#33866 (functional context) | evidence/chain4/ (demo.cjs, check4dot.mjs, dist), evidence/chain4/killpair-delivery/ (install-prune + SHAPE-A tests) |
| **M2** MCP roots-escape | Steering chain (C3, ARMED-WITH-ESTIMATED-FOLLOW): repo-derived priority-0.9 instruction content → run_target option-values → out-of-roots read → build-artifact exfil (live demo, findings/M2/evidence/steering-demo/); H2 real-agent follow scored MEDIUM-HIGH (INT2); trigger refined to armed-but-unconfirmed with two closing branches; run_target amplifier mechanism corrected (relative .. traversal; fileReplacements NOT a channel) | Low-Medium (unchanged); promotion trigger documented | #33628 (population citation) | evidence/steering-demo/, evidence/run-target-kp/ |
| **D3** fork guard | FUTURE-CONDITIONAL chain (C5): enabling defect UNFIXED at pin (yml:21) + **INDEPENDENT CO-DISCOVERY — angular/components #33632 OPEN** on the same guard-defect class → **file-now strategy** (window analysis: the #33632 reporter is the single most likely entity to file the angular-cli instance; delta-first humanized writeup must open with the quantified robot-budget consumption); robot-budget channel quantified (E12 correction); queue-wedge killed; cascades rows 11-15 | Low (unchanged; control-integrity) | #33632 (NEW), #961, #3746/#3761, #3827 | C5A/C5B/C5C/C5E/C5H verdicts; cascades rows 11-15 |

### (b) Chain-to-finding map — which finding carries which chain hop

| Chain | Hop | Carrier finding | Evidence |
|---|---|---|---|
| C1 cloned-repo delivery | H1 registry redirect + dist-tags fetch/injection | W1 (manager-independent ng-update path; yarn-classic add path) | chain1 fixture H1a/H1b/H1c (POSIX no-exec negative) |
| C1 | H2 outputPath delete | M3 | chain1 fixture H2 |
| C1 | H3 cache purge (unconditional) | D2 | chain1 fixture H3 |
| C1 | H4 locale-key write escape | E1-C1 (member A) | chain1 fixture H4 (2-level escape) |
| C1 | H5 schematics-defaults route payload (product-code persistence) | D1 | chain1 fixture H5 |
| C1 | H6 case-guard root-delete | M3 (amplifier #1) | chain1 fixture H6 |
| C2 CI sabotage | config-as-data: purge/delete/writes on PR content | D2 + M3 + E1-C1 | wire-2 spec; KP-C2 |
| C2 | macOS root-delete (case-insensitive APFS) | M3 (amplifier #1) | C2B (2 reproductions) |
| C2 | W1-on-Windows = CI-token RCE | W1 (chainstorm amplifier) | KP-W1 (3 precision corrections) |
| C3 MCP steering | repo content → priority-0.9 instructions → run_target options → exfil | M2 (residual + run_target amplifier) | steering-demo/, INT2 |
| C4 browser supply chain | locale-key + dependency-confusion → module in client bundle | E1-C1 (member C, browser venue) | chain4/ demo.cjs |
| C4 | same content in legacy SSR server process | E1-C1 (member C, SSR venue — MEDIUM 6.3, corrected E2-B2) | C4F + KP-E1C1 + ECKP |
| C5 D3 forward | guard ineffectiveness → robot-key exposure (future-conditional) | D3 (+ cascades rows 11-15) | C5A/C5E/C5H |

### (c) Next-phase residue list (Wave D input)

1. **W1 Windows E2E** — run WINDOWS-E2E-FIXTURE.md on any Windows host; closes the cmd.exe execution rung AND makes the CI-token venue (C2D) execution-confirmed. Highest-value single artifact.
2. **Wire-2 CI demo (Chain 2)** — private-repo Actions run on a macOS runner proving the case-guard root-delete + config-as-data purge; operator-gated (fresh confirmation at the act); wire-2 spec in payload-proposals/chain2-wire2-spec.md.
3. **Real desktop-client chain demo (Chain 3 closing branch)** — an actual shell-less MCP client (or a documented deployment) following the steered instruction; the remaining un-demonstrated hop (H2) is the difference between ARMED and CONFIRMED.
4. **E1-C1 legacy-SSR venue E2E** — full legacy server-bundle build with the malicious locale content executing in a real SSR server process (venue-split severity rests on the source-verified chain; a runtime run closes it).
5. **D3 filing timing** — file now per the window analysis (#33632 co-discovery cluster active across 5 repos); delta-first humanized writeup (quantified robot-budget consumption first).
6. **Current-main re-verification for M3 + E1-C1** — post-pin fixes: bd413b0eb/#33312 (M3 write path), #33859/#33866 (E1-C1 i18n inliner refactors); verify whether the M3 delete-path + case-guard and the E1-C1 SSR venue survive on main before any filing (no wire access in-lab — operator or a fresh pin update needed).
7. **Chain 5 watch-list (5 triggers)** — a dev-infra action version that reads untrusted checkout content; new workflows using the fork-guard pattern; concurrency-group additions; robot-key scope changes; #33632's resolution status (fix-sweep staleness: if the components fix is swept into angular/cli, the D3 guard sub-claim becomes historical).
8. **Operator severity decisions** — E1-C1 venue-split record (legacy-SSR MEDIUM 6.3 after the E2-B2 correction vs a separate finding; the superseded MEDIUM 6.3 (wave-B corrected) note is in §13), W1 CI-variant severity (Medium?), and the C2D Actions-minute-burn quantification (source-derived vs live measurement).
9. **Chain matrix maintenance** — re-verify plan.md §12 rows against the Wave D outcomes; keep the composite X1-X4 per-shape capability table (composite-as-single-scenario remains killed).



## 14. Wave D planning outputs (2026-08-15) — next phase (angular-cli-next-v1.md)

### Lanes (DR1-02)
context.md is absent at the harness root (template hint only); the authoritative source is `plan.md §13` (read) plus the Wave-B lane verdicts on file. Here is the next-phase lane plan.

## Next-phase LANES (12) — from plan.md §13c residue + Wave-B lane recommendations

| # | Lane | Source residue / recommendation | Owner (primary → gate) | Terminal verdict expected | Dependencies / effort |
|---|---|---|---|---|---|
| N1 | **W1 Windows E2E** — run `WINDOWS-E2E-FIXTURE.md` (registry stub + yarn-classic + `ng add`/`ng update`) on a Windows host; closes the cmd.exe execution rung and makes the CI-token venue (C2D) execution-confirmed | §13c-1 | agent (fixture audit + run-bundle prep) → **operator** (any Windows host; method-2 local) | `resolved` (execution-observed) or `blocked` (no host) | 1 round, no wire; highest-value single artifact |
| N2 | **Wire-2 CI demo (Chain 2)** — private-repo Actions run on a macOS runner proving case-guard root-delete + config-as-data purge; operator-gated at the moment of the act | §13c-2 | agent (spec finalization + cleanup plan) → **operator** (fresh confirmation) | `confirmed` (wire demo) or `blocked` (no confirmation) | 1 round + operator act; spec at payload-proposals/chain2-wire2-spec.md |
| N3 | **Real desktop-client chain demo (Chain 3 closing branch)** — an UNPREPARED agent instance (not the chain authors) following the steered instruction; or documented deployment evidence of a shell-less client with the angular-cli MCP server | §13c-3 + M2 trigger (armed-but-unconfirmed) | agent (blind harness with fresh context; M2-POC's honest-limitation noted) | `confirmed` (H2 demonstrated) or `needs_more_evidence` | 1-2 rounds; closes the C3 ARMED→CONFIRMED gap |
| N4 | **E1-C1 legacy-SSR venue E2E** — full legacy server-bundle build with malicious locale content executing in a real SSR server process (venue-split severity rests on source-verified chain today) | §13c-4 | agent (lab build; no wire) | `resolved` (runtime proof) | 1 round; extends evidence/chain4/ssr-venue/ |
| N5 | **E1-C1 member F compiled demo** — bundle the index-html generator + malicious baseHref → emitted index.html with the injected script (the ECCS-recommended demo; widest-venue member, both builder stacks) | Wave-B ECCS | agent | `resolved` (compiled PoC) | 1 round; filing-relevant (config-trust doctrine counter) |
| N6 | **D3 filing-timing watch + delta-first humanized draft** — monitor #33632 resolution (5-repo cluster) + sweep risk into angular-cli (#32116 on maintainer radar); produce the delta-first writeup (quantified robot-budget first) | §13c-5 + KP-D3 + Wave-B D3RV | agent (draft + watch log) → **operator** (file now; not deferred past next session) | `resolved` (draft) / operator files | 1 round; watch = recurring light lane |
| N7 | **Current-main re-verification (M3 + E1-C1)** — post-pin fixes: bd413b0eb/#33312 (M3 write path), #33859/#33866 (E1-C1 i18n inliner refactors); verify M3 delete-path + case-guard and E1-C1 SSR venue survi

### Round map (DR1-16)
I have the full residue list and chain state. Building the next-phase round map:

# NEXT-PHASE ROUND MAP (N1–N8 × 8 lanes = 64 slots)

**Lane pool (from DR1-02 residue + Wave B additions):**
- **N-A** W1 execution rung — in-lab spawn-string runtime simulation (POSIX approximation of the cmd.exe split, real compiled pin modules) + Windows-E2E run spec finalization (operator-gated host)
- **N-B** Chain 2 wire-2 spec finalization + exact run script (operator-gated at the act)
- **N-C** Chain 3 real-agent closing branch — run the actual pi runtime agent against the steering harness (`findings/M2-mcp-best-practices-roots-escape/evidence/steering-demo/`) to convert H2 from estimate to observation + deployment-evidence branch
- **N-D** E1-C1 legacy-SSR full E2E — real legacy webpack server-bundle build with the malicious locale key → runtime execution (closes the venue-split evidence; severity **6.3 Medium** per the Wave-B corrected vector, superseding the 7.3 figure)
- **N-E** E1-C1 member F compiled demo — `augment-index-html.ts:267-270` `emitRaw` baseHref injection → emitted index.html with injected script (Low-Medium; filing-relevant, both stacks)
- **N-F** E1-C1 member E compiled demo — `i18n-options.ts:258-262` + `createTranslationLoader` translation-path read (Low)
- **N-G** W1 version-check venue + package.json-poisoning compiled proof — `cli-version.ts:63` chain + `updateDependencies` write (W1 family, Low-Medium venue)
- **N-H** Current-main re-verification checklist for M3 + E1-C1 — post-pin fix diffs (bd413b0eb/#33312 write-path; #33859/#33866 i18n inliner refactors) + the exact re-run procedure (filing precondition, operator or pin-update gated)
- **N-I** D3 filing package — delta-first humanized draft (quantified robot-budget first; `payload-proposals/D3-filing-draft.md` as base) + filing sequence (Low, control-integrity)
- **N-J** M2 residual filing package — file-now composition (residual + run_target amplifier + C3 as context; `payload-proposals/`)
- **N-K** D1 filing-opening finalization (`payload-proposals/D1-filing-opening.md`; Low-Medium)
- **N-L** Chain 5 watch-list operationalization — 5 triggers + #33632 tracking note
- **N-M** Operator severity decision briefs — E1-C1 venue-split record (6.3), W1 CI-variant (Medium candidate), Actions-minute quantification
- **N-N** Chain matrix + records maintenance (plan.md §12 rows vs Wave D outcomes)

## Round table

| Round | Lanes (8 per round) | Focus |
|---|---|---|
| **N1** build/demos | N-A sim 

## 15. Next phase lanes (per angular-cli-next-v1.md — Wave D bootstrap)

| # | Lane | Source residue / recommendation | Owner (primary → gate) | Terminal verdict expected | Dependencies / effort |
|---|---|---|---|---|---|
| N1 | **W1 Windows E2E** — run `WINDOWS-E2E-FIXTURE.md` on a Windows host; closes the cmd.exe execution rung AND makes the CI-token venue (C2D) execution-confirmed | §13c-1 | agent (fixture audit + run-bundle prep) → **operator** (any Windows host; method-2 local) | `resolved` (execution-observed) or `blocked` (no host) | 1 round, no wire; highest-value single artifact |
| N2 | **Wire-2 CI demo (Chain 2)** — private-repo Actions run on a macOS runner proving case-guard root-delete + config-as-data purge; operator-gated at the act | §13c-2 | agent (spec finalization + cleanup plan) → **operator** (fresh confirmation) | `confirmed` (wire demo) or `blocked` | 1 round + operator act; spec at payload-proposals/chain2-wire2-spec.md |
| N3 | **Real desktop-client chain demo (Chain 3 closing branch)** — UNPREPARED agent instance following the steered instruction, or documented shell-less deployment evidence | §13c-3 + M2 trigger (armed-but-unconfirmed) | agent (blind harness, fresh context; M2-POC honest-limitation noted) | `confirmed` (H2 demonstrated) or `needs_more_evidence` | 1-2 rounds; closes C3 ARMED→CONFIRMED |
| N4 | **E1-C1 legacy-SSR venue E2E** — full legacy server-bundle build, malicious locale content executing in a real SSR server process | §13c-4 | agent (lab build; no wire) | `resolved` (runtime proof) | 1 round; extends evidence/chain4/ssr-venue/ |
| N5 | **E1-C1 member F compiled demo** — index-html generator + malicious baseHref → emitted index.html with injected script (Low-Medium; both stacks; filing-relevant) | Wave-B ECCS | agent | `resolved` (compiled PoC) | 1 round |
| N6 | **E1-C1 member E compiled demo** — i18n-options.ts:258-262 + createTranslationLoader translation-path read (Low) | Wave-B ECCS | agent | `resolved` (compiled PoC) | 1 round |
| N7 | **W1 version-check venue + package.json-poisoning compiled proof** — cli-version.ts:63 chain + updateDependencies write (Low-Medium venue) | Wave-B W1-ME/W1-CS | agent | `resolved` (compiled PoC) | 1 round |
| N8 | **Current-main re-verification (M3 + E1-C1)** — bd413b0eb/#33312 write-path, #33859/#33866 i18n inliner refactors; verify delete-path + case-guard + SSR venue survive on main | §13c-6 | agent (GitHub API diffs + local pin re-run) → **operator** (pin-update gated) | `resolved` (survive) / `stale` (fixed — filing reframe) | 1-2 rounds |
| N9 | **D3 filing package** — delta-first humanized draft (quantified robot-budget first) + filing sequence; #33632 co-discovery race | §13c-5 + KP-D3 + D3RV | agent (draft) → **operator** (file now) | `resolved` (draft) / operator files | 1 round; watch = recurring |
| N10 | **M2 residual filing package** — file-now composition (residual + run_target amplifier + C3 as context) | Wave-B M2FD | agent → **operator** | `resolved` (package) / operator files | 1 round |
| N11 | **D1 filing-opening finalization** (payload-proposals/D1-filing-opening.md; app-trust scoping) | Wave-B D1FD/D1KP | agent → **operator** | `resolved` | 1 round |
| N12 | **Chain 5 watch-list operationalization** — 5 triggers + #33632 tracking + sweep risk (#32116 on maintainer radar) | §13c-7 + Wave-B D3ME | agent (watch log; recurring) | `maintained` | light, recurring |
| N13 | **Operator severity decision briefs** — E1-C1 venue-split record (6.3 vs 8.1 calculator-variant), W1 CI-variant (Medium?), Actions-minute quantification | Wave-B N-M | agent (briefs) → **operator** (decisions) | `resolved` (briefs delivered) | 1 round |
| N14 | **Chain matrix + records maintenance** — plan.md §12 rows vs Wave D outcomes; rounds N rows; kernel events; cleanup ledger | §13c-9 | agent | `resolved` | continuous |

**Lane pool mapping (N-A..N-N → table):** N-A=N1 · N-B=N2 · N-C=N3 · N-D=N4 · N-E=N5 · N-F=N6 · N-G=N7 · N-H=N8 · N-I=N9 · N-J=N10 · N-K=N11 · N-L=N12 · N-M=N13 · N-N=N14.

```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "Both tables grounded in on-file records: rounds.md N1-N8 x 8 lanes mirror the DR1-16 round map verbatim (plan.md §14, extracted from the DR1-16 lane output); the 14-lane plan.md §15 table maps each N-lane to its source residue (plan.md §13(c) items 1-9, verified at lines 314-330) or Wave-B addition (E1-C1 members E/F from ECCS; W1 version-check venue from W1-ME; M2 file-now from M2FD; D1 opening from D1FD/D1KP), with severity anchors re-verified: E1-C1 legacy-SSR 6.3 Medium corrected vector (findings/E1-C1-i18n-locale-key-escape/REPORT.md venue-split section, superseding E2-R7's 7.3 per E2-B2/ECKP), W1 CI-variant Medium candidate (findings/W1-yarn-classic-disttags-win32/REPORT.md CHAINSTORM AMPLIFIER), D3 budget numbers corrected (issue_labels 7-10 + AI-key, labels 8-12; findings/D3-branch-manager-fork-guard/REPORT.md)."
    }
  ],
  "changedFiles": [],
  "testsAddedOrUpdated": [],
  "commandsRun": [
    {
      "command": "grep -n '## 14' + sed plan.md §14 (DR1-02 lanes + DR1-16 round map)",
      "result": "passed",
      "summary": "next-phase lane pool (N-A..N-N) and N1-N8 x 8 round table extracted verbatim"
    },
    {
      "command": "grep + sed plan.md §13(c) residue list (items 1-9, lines 314-330)",
      "result": "passed",
      "summary": "all 9 residue items confirmed as the source anchors for lanes N1-N14"
    },
    {
      "command": "read /tmp/ir/DR1-16-full.md round table + severity anchors",
      "result": "passed",
      "summary": "N1-N8 lane assignments and the E1-C1 6.3/W1 Medium/D3 file-now anchors confirmed"
    }
  ],
  "validationOutput": [
    "rounds.md N1..N8 rows drafted (8 lanes each, 64 slots total) per the DR1-16 map; plan.md §15 lanes table drafted (14 lanes) with owner/gate/terminal-verdict/effort columns; lane-pool mapping table (N-A..N-N) included; both drafts saved to /tmp/ir/next-phase-rounds-draft.md and /tmp/ir/next-phase-lanes-draft.md for the orchestrator to append"
  ],
  "residualRisks": [
    "Draft rows use 'planned' verdicts by design (the next phase has not executed); the orchestrator fills verdict text as N1-N8 land",
    "N8 current-main verification depends on GitHub API reads or an operator-gated pin update (no wire access in-lab)",
    "Severity anchors will need a final operator confirmation when the E1-C1 finding.json is updated to the 6.3 venue-split vector"
  ],
  "noStagedFiles": true,
  "diffSummary": "Read-only records-writer lane: two markdown table drafts produced (rounds N1-N8 rows + plan §15 lanes table), saved to /tmp/ir/; no engagement files modified",
  "reviewFindings": [
    "no blockers: both tables trace every lane to a verified on-file source (plan.md §13(c) items 1-9, Wave-B lane verdicts, DR1-16 round map) with severity anchors re-verified against the finding REPORTS"
  ],
  "manualNotes": "The orchestrator should append the rounds block under a '## Next phase rounds (N)' header in rounds.md and the lanes table as plan.md §15; the N3 row intentionally lists 'Chain 3 real-agent RUN' in N4 (per the DR1-16 map, the run executes in N4 with the harness built in N1)."
}
```
