# Round E1-REVIEW briefs — verify the E1 escalation claims (fresh context)

Per the operator's standing requirement: at the end of each round, a review verifies each claim.
Reviewers are fresh-context, adversarial-lite: verify the claim against the SOURCE and the RAW
evidence, do not trust the hunter's summary. For each claim: verdict `verified | overstated |
wrong`, with the decisive file:line or raw-log line.

## ER-1 — verify E1-2 (fork race capped) + E1-8 (merchant exposure)
Read evidence/roundE1/E1-2.md + E1-8.md. Claims: (a) the MC race between the victim spend C and
the attacker ghost A is position-only (both 'good', conflict machinery never fires —
main_chain.js:1292-1293); (b) the attacker can reliably win the MC position via tip anchoring +
unit-hash grind (E1-2 measured 8 distinct hashes spanning the lexicographic range — check the
grind claim: is the unit hash really controllable by content? does the tie-break really use it?);
(c) the value ledger always resolves to the victim (ghost payload rejected by the owner binding —
divisible_asset.js:159); (d) merchant exposure: direct-descendant ghost, unbounded window, no
signal (E1-8's raw evidence). Report evidence/roundER/ER-1.md.

## ER-2 — verify E1-5 (parent_composer crash) + E1-11 (storage accounting)
Read evidence/roundE1/E1-5.md + E1-11.md + evidence/lab/e15/e15-throw-repro.log. Claims: (a) the
filterParentsByTpsFeeAndReplace throw (parent_composer.js:461) crashes the composing process via
unhandled rejection when all candidate parents underpay (raw log: 16 exclusions → no replacements
→ unhandled rejection — verify the log really shows this); (b) the pool is attacker-influenceable
(the top-16 pool shape, ORDER BY last_ball_mci DESC LIMIT 16 — verify the LIMIT and the exclusion
logic); (c) E1-11: storage-size accounting conserved (16/16 shapes measured) + the checkStorageSizes
throw → scheduled crash (aa_composer.js:1913-1935, 2061-2062). Report evidence/roundER/ER-2.md.

## ER-3 — verify E1-12 (multisig DoS) + E1-4 (F1 one-off)
Read evidence/roundE1/E1-12.md + E1-4.md. Claims: (a) my_xpubkey from non-correspondents
(device.js:214 allowlist) → addDeviceXPubKey inserts a member with approval_date, no membership
check (wallet_defined_by_keys.js:361-378) → the wallet never finalizes (checkAndFinalizeWallet
requires member_ready_date) → no removal path (deleteWallet blocked by approval_date) — verify
each step against the pinned source + the empirical run (real schema); (b) F1 is the ONLY
verification primitive with a prover-supplied truth anchor (E1-4's per-primitive table — spot-check
is_valid_sig, vrf_verify, is_valid_signed_package). Report evidence/roundER/ER-3.md.

## ER-4 — verify the orchestrator's fee-accounting adjudication (OV-1, replacing the timed-out E1-1)
Read evidence/roundE1/orchestrator-verifications.md (OV-1) + the source. The adjudication claims:
(a) the declared tps_fee is burned from inputs at save (validation.js:2654-2656 balance closure);
(b) the settlement applies ONLY the delta (declared - final) to recipient balances
(storage.js:1246-1261); (c) getTpsFeeRecipients overrides non-author recipients to the author
(storage.js:1458-1465) — no targeted drain; (d) conservation: net cost = final, no money creation;
(e) the double-application candidate (updateTpsFees has no dedup — could the same MCI settle
twice?) — E1-1 traced the callers (advanceMcStability.finish:577 does NOT update fees;
updateMainChain.finish:448 does; writer's loop calls it separately, serialized under
handleJoint/write locks) — VERIFY this function-boundary claim against the source, and check for
ANY path where the same (address, mci) delta applies twice (updateMissingTpsFees re-runs? restart
with assocStableUnitsByMci rebuilt? two MCIs in one batch? the REPLACE INTO keying — is (address,
mci) unique?). This is the highest-value verification — a double-credit would be Critical.
Report evidence/roundER/ER-4.md.

## Output contract
Report to evidence/roundER/<id>.md; return JSON {id, verdict, per_claim: [{claim, verdict,
evidence}]}. Fresh context; do not trust hunter summaries; verify against pinned source + raw
logs. No live network. No secrets.
