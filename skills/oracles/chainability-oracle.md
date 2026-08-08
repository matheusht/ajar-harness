---
id: chainability-oracle
type: oracle
description: Does this finding compound with something else into something worse, or is its scope exactly what's already claimed? (angle-driven completeness check)
---

# Chainability oracle — "does this finding compound into something worse?"

Runs at Stage 5 canonically, but just as legitimately as a final sweep after regrade/pocinator before
treating a finding as advisory-ready — this harness's stages are a development progression, not a
waterfall. Regrade re-litigates whether the finding is real; pocinator asks whether a specific PoC
proves the claim; this asks whether the claim's *scope* is complete, or whether something compounds it.
Full doctrine and worked examples: `engine/chainability.md`. This card is the terse, invocable version
for an agent loading it by id mid-run. For driving a *confirmed* finding to its maximum honest impact
(the escalation half — the move-set, the marginal-contribution anti-reward-hack keystone, and a
parametrized escalation goal-prompt blueprint), load `engine/escalation.md`.

## The six angle-shapes (baseline, not closed)

Instantiate each concretely for the actual finding at hand, then check against real code or real
behavior — never reason about an angle in the abstract. This list is a starting baseline, not
domain-limited or closed: add engagement- or finding-specific angles freely whenever judgment says
something might escalate further or might have been missed, whatever the domain. An ad-hoc angle only
gets promoted into this canonical list once it's proven out more than once across separate instances —
extend freely, promote sparingly.

1. **Persistence-of-effect on retry/reentry** — does the triggered effect leave residual state that
   changes what happens next time (corruption, an easier second trigger, a different failure mode)?
2. **Repeatability and backoff** — can the mechanism re-trigger, and does anything rate-limit, ban, or
   cool down the attacker between attempts? Missing backoff is the single highest-yield angle observed
   so far — a one-time effect and a durable, repeatable one are very different severities.
3. **Composition with other findings already surfaced in this engagement** — does this finding's
   vulnerable window overlap with a separately-found mechanism for a combined effect worse than either
   alone? Trace the actual overlap or disjointness in code, don't assume either way.
4. **Population/reach beyond the originally-assumed victim class** — does the precondition apply to a
   narrower or broader population than first stated?
5. **Fan-out/propagation to multiple victims from one attacker action** — can a single crafted artifact
   reach victims the attacker never directly connected to, via gossip, relay, or re-broadcast?
6. **Sibling-pattern recurrence nearby** — does the identical root-cause shape (not just a related
   concern) recur in an adjacent field or code path, providing a second route to the same or a worse
   outcome?

## Verdict set
`bounded` · `amplifier_found` · `new_finding_spun_off` · `needs_more_evidence` · `blocked`

- **`bounded`** — angles close cleanly; scope is exactly what's already claimed. The expected majority
  outcome — a clean `bounded` across several angles is thoroughness, not a sign of insufficient effort.
- **`amplifier_found`** — a real, code-confirmed mechanism makes the *consequence* worse (wider
  durability, broader reach, compounds under repetition) without changing what the base finding is.
  Folds into the existing report's Impact section, doesn't spin off a new finding.
- **`new_finding_spun_off`** — a genuinely distinct vulnerability surfaces, not a downstream consequence
  of the one being checked. Routes to a fresh Stage 0/2 candidate, logged separately — do not fold a
  different root cause into the current finding's narrative just because it surfaced during this pass.
- **`needs_more_evidence`** — an angle is plausible but needs a concrete additional test before closing
  either way; name the specific next step.
- **`blocked`** — genuinely couldn't investigate an angle (environment/infrastructure/artifact
  unavailable) — not a judgment on the finding either way.

No verdict here silently closes anything.

## Scope boundary: not regrade's `escalation_found`

Regrade's `escalation_found` = the original investigation missed direct reach of the identical
mechanism (the finding was under-scoped from the start — a reach question about completeness).
Chainability's `amplifier_found` = the mechanism was scoped correctly, but its downstream consequence
compounds (a consequence question about what happens after it fires once). If an angle turns up
something that looks like the first shape, that belongs to regrade, not this oracle, even if it
surfaced during a chainability pass.

## Fresh eyes: strong recommendation, not a hard gate

Unlike regrade's absolute zero-prior-investment requirement, a single chainability pass with full
context can close angles correctly. But an independent second pass on the same finding has, in
practice, found real angles the first pass didn't think to check — recommend a second, fresh pass on
any high-value finding, especially before treating it as advisory-ready, without treating it as a
non-negotiable the way regrade's freshness requirement is.

## When required

Run at least once on any finding before treating it as advisory-ready, regardless of where in the
pipeline that ends up happening. A second, independent pass is worth the cost on any high/critical
candidate specifically.
