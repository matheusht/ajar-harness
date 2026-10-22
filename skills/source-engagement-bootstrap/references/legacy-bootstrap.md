# Existing-engagement source bootstrap

Use this only for a supported existing queue/record engagement or a source task
explicitly assigned to that legacy runtime. The [root legacy procedure](../../../docs/agents/legacy-local-research.md)
and signed target-local scope govern the work. For a new local source task,
return to the [canonical skill](../SKILL.md) and prepare the native route.

## Phase 3 — Bootstrap the legacy engagement

1. Follow `docs/agents/legacy-local-research.md` placement rules: Plane 3 belongs in the selected target's own project repository. Use an existing local source tree when supplied. If only a remote repository is supplied, stop and ask for the intended local checkout path before cloning or creating Plane 3.
2. Reuse an existing `engagements/<id>/`. Copy `engagements/_TEMPLATE/` only when the operator explicitly assigns a new task to this legacy runtime; never overwrite an existing engagement.
3. Verify the existing source identity using the exact commit and eligible release/tag; acquire only missing explicitly authorized source. Record uncommitted source drift. Do not silently switch branches or update dependencies.
4. Create or update only:
   - `engagements/<id>/scope.md`
   - `engagements/<id>/asset-prioritization.md` (or `coverage-matrix.md` for a multi-asset pack, per recent engagements)
   - `engagements/<id>/goal-prompts/<id>-goal-prompt.md` (one per asset for a multi-asset pack)
   - `engagements/<id>/program-policy.md` when the program has published rules to capture verbatim
   - template files for later canonical records and unique recon/cleanup narrative; generated progress remains derived
5. Prepare the frozen corpus manifest/enumeration and its initial-scope digest before signing when budget-bounded completion may be used. Follow the [entry/resume procedure](goal-template.md#entry-and-resume-procedure); initialize only after the exact scope is signed and init's operator-console SSH authority is available, before any recon. Existing engagements require admitted reads, not reinitialization or a manually maintained progress substitute.

## Phase 4 — Draft scope for the complete handoff

Fill every scope field from verified input:

- source-only box and exact source location;
- exact repository, commit/tag, and release eligibility;
- static-analysis and local disposable-build surfaces;
- benign safe signals;
- explicit exclusions;
- escalation ceiling;
- owned accounts/fixtures and concurrency `1` unless explicitly authorized;
- proposed Zone-2 classes and containment, if sufficiently specific;
- cleanup and data-retention rules;
- operator identity and date, with `signed: [ ]` (or `[x]` only if the operator signed inline in-session, per safety rule 3's exception).

Do not begin vulnerability research, run a vuln skill, build the target, or create a PoC until the human signs. Complete the Phase 5 goal draft and readiness facts before presenting the exact file awaiting signature.

## Phase 5 — Generate the long-running goal brief

Before requesting signature, prepare the complete reviewable scope, goal draft and runtime/readiness facts together. Mark launch pending until exact scope signature, authorized kernel initialization and execution readiness are satisfied. Copy the standard scaffold template from `engagements/_TEMPLATE/goal-prompts/`
into `engagements/<id>/goal-prompts/<id>-goal-prompt.md` and fill every `<...>` with verified
engagement facts. Replace `[HARNESS_CHECKOUT]` with the verified absolute harness checkout path in every generated goal reference; verify the copied link resolves from the target repository. If the checkout is unknown, retain an explicit pending placeholder and do not present the goal as launch-ready. Also read prior goal prompts under `engagements/*/goal-prompts/` (excluding
vendored/upstream trees) as style/examples only. Never copy a prior authorization that conflicts with
current root gates.

**Standard scaffold templates (pick by engagement lifecycle):**
- `engagements/_TEMPLATE/goal-prompts/goal-prompt-START.md` — the default for a NEW explicitly legacy engagement.
  Dense, persistence-mode, structured into GOAL / IN / OUT-KILL / BUILD-A-CARD / PIPELINE /
  CASCADING / OPERATING-MODEL / KEY-ROUTING / AUTHORIZATION / FIRST-MOVE blocks. Modeled on the Tron
  engagement's goal prompt.
- `engagements/_TEMPLATE/goal-prompts/goal-prompt-REVISIT-ESCALATION.md` — the default when REVISITING /
  REDOING / RE-RUNNING an already-closed engagement for escalation vectors or an exhaustion check
  ("was it exhausted?", "find the critical escalation, no reward-hacking"). Adds the orchestrator-
  participates / independent-second-reviewer-then-synchronise rule for direction-changing claims,
  re-attack-the-prior-kill-conditions framing, and never-audited-surface-first routing. Modeled on the
  Crown engagement's revisit prompt.
- Long-form structured fallback: `goal-template.md` for engagements neither template fits. Copy only its fenced `markdown` goal body, then substitute the verified `[HARNESS_CHECKOUT]` path. The shared entry/resume procedure stays in the harness reference; do not copy or rewrite it into the target goal.

The template block must, once filled:

- reference `CLAUDE.md`, the signed scope, `engine/whitebox-analysis.md`, persistence, regrade, pocinator, chainability, escalation, cleanup, and the prioritized asset map;
- preserve the Stage 0 → Post progression as a backtracking map, not a waterfall;
- use rules only as cheap prefilters;
- require multiple genuinely independent keep/kill and confirm/refute reviews;
- require verification-of-the-verification against the real, exact in-scope source/build;
- separate signal, adjudication, PoC proof quality, report quality, and operator acceptance;
- use evidence-licensed persistence and bounded exhaustion, not "find a bug at any cost";
- prevent reward hacking, emulator-only proof, unsupported impact, and forced findings;
- preserve every root human gate and the exact independent review obligations;
- prohibit autonomous filing and Plane-1 promotion;
- define exact terminal states and `goal_complete` acceptance criteria.

Preferred model roles are configuration, not fabricated capabilities: a high-judgment model for planning/triage and a persistent coding model for bounded implementation/debugging. Use the operator's requested models only if actually available; otherwise report the mismatch rather than silently substituting.

## Phase 6 — `/goal` handoff

Use a referenced file, not a giant inline goal. The goal file carries full instructions; `/goal` carries only the objective, authoritative paths, budget, gates, and done condition.

Use the operator-selected goal interface only if available; it is not a replacement for the governed queue runner. Example format for clients supporting this syntax:

```text
/goal --tokens <EXPLICIT_BUDGET> Execute the signed, source-only engagement <id>. Read and obey @engagements/<id>/goal-prompts/<id>-goal-prompt.md and @engagements/<id>/scope.md; root CLAUDE.md gates override. Work until its bounded terminal criteria are verified, pause at every required human gate, and call goal_complete only when the goal file's acceptance checklist is satisfied.
```

Adjust the token budget only from an explicit operator preference or a documented corpus estimate. A token budget is not authorization to cross a gate.

## Legacy final response contract

Return, in order:

1. eligible/rejected target summary;
2. ranked repositories and ranked critical assets with evidence/confidence;
3. selected engagement and files created;
4. blockers and the exact human action required, especially unsigned scope;
5. one copyable `/goal` command **only after scope is signed**; before signature, show it as `PENDING — do not run`.

Never state that the engagement is ready while the scope is unsigned, source identity is unfrozen, required safe signals are absent, or the canonical record path is unavailable.
