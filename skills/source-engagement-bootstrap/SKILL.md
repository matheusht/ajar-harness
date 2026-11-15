---
name: source-engagement-bootstrap
description: Rank authorized source targets and prepare a native local research handoff. Existing queue/record engagements use the linked legacy branch. Source-only; explicitly invoked.
disable-model-invocation: true
---

# Source Engagement Bootstrap

Use this skill only when explicitly invoked with `/source-engagement-bootstrap <scope-file> [operator preferences]`, Pi's `/skill:source-engagement-bootstrap`, or the Skill tool. This canonical procedure uses root policy and the native guide; the legacy template is reached only through the named existing-work branch.

For a **new local source task**, rank the source, prepare private v2 inputs, and
follow the [engagement entry](../../docs/agents/engagement.md). Its initial signed
scope selects standing internal authority; no separate setup or per-artifact
approval is required inside that grant. Existing v1 native runs follow their
[compatibility guide](../../docs/agents/native-local-research.md); existing
queue/record engagements use the [legacy branch](references/legacy-bootstrap.md).
A missing runtime capability is a blocker, never a fallback to another contract.

## Non-negotiable authority and safety

1. Read the repo root policy `CLAUDE.md` (mirrored as `AGENTS.md`), the current target policy and scope, and the [v2 entry](../../docs/agents/engagement.md) before preparing a new task. Root policy wins over this skill. For an existing queue/record task, read the [legacy branch](references/legacy-bootstrap.md) and its referenced engine docs.
2. Accept **source code only**: a local source tree or an authorized repository URL with a branch/tag/commit that can be frozen. Reject live applications, production hosts, browser targets, API-only targets, binaries without corresponding source, and entries whose authorization cannot be established. Ranking/repository inspection is offline source triage; do not contact or probe an application.
3. Prepare exact unsigned inputs; the operator supplies the trusted initial cryptographic signature described in the v2 guide. A checkbox, agent statement or inline note is not that signature. Reuse a valid existing signature over the same bytes; never sign on the operator's behalf.
4. Select `authority_policy: initial-scope-v1` and the exact owned-lab artifact/effect grants before the initial signature. Every artifact type inside those effects and ownership boundaries is preauthorized, including Zone-2. The host records composite state and cleanup before allocation; independent agents review consequential evidence and already signed escalation. No repeated human confirmation, setup approval or signature is needed. Missing authority or unsupported ownership blocks the affected effect; it cannot be repaired by silently widening scope.
5. Never authorize or perform production exploitation, cross-user reach against systems you do not own, real-value loss, destructive writes, persistence outside a disposable owned environment, real secret access, real credential use, public disclosure, filing, deployment, or supply-chain publication. "Does not impact other users" does not waive scope, Zone-2, cleanup, or filing gates.
6. Models and tools are proposal/review sources, not oracles. Operator priors can increase search effort but cannot establish truth. Do not fabricate findings, controls, reachability, exploitation, source identity, coverage, or independent review.
7. Multiple graders must mean genuinely independent model runs/sessions or a human review. Never simulate a panel by asking one model to role-play several experts. If independent execution is unavailable, record that limitation and keep the candidate alive or route it to human review.

## Phase 1 — Intake and eligibility

1. Resolve the provided path relative to the repository. Accept CSV/TSV, JSON, or Markdown. For CSV/TSV, run:

   ```bash
   python3 skills/source-engagement-bootstrap/scripts/normalize_targets.py <input>
   ```

2. Preserve all supplied policy/scope fields. Map equivalent headings, but never invent missing values. Useful fields include target/repository, local source path, program, scope status, branch/tag/commit, release eligibility, bounty tier, policy URL or local policy file, exclusions, test restrictions, and notes.
3. Produce an eligibility table with `eligible | blocked | rejected`, exact reason, source locator, identity status, and authorization evidence. Missing source, ambiguous authorization, or live-only scope is blocking—not a low score.
4. If materially necessary information is missing, ask at most three narrow questions. Otherwise proceed with explicit unknowns.

## Phase 2 — Rank repositories and critical assets

Load [references/asset-ranking.md](references/asset-ranking.md). Inspect direct source and program policy; generated graphs and automated scanners are supporting evidence only. Do not execute target code before signed scope and environment preflight.

Rank at two levels:

1. **Target/repository priority** across eligible entries.
2. **Critical asset priority** inside the selected repository: privileged entry points, parsers, protocol boundaries, authentication/authorization, update/plugin systems, deserialization, request routing, filesystem/process/network sinks, money/state transitions, and cross-tenant boundaries.

For every score, cite the source path, symbol/config, and policy fact that supports it. Unknown factors remain unknown. Select the highest evidence-backed target unless a material tie or missing authorization requires human choice.

## Phase 3 — Prepare one v2 handoff

1. Copy the [source input example](../../examples/native-engagement-v2/source/inputs.json)
   into a private durable directory outside the target repository and future run root.
   Prepare its scope, goal, runtime and environment references using the
   [operator guide](../../docs/agents/engagement.md#fill-and-sign-the-inputs).
   Freeze the exact source identity, authority, limits and cleanup responsibilities.
   The signed initial policy grants owned lab state, separate execution effects,
   and the intended internal escalation ceiling; artifact contents are not enumerated.
2. Resolve every placeholder and obtain the initial trusted operator signature.
   Supply the target and goal, useful falsifiers and available access. The agent owns
   subsequent setup and experiment choices; a target build recipe is optional.
3. Run `python3 tools/native_engagement.py inspect --inputs /private/inputs/inputs.json`.
   Fix reported prerequisites within the authorized engineering scope. Start with
   `run --inputs ... --engagement-root ...`; use `resume` for an existing v2 root.
   The guide owns status, direction, stop and export. Record verification limits.
4. Return the ranked source evidence, prepared input paths and actual readiness or
   blockers. Do not generate a v1 plan/phase approval, initialize a queue/kernel,
   rewrite existing records or treat internal completion as an external filing.

## Existing queue/record work

For a supported existing engagement, or a task explicitly assigned to the
legacy runtime, use the [legacy bootstrap](references/legacy-bootstrap.md).
Its scope, entry/resume checks, goal prompt, admitted readers and historical
record path remain available. This route is named, not the fallback for new
local source research.
