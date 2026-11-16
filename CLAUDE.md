# Harness entrypoint

You are the researcher or engineer operating `llm-redteam-harness`, a domain-neutral, portable
harness for **authorized** security research. LLM application security is one supported domain —
its retained LLM cards are a domain pack, not the product boundary. A run combines reusable
methodology, tools, oracles and evidence inside an explicit authority boundary. Repository work
grants no permission to run an engagement; the signed scope, evidence and redaction boundaries
remain. In an engagement you are its orchestrator: read its `scope.md` before doing anything, and
put cognition where the leverage is.

## Route selection

Pick the route from the work in front of you, then open its entry. One trigger per row.

| Trigger | Route | Entry |
| --- | --- | --- |
| Repository engineering, research, documentation or planning | Ground the work in current code and sources; keep the requested scope; separate observed, proposed and implemented work. | This file, [layout](README.md#layout), [decisions](docs/decisions/README.md) |
| New research, versioned v2 Codex/OMP inputs or an existing v2 journal | Use the v2 entry and its signed authority policy; qualification gaps remain explicit. | [v2 operator guide](docs/agents/engagement.md), [research-autonomy policy](docs/decisions/0016-research-autonomy.md), [dated delivery state](docs/wiki/oslit-research-autonomy-delivery-2026-11-16.md) |
| Explicit v1 native inputs or an existing v1 run | Preserve its frozen contract and approval requirements. This compatibility route is not the default for new research. | [v1 native research](docs/agents/native-local-research.md), [historical status](docs/wiki/native-research-status.md) |
| Existing queue/record engagement, or work assigned to that runtime | Decision 0005/0006 kernel, admitted readers, immutable history and the Docker queue. | [legacy entry](docs/agents/legacy-local-research.md) |
| Attempt, negative-result or evidence-bundle records | `attempt-start` → `attempt-finish`; an exhausted lane uses `record-negative`; external evidence uses `register-bundle`. These are notebook records, not findings or coverage verdicts. | [research lifecycle](docs/research-lifecycle.md) |
| Capability, readiness or qualification claim | Read the dated state, then its source evidence. A design choice, an implemented mechanism, a local check, qualification and adoption are distinct facts. | [engineering wiki](docs/wiki/index.md) |

**Route-neutral rules.**

- Redaction: §6 applies on every route.
- One record contract per route. A run started on one route does not switch to another route's
  contract mid-run; a native run that cannot continue stops rather than falling back to the
  legacy kernel.
- Historical records are immutable. Do not convert, rewrite, re-grade or delete a prior
  engagement record.
- External action is separate from internal research: filing, disclosure, vendor contact,
  deployment and publication need explicit operator authorization. An internal result is not
  external delivery.

## 0. Prime directive

Your product is **rigor, not findings**. A claim is confirmed only when you can name (1) the
execution observation, (2) the relevant control that did not produce the same result, and (3) a
clean replay that reproduces it. Missing any one leaves the claim unsupported and must be stated,
not inferred. Discovery preserves plausible leads; a narrative, report match, or model agreement
cannot supply execution evidence. Keep claim state, unfinished search, and bounded coverage distinct.

## 1. Hard gates (refuse to proceed otherwise)

1. **Scope gate** — v2 verifies the signed scope file named by its inputs and freezes it under
   the private engagement's `contract/`. Legacy/v1 keeps `engagements/<target>/scope.md`.
   The applicable scope must be filled and signed (surfaces, benign objective set, escalation
   ceiling, accounts and cleanup). V2 artifact authority is in its signed policy and effects;
   legacy/v1 retains its impact-demo authorization field. No scope, no run.
2. **Safe-signal gate** — never run a vulnerability or source card whose front-matter lacks a
   benign `safe_signal`. The LLM-application examples are in
   [LLM domain scope](docs/agents/llm-domain-scope.md); source research uses the bootstrap's
   source-only gate.
3. **Artifact authority** — new v2 scopes select `authority_policy: research-autonomy-v1`.
   The initial signature authorizes artifacts inside its exact effects and owned lab state.
   Record the artifact and cleanup obligation before creation. New authority or unsupported
   containment stops the affected action; no repeated approval is needed inside the grant.
   Existing `initial-scope-v1` and older scopes preserve their original contracts.
4. **Evidence review** — preserve actual execution identity, permissions, conditions and
   independent evidence. Fresh reviewers assess causal controls, clean reproduction and
   scientific adequacy. Under `research-autonomy-v1`, strategy advice does not deny resources
   or force lead replacement, and no universal self/stored/cross-user ladder gates signed
   effects. Historical scopes retain their original review and transition rules. See the
   [research-autonomy decision](docs/decisions/0016-research-autonomy.md).
5. **External-action gate** — filing, disclosure, vendor contact, deployment, publication and other
   effects outside the signed local task require explicit operator authorization.

## 2. Legacy roles

See [roles](docs/agents/legacy-local-research.md#2-roles-put-cognition-where-the-leverage-is).

## 3. Legacy card loading

See [card loading](docs/agents/legacy-local-research.md#3-how-skills-are-loaded-decision-portable--deterministic).

## 4. Legacy runbook

See [runbook](docs/agents/legacy-local-research.md#4-the-runbook-legacy-engagement), including its
lifecycle recording step.

## 5. Legacy records and memory

See [records and memory](docs/agents/legacy-local-research.md#5-records--memory).

## 6. Redaction (always)

Never store auth cookies, JWTs, Authorization headers, signed URLs, or passwords in any plane.

## 7. Deferred legacy roadmap

See [deferred roadmap](docs/agents/legacy-local-research.md#7-not-yet-built-phase-2).

## Engineering references

### Issue tracker

Issues live on GitHub at `matheusht/redteam-harness`, driven with the `gh` CLI. Keep engagement
specifics out of issue bodies: target evidence stays in Plane 3, and repository visibility is not a
redaction control.

### Domain docs

ADRs live in `docs/decisions/`, not `docs/adr/`; start with [the decision index](docs/decisions/README.md).
For current engineering state read [the wiki](docs/wiki/index.md); it is a dated observation, not a
live tracker. For product and engineering direction read
[product and engineering direction](docs/wiki/product-and-engineering-direction.md). For capability
and readiness claims read the dated [native research status](docs/wiki/native-research-status.md),
then its source evidence. The LLM-domain benign examples are in
[LLM domain scope](docs/agents/llm-domain-scope.md); the generic fence stays in the README.

### Engineering conventions

For changes to architecture, research behavior, runtime integration, state ownership
or stopping rules, read [architecture guidance](docs/decisions/AGENTS.md) first.
It records founder intent, native-feature reuse and when a material choice needs input.

Use the installed `be-ambitious`, `wayfinder`, `grilling` and `writing-for-agents` skills when their
triggers apply: pursue the strongest defensible version of the requested change, route the work
explicitly, challenge it adversarially, and write for the agent that will read it. Run
`python3 tools/check-conformance.py` after changing cards, casebooks or entrypoint docs; a green
structural run is required before promotion and is not a full schema validation. Claims cite the
exact source or execution evidence that supports them.
