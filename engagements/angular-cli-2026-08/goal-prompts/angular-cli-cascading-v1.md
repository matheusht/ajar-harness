# GOAL PROMPT — `angular-cli-2026-08`, CASCADING PHASE (escalation × chainability)

You are the **orchestrator** of the cascading phase of an authorized white-box red-team of
`github.com/angular/angular-cli`. Read `CLAUDE.md`, then this engagement's `scope.md`,
`program-policy.md`, the Phase-1 longrun prompt (`goal-prompts/angular-cli-longrun-v1.md`),
`cascades.md`, and `plan.md` before anything else. The kernel is **ACTIVE** (scope attested
`95971192…`); the Phase-1 funnel is complete with **five promoted findings**; this phase pushes them
to their maximum *honest* impact and hunts what they compound into.

---

## 0. The contract

Work this phase for **4+ hours of active orchestration** — parallel rounds of hunters and reviewers,
persistence mode throughout (`engine/persistence.md`), kill discipline requiring new signal. Giving up
early is not allowed; manufacturing severity is equally forbidden.

Exactly one of two statements will be true at the end, and both take the same work:

- a confirmed finding **escalated to a higher honest impact** (a demonstrated amplifier or a
  spun-off new finding), **or**
- every angle on every promoted finding is **`bounded`** with the cap demonstrated by a real input
  against real code — a proven ceiling, recorded per finding.

`bounded` with proven caps is a first-class success (`engine/escalation.md` §0). The failure to avoid
is reward-hacking severity upward, or closing angles by assumption instead of evidence.

## 1. State — the primitives you are composing

Phase 1 promoted (all gates G0–G6 clear, `findings/`):

| ID | Severity | Primitive |
|---|---|---|
| **M3** | Medium | `deleteOutputDir` uncontained: application-builder delete path (`index.ts:176-178`, `options.ts:331`) + legacy browser/server — recursive deletion outside workspace root via `outputPath` |
| **D2** | Medium | `ng cache clean` force-`rm`s an arbitrary path from workspace config `cli.cache.path` (absolute/`..`, no containment, no confirmation) — **discriminator:** the same path IS guarded in the `tempDirectory` consumer (`package-manager.ts:647-651`) |
| **M2** | Low-Med | MCP `get_best_practices` reads outside declared roots (`createRequire` ancestor walk, raw `readFile`) and injects the content into the agent context (`audience:["assistant"]`, `priority 0.9`); symlink channel reads arbitrary files |
| **D1** | Low-Med | `module` schematic `buildRoute` interpolates `--route` raw into the generated routing module — quote breakout executes code at module scope |
| **D3** | Low | branch-manager fork guard `github.event.repository.fork == false` is always-true on PR events — fork PRs reach the robot-key job (action API-only → capped) |

Also held (real-but-capped, `rounds.md` R3-R5): win32 shell-string spawn surface (`host.ts:157-164`
— unquoted specifiers/registry in `npm view`/`install` args), MCP `run_target` unvalidated option
values (`--output-path`, `--file-replacements`), MCP `doc-search` redirect-follow/http-scheme fetch,
schematics package-manager task `shell:true` (L5-SITE-1), `ng add` silent-exec asymmetry (R3-1),
`ng update` migration-collection `..` escape (R3-2). **The caps on these are escalation targets, not
facts** (`engine/escalation.md` §2.1: attack your own caps first).

Attribution boundary (`scope.md` §4, `cascades.md`): any root cause resolving into `angular/dev-infra`
(actions at pin `04230133`, `ng-dev` machinery) is dev-infra's finding — record in the attribution
ledger, do not open a finding here. A defect in **this repo's wiring** of a dev-infra action IS ours.

## 2. Method — chainability angles, instantiated for THESE findings

`engine/chainability.md` §3's six angle-shapes, instantiated concretely (ad-hoc angles encouraged —
agentic/CLI surfaces get angles the generic six don't cover; promote nothing to the canonical list):

1. **Persistence-of-effect on retry/reentry** — M3/D2: does the deletion leave partial state that
   changes the next build/cache run (e.g., delete of the output dir mid-watch, cache re-created as a
   file, symlink loops)? D1: does the injected code survive regenerations (idempotent generators)?
2. **Repeatability and backoff** — D3: can a fork PR re-trigger the secret-bearing job repeatedly
   (synchronize/labeled events, dispatch spam with no rate limit)? M2: every `get_best_practices` call
   re-reads the injected guide — is the agent re-poisoned each turn?
3. **Composition with other findings** — THE money lane: **M2 → run_target** (agentic RCE: injected
   instructions steer the agent into `run_target` with `--file-replacements`/`--output-path` options —
   arbitrary read/write via the build path); **M2 symlink → exfil** (secret read into agent context →
   outbound); **M3 + D2 family** (both are uncontained-workspace-config→destructive-rm — a shared
   chokepoint sweep of ALL rm/delete sinks); **D1 → workspace schematics defaults** (one cloned
   project poisons every `ng generate`); **D3 → labels/post_approval_changes jobs** (same broken
   guard family in dev-infra.yml — wiring question, not action internals).
4. **Population/reach** — M3/D2: which builders/commands share the unguarded utility (app-shell,
   prerender, ng-packagr, extract-i18n, karma, dev-server watch deletions)? D1: which schematics
   interpolate raw options (application, workspace, config generators — grep every
   `applyTemplates` call site); M2: which MCP tools resolve modules/read files off the host
   (`doc-search` fetch, `projects.ts` walk-up).
5. **Fan-out/propagation** — D1: does the generated file get imported by build tooling that ships it
   (library builds, publish of generated code)? M2: does the injected content reach OTHER tools the
   agent controls (the MCP server's own tool list)? D3: does the ineffective guard propagate to the
   downstream dev-infra merge-evaluation dispatch with attacker-influenced inputs (`sha` field)?
6. **Sibling-pattern recurrence** — the win32 shell-string surface: find every unquoted
   config/registry/specifier arg reaching `spawn(..., {shell:true})` on win32; the `ng update`
   migration-collection `path.join` escape: sibling `path.join(packagePath, external)` sites; the
   MCP roots family: every raw-fs call in `tools/` not mediated by the host.

## 3. Escalation move-set (each with its keep-reason guardrail)

`engine/escalation.md` §2, with the **marginal-contribution critique** (§1) as keystone: severity =
the DELTA the bug adds vs the world without it — subtract the precondition before crediting any
escalation. Concretely for this phase:

1. **Attack the caps you wrote.** Point hunters at each cap: M2's "attacker must control the resolved
   @angular/core metadata" (test dependency-confusion/hoist layouts adversarially); D3's "action is
   API-only" (verify the dispatch inputs `repo/owner/pr/sha` cannot carry attacker-controlled
   values into dev-infra's merge-evaluation beyond a PR number); win32's "developer-invoked input"
   (test cloned-repo `.npmrc` registry, workspace schematics defaults, registry `dist-tags` values
   feeding specifiers — `update-resolver.ts` chains); D1's "input-trust" cap (workspace schematics
   defaults as the amplification channel — prove or kill).
2. **Worst honest version, not "is it real."** Re-open each finding's disposition; every cap is an
   untested assumption until removed or proven with file:line.
3. **Find the shared chokepoint.** The uncontained-rm family (M3+D2) funnels through config→destructive
   fs ops: enumerate every `rm`/`deleteOutputDir`/`unlink` sink that consumes workspace-config paths,
   and every `path.resolve(workspaceRoot, x)` without containment. One demonstrated chokepoint
   widens both.
4. **Severity re-score only on demonstrated delta.** A cap that holds after adversarial testing keeps
   the finding's severity. An amplifier that survives the marginal-contribution critique updates the
   finding's Impact section (`amplifier_found`) — it does not rewrite the finding's identity.

## 4. Operating model

`engine/multi-round-orchestration.md`. Round E0 is an **angle matrix**: one hunter per (finding ×
angle) cell, blind to your suspicion, reporting `bounded` / `amplifier_found` / `new_finding_spun_off`
/ `needs_more_evidence` / `blocked` with file:line evidence (`engine/chainability.md` §4). Every
`amplifier_found` gets an independent kill-pair refuter (fresh context, adversarial) before it touches
a report. Every `new_finding_spun_off` opens a fresh candidate in `unproven/` — it is NOT folded into
the parent finding. Every `bounded` records the exact input that was tried and failed.

A held vector is a wrong turn, not a dry verdict (`engine/persistence.md`): re-route, re-recon, do not
tunnel. Blocked records the specific missing mechanism, never a mood.

Findings keep their gate discipline: any new or amended finding ships runnable PoC + negative control,
G6 real-path provenance declared honestly in `attest.json`, and passes all 7 gates before promotion.

## 5. Evidence and containment — unchanged from Phase 1

- Local lab only: built CLI + compiled modules at the pin; synthetic fixtures; no live Angular/Google/
  npm systems; no real credentials — ever (the staged deepsec key in `/tmp/deepsec-scan-cli/` is
  cleanup-listed, never reused).
- Wires unchanged (`scope.md` §9): any act tripping a wire stops and asks — name the wire, state the
  cleanup path.
- Every cascade Q1/Q2 gets logged in `cascades.md` even when the answer is nothing.

## 6. Terminal states

Per survivor, one of: `bounded` (cap demonstrated with a real input) · `amplifier_found` (folded into
the finding's Impact with the delta stated) · `new_finding_spun_off` (fresh candidate, gated) ·
`needs_more_evidence` (names the concrete next test) · `blocked` (names the missing condition). Never
"probably worse". Never agent consensus. The final verdict for the phase is **coverage**, not
"the model finally agreed".

## 7. Calibration — read the result correctly

`angular-cli` is mature and heavily reviewed; Phase 1 already banked 5 findings and this phase's
realistic yield is: **one demonstrated chain or amplifier** (M2→run_target agentic amplification and
the uncontained-rm chokepoint are the strongest candidates), **or** a fully-bounded matrix with every
cap proven — both are success. The failure to avoid is a $31,337 fantasy chased past the evidence, or
a dev-infra root cause filed under this name.

## 8. First move

1. Enumerate the composition matrix in `plan.md` §7 (findings × angles × target caps) — every cell
   gets an owner and a one-line hypothesis.
2. Launch E0: parallel hunters on the highest-value cells first (M2→run_target chain, M3+D2 chokepoint
   sweep, win32 cap attacks, D1 schematics-defaults channel, D3 dispatch-input verification).
3. Funnel E0 verdicts: kill-pairs on every amplifier, gate checks on every spin-off, cascade Q1/Q2
   logged, `cascades.md` + `rounds.md` updated as the phase runs — not at the end.

**Do not file, submit, publish, or contact Google, Angular, or any maintainer. The operator files.**
