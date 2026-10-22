---
name: source-engagement-bootstrap
description: Rank authorized source targets and prepare a native local research handoff. Existing queue/record engagements use the linked legacy branch. Source-only; explicitly invoked.
disable-model-invocation: true
---

# Source Engagement Bootstrap

Use this skill only when explicitly invoked with `/source-engagement-bootstrap <scope-file> [operator preferences]`, Pi's `/skill:source-engagement-bootstrap`, or the Skill tool. This canonical procedure uses root policy and the native guide; the legacy template is reached only through the named existing-work branch.

For a **new local source task**, rank the source, prepare one target-local scope
and native brief, then follow the [native entry](../../docs/agents/native-local-research.md)
for the current prepare/start/resume/stop interface. This source branch implements
the proposed #166 default; #165 remains open and qualification is unverified.
Actual runs still require a signed scope, plan-bound approval and supported
runtime; an unqualified result cannot be called adopted. Do not silently fall
back to a queue task because native
qualification is unavailable. A supported existing queue/record engagement follows the
[legacy branch](references/legacy-bootstrap.md) instead.

## Non-negotiable authority and safety

1. Read the repo root policy `CLAUDE.md` (mirrored as `AGENTS.md`), the current target policy and scope, and the [native entry](../../docs/agents/native-local-research.md) before preparing a new task. Root policy wins over this skill. For an existing queue/record task, read the [legacy branch](references/legacy-bootstrap.md) and its referenced engine docs.
2. Accept **source code only**: a local source tree or an authorized repository URL with a branch/tag/commit that can be frozen. Reject live applications, production hosts, browser targets, API-only targets, binaries without corresponding source, and entries whose authorization cannot be established. Ranking/repository inspection is offline source triage; do not contact or probe an application.
3. Never claim to be the human operator or fabricate a scope signature. Fill the scope completely, record the proposed operator identity, leave its `Signed: [ ]` block pending, and stop at the scope gate. Resume only after the human signs it. An operator may explicitly sign inline in-session; then record their stated identity, date, and `[x]`, quoting that instruction. The agent still never invents a signature.
4. Convert operator intent into exact proposed artifact classes, environment, accounts, containment, expiry and cleanup requirements. Before creating a Zone-2 PoC artifact, require fresh human confirmation or an explicit standing local-PoC grant in the current signed scope that the record kernel enforces (`CLAUDE.md` §1 gate 3). The `chia-blockchain` child may use that grant for contained local PoCs and necessary local experiments. Record each artifact and cleanup obligation at creation; effects beyond signed environment, containment, or cleanup authority require human confirmation. A native route without the kernel does not inherit that grant.
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

## Phase 3 — Prepare one native handoff for new local source research

1. Put `engagements/<id>/scope.md` in the selected target's own repository.
   Record the exact source identity and eligible release, local environment,
   authorized surfaces and benign objectives, exclusions, safe-signal cards,
   effect and escalation ceiling, accounts, expiry, cleanup authority, and
   operator identity. Prepare a signed-scope review; only the operator signs.
   The legacy `_TEMPLATE/` contains queue/kernel fields and is not copied into
   a new native run. Ranking and a draft scope never authorize execution.
2. Prepare a separate native brief with the target and objective, a falsifier,
   exact source, allowance, stop conditions, optional reference/tool files,
   independent capture needs, and chosen fresh review behavior. Keep the
   persistent private run root outside `engagements/<id>` and outside the source
   tree. Match the actual supported target/model/transport and capture class in
   `tools/native_research.py prepare --help`; an unsupported class is a blocker,
   not an invitation to infer that a generic adapter exists.
3. Follow the [native guide](../../docs/agents/native-local-research.md) for
   `prepare`, plan inspection, plan-bound approval, `start`, `research`, `resume`,
   `review`, `status` and `stop`. The guide owns their detailed sequence. Before
   any run, require the signed scope, benign `safe_signal` for every used
   vulnerability card, exact plan-bound approval, and runtime/independent-capture
   readiness. Record the #165 qualification/adoption status without treating
   source implementation as that decision. Until actual run requirements exist,
   return the proposed paths and blockers, with `start` marked pending. A native
   route without the record kernel never inherits a kernel-enforced standing
   local-PoC grant; Zone-2 creation needs fresh human confirmation.
4. Return ranked source evidence, the selected target and prepared scope/brief
   paths, the exact unresolved authorization/runtime facts, and the `prepare`
   command only when its inputs are fixed. Do not generate a legacy `/goal`
   brief, initialize the queue or record kernel, or treat native output as an
   external filing.

## Existing queue/record work

For a supported existing engagement, or a task explicitly assigned to the
legacy runtime, use the [legacy bootstrap](references/legacy-bootstrap.md).
Its scope, entry/resume checks, goal prompt, admitted readers and historical
record path remain available. This branch is named, not the fallback for new
local source research.
