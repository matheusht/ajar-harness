# KP-F2-link — can an old-DAG-attached unit stabilize and execute?

Pinned `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44`. Worker trace of the load-bearing reachability
question for F2 (`is_valid_signed_package` eval-side S1 bypass) and the whole S1 old-DAG family
(A5 multi-trigger, A6 outer AA-trigger gate, f1-T2/T3/T7, P9-bonus 60-sibling cap).

## Terminal verdict

**F2 and the entire S1 old-DAG family are DEAD as attacker-reachable consensus/availability bugs.**
Old-DAG-attached units cannot stabilize, and every formula-evaluation path runs at a modern
position. The mechanism each candidate depends on (gated evaluation at an old `mci`) is unreachable
on a real node. All file:line anchors are against the pinned commit.

## Q1 — Can an old-DAG-attached unit be included on the main chain? NO.

Three source-verified mechanisms, any one of which suffices:

1. **Witnessed level is ancestry-derived and old.** `determineWitnessedLevelAndBestParent`
   (storage.js:691-724) computes the unit's `witnessed_level` by walking UP the best-parent chain
   from the unit's parents (`addWitnessesAndGoUp`, storage.js:698-715), collecting authors that are
   in the current OP list until `MAJORITY_OF_WITNESSES = ceil(12/2) = 6` (constants.js:119). For an
   old-attached unit the walk stays in the OLD ancestry — the OPs' old waypoints, at old levels. The
   resulting `witnessed_level` is the level of the old region (~≤10M), never the tip region (~12.1M+
   post-`pemCurvesFixMci`). The current OPs' units live at the tip and are NOT in the old ancestry.
2. **Best-parent selection sorts by witnessed level.** `determineBestParent` (storage.js:2029-2084)
   sorts parents by `witnessed_level DESC, level-witnessed_level ASC, isOP, unit ASC`. Any unit
   whose parent set contains a tip-region unit (witnessed_level ~12.1M+) alongside the attacker's
   old-attached unit (~10M or 0) picks the tip unit. An old-attached unit can only "win" if ALL of a
   unit's parents are old-attached (an attacker-only side branch) — see Q2.
3. **The MC walk starts from the tip.** `updateMainChain` (main_chain.js:32) is called from
   writer.js:643 with `from_unit=null` → `findNextUpMainChainUnit(null)` → `readLastUnitProps`
   (main_chain.js:55-88) selects the free unit with the highest `witnessed_level`
   (`ORDER BY witnessed_level DESC, level-witnessed_level ASC, unit ASC`), then walks up its
   best-parent chain marking `is_on_main_chain=1` (main_chain.js:93-120). The newly added unit is
   only `last_added_unit` (used for the genesis/ball checks), never the walk's start. An
   old-attached unit is never on this path.

## Q2 — Can it reach the witnessed level required for stability? NO.

Stability requires the unit to be an MC unit whose MCI is stabilized. `markMcIndexStable`
(main_chain.js:1268-1300) stabilizes units with `main_chain_index = mci` on the MC path. Since an
old-attached unit is never on the MC (Q1), it never gets a `main_chain_index`, never stabilizes,
never gets a ball, and is eventually purged/archived. The `bStableInParents` spend gate
(validation.js:2445-2466) treats its outputs as unstable/unspendable-by-others; the unit's own
spends never confirm. Its outputs are economically inert.

Additional guard: on a network past `witnessedLevelMustNotRetreatFromAllParentsUpgradeMci`
(5210000), validation rejects a unit whose computed witnessed level retreats from its parents'
(validation.js:913-919) — an old-attached unit with higher-witnessed parents is rejected outright.

## Q3 — What is the evaluation mci for an AA trigger at stabilization? The CURRENT (stabilized) mci.

- Triggers are INSERTed into `aa_triggers` only for MC units at stabilization:
  `main_chain.js:1665-1684` — `SELECT ... WHERE units.main_chain_index = ? AND units.sequence = 'good' ...`
  with `mci` = the stabilized MCI; `INSERT INTO aa_triggers (mci, unit, address) VALUES (mci, ...)`.
- Execution: `handleAATriggers` (aa_composer.js:59-88) reads `aa_triggers.mci` and calls
  `handlePrimaryAATrigger(row.mci, ...)` (aa_composer.js:76) — the STABILIZED mci, which for any
  unit that stabilizes is the current position (≥ `pemCurvesFixMci` on a mature network).
- The eval-side gates in question (`formula/evaluation.js:1652` 3-package cap, `:1693`
  `max_complexity`) key on this mci — always modern for executed triggers.

## Q4 — Any OTHER path where gated evaluation runs with mci < pemCurvesFixMci? NO — every path is current-position.

| path | mci source | verdict |
|---|---|---|
| AA primary trigger execution | `aa_triggers.mci` = stabilized mci (main_chain.js:1682, aa_composer.js:64-76) | current |
| AA secondary triggers | handled in-transaction at stabilization (`handleSecondaryTriggers`, aa_composer.js:1721-1765) | current |
| Remote getters (`execute_getter` RPC) | `executeGetterInState` (formula/evaluation.js:3374-3410): `objValidationState.last_ball_mci = props.main_chain_index` from `SELECT * FROM units ORDER BY main_chain_index DESC LIMIT 1` (current tip); `callGetter` (formula/evaluation.js:3440+) inherits it | current |
| Dry-run / estimation (`bAir`) | `readLastStableMcUnit` (aa_composer.js:275-309): `SELECT ... FROM units WHERE +is_on_main_chain=1 AND +is_stable=1 ORDER BY main_chain_index DESC LIMIT 1` | current |
| Definition-validation-time formula checks | `validateAADefinition` (aa_validation.js) checks structure + getter props, does not run the eval-side gates | n/a |
| Old-DAG AA definition units | validation.js:1764 transient-error guard (`!hasBall && minRetrievableMci >= fix && last_ball < fix`) blocks no-ball old-attached definitions on mature nodes; ball-carrying old-attached definitions would need MC inclusion — impossible per Q1 | blocked |

## What this means for the engagement's S1-family candidates

| candidate | prior status | new verdict | reason |
|---|---|---|---|
| F2 (signed-package eval-side bypass, f5-T1) | confirmed mechanism | **DEAD (unreachable)** | eval runs only at stabilization/getter/dry-run = current mci; old-attached triggers never execute |
| A5 (count_primary_aa_triggers>1 gate gap, f1-T2) | candidate | **DEAD** | validation-time skip; skipped checks only matter for executing triggers (never) |
| A6 (outer AA-trigger gate, f1-T3) | candidate | **DEAD** | same |
| f1-T7 (ball-carrying old-DAG AA definition guard) | weak | **DEAD** | a ball requires MC inclusion (Q1) |
| P9-bonus (60-sibling cap S1-gated) | confirmed mechanism | **DEAD** | below-fix evaluation position unreachable; above-fix the cap applies |
| validation.js:741 (non-AA parent gate) | cross-flag | **DEAD** | era-consistency for never-stabilizing units; no consensus effect |
| f5-T2/T4 (other bare-mci eval gates) | weak | **DEAD** | same unreachability |

## Why the team's "enforce for all new units even if attached to an old part of the DAG" commits do not contradict this

The disjunct-migration commits (277fad7/048fbdb/682e136) close a REAL attack class at the
**validation** layer: units attached to old DAG parts WERE accepted into the DAG (parents
retrievable, no recency requirement — validation.js:604-638) and DID skip new validation rules.
The team hardened those rules because old-attached units exist in the DAG as junk and must follow
the same rules. What they cannot do — and what F2 needed — is STABILIZE and EXECUTE. The commits
defend the validation boundary; the execution boundary is defended by the MC/stability machinery
(Q1/Q2/Q3). Both are needed; the missing disjuncts on the eval side (formula/evaluation.js) are a
latent hazard only if a future path introduces old-mci evaluation — today there is none.

## Residual risks (honest)

1. **Source-trace, not empirically demonstrated.** The lab has no witness/OP infrastructure, so I
   could not run a two-node network with synthetic OPs to empirically show an old-attached unit
   failing to stabilize. The chain is deterministic and each link is cited; the definitive proof
   would be the multi-node lab (f2's planned PoC territory).
2. **The reorg corner.** If a reorg (goDownAndUpdateMainChainIndex) ever assigned a `main_chain_index`
   ≤ `last_ball_mci` to a previously-unballed temp-bad unit, the crash-family state (1686/2451)
   would become reachable. Unproven and unlikely (reorgs null out MC status); noted for the record.
3. **Future code paths** could introduce old-mci evaluation (e.g., a light-client feature that
   evaluates AAs against historical state). The eval-side bare-mci gates remain a hardening item
   (add the disjunct), not a live bug.

## Files

- This report: `evidence/round2/KP-F2-link.md`
- No scripts run this pass (pure source trace — the lab cannot construct the witness state).
