# 0015 — Initial signed authority for autonomous internal research

**Status:** Accepted policy and caller-routing decision, 15 November 2026.
The operator explicitly requested completion of the autonomy policy and caller
migration in the `technical oslit` chat: no repeated human review or renewed
signatures for Zone-2 artifacts already authorized at the start. Pricing, CI and
the operator's fresh-target research test are excluded from this change.

## Authority once, enforcement throughout

A new v2 scope can select `authority_policy: "initial-scope-v1"`. The operator
signs that scope once, including its effects, resources, environments, accounts,
network destinations, escalation ceiling, limits and cleanup authority. Preparation,
research, review, recovery and resume use those same immutable signed bytes.
There is no per-artifact confirmation token, second setup approval, renewed
signature on resume, or human approval between already authorized internal rungs.

Artifact content is not a permission taxonomy. Inside an explicitly authorized
owned laboratory, every artifact type is covered by that laboratory's composite
state grant: programs, probes, generated files, working copies, processes, and
contained impact demonstrations. Their lifecycle is registered before allocation;
published evidence names and hashes material contents. A new filename, technique,
or Zone-2 classification does not create another operator gate.

`owned-lab-state-v2` covers the owned tool/client lab across source, binary,
application and combined access. It does not authorize mutation of a remote
application merely because that application's ID is among the lab's resources.
`owned-application-state-v1` separately covers an explicitly owned application
and its declared state volumes. Every effect still needs its matching execution,
target or reset permission. Unsupported ownership or cleanup is a capability gap;
an extra confirmation does not make an unenforced path safe or implemented.

Independent agent review remains mandatory where the evidence protocol requires
it. The controller admits the next signed internal rung only after the predecessor
succeeds and its exact evidence receives current independent review. Changed
evidence invalidates that review. This is agent work, not an operator approval queue.

Authority expansion still needs the operator: a new resource, account, destination,
effect, ceiling or cleanup responsibility is outside the initial grant. External
filing, disclosure, contact, publication, deployment and merge remain separate
actions. Operator stop, expiry, revocation, unknown effects and cleanup holds remain
enforced. This policy does not grant a research engagement or execute a target.

Scopes without this policy retain their original gates. Existing scope files,
signatures, journals and frozen guidance are not rewritten or upgraded in place.
The v1 artifact class retains its source/binary semantics. The new policy is selected
in the initial scope, before its one signature, not inserted midway through a run.

## One entry for new work; explicit compatibility for old work

`tools/native_engagement.py` is the public entry for new v2 work. Its default help
and unreadable/unknown-input path use v2. Only an explicitly recognized v1 input
or a state-only v1 engagement selects the old driver. A conflicting root refuses;
neither route falls back after a failure. Both `--flag value` and `--flag=value`
forms preserve this selection.

| Caller | Disposition |
| --- | --- |
| Root README, AGENTS/CLAUDE, source bootstrap and Pi discovery | New work enters the v2 guide and initial signed contract. Old plan-bound approval instructions are retired from this default path. |
| `native_engagement.py` → controller/runner → native boundary | Sole v2 orchestration, authority and journal path. |
| Codex/OMP adapters, environment/network/lease owners | Retain execution, enforcement and observed receipts; they do not own another engagement state machine. |
| `native_research.py`, `native_setup_builder.py`, `native_continuation.py`, `native_closeout.py`, old provider gateway | Retain for explicit v1 inputs/records. They are not duplicate v2 controllers and are not deleted to make migration appear larger. |
| `native_patch_check._apply`, runtime/credential helpers | Retain reused effect primitives; a helper import does not import the v1 authority workflow. |
| Queue/kernel writers, historical readers and evidence | Retain for their own contracts. No history conversion, deletion or regrading. |

This supersedes the unconditional per-artifact/operator-rung gates only for the
explicit initial-scope v2 policy. It completes policy adoption and default caller
routing, not physical runtime qualification, multi-day operation, or research
acceptance. The [contract](../research/oslit-v2-contract-2026-11-14.md) defines
fields and enforced ownership; the [operator guide](../agents/engagement.md) owns
the workflow.
