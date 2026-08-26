---
id: pattern.dag-old-dag-rule-gating
name: Old-DAG Rule Gating — upgrade-gated validation bypass by time-travel attachment
description: >
  A validation rule is gated on the main-chain height (last_ball_mci >= constants.X) so it only
  applies to units attached to the "new" part of the DAG. An attacker attaches a unit to an OLD part
  of the DAG (below the gate MCI), or crafts a unit with no ball, so the rule never fires — a
  time-travel variant of the legacy-route differential. DAG-specific: the unit is validated against
  the height of ITS position, not the current height.
type: pattern
owasp: "A01 Broken Access Control — rule-version gating / time-of-attach vs time-of-check"
also: "DAG/DLT consensus — validation asymmetry"
atlas: "—"
routes_to: ["stub:dag-dlt-vuln-cards"]

activation:
  strong:
    - "validation code contains `last_ball_mci >= constants.<X>` gates that skip or relax checks below an upgrade height"
    - "a check uses `objValidationState.last_ball_mci` (or similar position-derived height) instead of an unconditional rule"
    - "recent commits add `|| !hasBall && getMinRetrievableMci() >= X` disjuncts to existing gates — the team is mid-migration, missed rules are live"
    - "a unit's validity depends on where in the DAG it is attached, and the attachment point is attacker-chosen"
  weak:
    - "any `constants.*Mci` comparison in validation.js / formula/validation.js / aa validation"
    - "upgrade flags (`pemCurvesFixMci`, `noPrivateAssetsWithConditionsUpgradeMci`, ...) used as rule gates"
    - "catchup or network paths that accept units whose position is below the current min retrievable MCI"
  negative:
    - "every upgrade-gated rule also carries the `!hasBall && minRetrievableMci() >= X` disjunct (the migration is complete for that rule)"
    - "the rule is unconditionally enforced regardless of position"
    - "attachment-point height is not attacker-controllable (unit must extend the current tip)"
---

# Old-DAG rule gating

> **Activation vs adjudication.** Presence of a `last_ball_mci >= constants.X` gate is a **strong**
> signal on sight — the question is whether the gate is bypassable (unit attachable below it) and
> whether the skipped check matters (a fund rule, a signature rule, a cap). Guilty until the
> disjunct is shown present.

**Idea.** DAG ledgers validate a unit against the height of the position the unit *claims* (its
parents' balls), not the node's current height. Rules introduced at an upgrade MCI are therefore
often gated on `last_ball_mci >= upgradeMci` — fine for honest units (they extend the tip), but an
attacker can attach a malformed unit to an *old* part of the DAG where the gate is false, skipping
the new rule. The defense pattern is the disjunct `|| (!hasBall && getMinRetrievableMci() >= X)`:
enforce the new rule whenever the *network* has passed the upgrade, even if this particular unit
hasn't. Any rule without the disjunct is a candidate.

**Impact classes.** Skipped signature/authentifier rules → spend-without-key (Critical).
Skipped asset/formula/depth rules → invalid units accepted, chain-halting divergence (Critical).
Skipped fee/commission rules → economic bugs (Medium/High).

## Suggested probes (benign, local-fork only)
- **Enumerate the gate sites.** Grep `last_ball_mci >= constants.` and `last_ball_mci < constants.`
  across `validation.js`, `formula/validation.js`, `aa_validation.js`, `storage.js`. For each, check
  whether the disjunct or an unconditional form exists. A gate with no disjunct is a candidate —
  the skipped check is the prize.
- **Construct the time-travel unit.** Build a unit whose parents are old units (pre-upgrade MCI)
  carrying the payload the gate skips (e.g., a definition/formula over the depth limit, a
  signature-less authentifier, a private asset with conditions). Confirm the node accepts it while
  the same payload attached to the tip is refused (negative control).
- **No-ball variant.** Units with no ball (not yet on MC) may also bypass gates that key on
  `hasBall`; test the same payload with a unit whose last_ball_mci is null/low.
- **Sibling sweep.** Every rule the team recently wrapped in the disjunct had siblings — audit the
  *other* rules in the same function/file that still use the bare gate.

## Negative controls
- The payload attached to the current tip IS refused (same payload, honest position).
- A rule WITH the disjunct is enforced regardless of attachment (positive control for the
  defense pattern).
- The bypass does not require non-default config.

## Counterexample (held)
- `getMinRetrievableMci()` on a mature network exceeds the upgrade MCI, so the disjunct makes the
  rule unconditional — the bypass only works against nodes behind / during the transition window.
  Record the window honestly; a narrow-window bypass is `real-but-capped`.
