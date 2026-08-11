# Round E4 briefs — obyte-ocore-2026-08 (final escalation round + terminal packages)

The escalation phase refuted its own finding (004 demoted). E4 closes the campaign: the remaining
empirical retries, the package revisions, and the terminal deliverables. Full persistence; caps
must be proven; every claim file:line + raw evidence.

## E4-1 — F4 REFUTATION REVIEW (fresh reviewer — the demotion's correctness)
Verify E3-10's M1/M2 + the demotion against the pinned source and the raw evidence:
(1) M1: the settlement ordering (stabilizeMci → markMcIndexStable → addBalls → updateTpsFees;
writer 1-MCI-per-pass throws) makes last_ball_mci = the previous mci → count=1 — verify against
main_chain.js + writer.js + the E3-10 S1 measurement (fee=17 every step, e310-exp.js); (2) M2:
the wall-clock elapsed dilution for honest units (S3: 4,917 base) + the equal-timestamp trick only
frosting the attacker's own chain; (3) E2-9's real-network corroboration (fees 0-190, balances
+181, no negatives — check the raw log); (4) the r2-drive synthesized-state critique (was the
honest unit seeded with the attacker's equal timestamps?). Verdict: demotion correct / incorrect /
needs correction. Report evidence/roundE4/E4-1.md.

## E4-2 — FLOOD ATTACKER-COST (retry E3-2's core question)
The honest-author freeze is dead; what does the ATTACKER's own chain pay? On the two-node lab with
the E3-2 timestamp fix (WP-1 at T0-1, flood units at T0, WP-2 at T0+1): post the flood chain and
measure the attacker's OWN settlement fees (the self-frosting economics at the real rate). Does
the attacker burn ~10.7% of the supply (making the attack pointless) or is there a cheaper
construction? Report evidence/roundE4/E4-2.md.

## E4-3 — F3 DISPLACEMENT EMPIRICAL (retry E3-3)
On the two-node lab: victim spend C, attacker ghost A as a direct descendant with a ground
timestamp; measure which unit holds the MC position and whether the attacker grind (unit-hash
content control, main_chain.js:46-48 ordering) reliably displaces C. Report
evidence/roundE4/E4-3.md.

## E4-4 — AIRDROP-CLAIM AA DEMO (retry E3-5)
The realistic form of F1's fund impact: an airdrop-claim AA (claim gated by a merkle proof of
inclusion in the airdrop list) drained with the vacuous proof — claim the airdrop for arbitrary
addresses. Use the E3-1 lab pattern (e31-aa-demo.js). Report evidence/roundE4/E4-4.md.

## E4-5 — F1 PACKAGE REVISION
Revise the obyte-2026-08-001 package: fold in the E3-1/E4-4 fund-impact demonstrations
(exploitability evidence: the withdrawal-gated AA bypass + the airdrop-claim drain), update the
severity rationale (the fund-impact class is now demonstrated; the usage-cap is the remaining
limiter), and re-run the six gates. Report the revision + gate results in
evidence/roundE4/E4-5.md.

## E4-6 — TERMINAL SEVERITY AUDIT
With ALL escalation evidence in: re-audit the severities of 001 (Medium — the fund-impact demo
raises or confirms?) and 003 (Low — the E4-3 displacement result, if it lands, raises or
confirms?). Marginal-contribution critique applied to each. Report
evidence/roundE4/E4-6.md.

## E4-7 — Q-1 POC FINALIZATION (retry E3-6)
Finalize the Q-1 maximum-impact PoC package: the delivery-loop script (hub mailbox → wallet
processing → crash → re-delivery), the blast-radius note, cleanup. Quarantine-level. Report
evidence/roundE4/E4-7.md.

## E4-8 — AA TO AA RESPONSE CHAINS (retry E3-8)
On the two-node lab: trigger an AA whose response triggers a second AA — measure chain depth
limits, ordering determinism, work amplification. Report evidence/roundE4/E4-8.md.

## E4-9 — AA-RESPONSE FEE INTERPLAY (retry E3-9)
AA responses carry no tps_fee but count in getFinalTps (count_aa_responses) and
getCountUnitsPayingTpsFee pre-charges the trigger: is there any fee-window inflation via AA
responses cheaper than normal units? Report evidence/roundE4/E4-9.md.

## E4-10 — FIELD-NOTES LESSONS PACKAGE
Draft the cross-engagement lessons for docs/field-notes.md (abstract, portable): (1) the
synthesized-state PoC lesson applied to our own finding (r2 drive vs E3-10 — a real-network
corroboration refuted a real-path drive that seeded unreachable state); (2) the
escalation-refutes-finding outcome (the adversarial round corrected the engagement's own record);
(3) SQL-semantic claims must be executed; (4) the blind-round lesson; (5) the settlement-ordering
verification pattern (verify WHERE a settlement runs relative to ball creation before believing a
window-count claim). Report evidence/roundE4/E4-10.md.

## E4-11 — MEMORY DISPOSITION FINALIZATION
Finalize the memory disposition: PC-2/PC-3/PC-5 promote recommendations (with the reachability
caps recorded), PC-1/PC-4 defer, the field-notes lesson list, and the casebook promotion
recommendation for this engagement (what a scrubbed casebook would contain). Report
evidence/roundE4/E4-11.md.

## E4-12 — CASEBOOK PREPARATION
Draft the scrubbed casebook structure for this engagement (casebooks/<id>/: case.yml,
recon-signals.yml, hypotheses.yml, oracle-matrix.json, lessons.md, promotion-notes.md) with the
abstract shapes only (no target identifiers beyond the DAG class). Report
evidence/roundE4/E4-12.md.

## E4-13 — OPERATOR HANDOFF PACKAGE
Assemble the operator handoff: the two proven findings (001 Medium, 003 Low) with their final
evidence, the demoted 004 with the refutation trail, the hardening backlog (17 items), the
quarantine candidates (Q-1 device crash with crash-loop PoC, Q-2 multisig DoS), the coverage
statement, and the submission-recommendation summary (what to file, at what severity, with the
program's Primacy-of-Rules framing). Report evidence/roundE4/E4-13.md.

## E4-14 — LIFECYCLE RE-RUN
Re-run the lifecycle gates on ALL packages (001, 003, 004-unproven): the gates must still pass for
001/003 after the revisions; 004 stays unproven with the refutation recorded. Report the gate
results. Report evidence/roundE4/E4-14.md.

## E4-15 — COVERED-DRY AUDIT (multi-round-orchestration §5)
The terminal audit: (1) every family exhausted or blocked with the decisive control; (2) the
primitive registry has no unattempted composition (CHAIN-1 + E1-13 + the F4 refutation);
(3) the blind round produced no new in-scope family (LR-4: one adjacent-surface family,
quarantined); (4) the ladder questions remain covered-dry; (5) the escalation phase's net effect
(what it added, what it corrected). Verdict: covered-dry / not-dry (with the missing piece).
Report evidence/roundE4/E4-15.md.

## E4-16 — PATTERN-CANDIDATE PROMOTIONS
Finalize the pattern-candidate promotions: PC-2 (dag.old-dag-rule-gating — with the stabilization
cap), PC-3 (verification-root-not-anchored — confirmed F1), PC-5 (bearer-token-uniqueness
party-keyed — confirmed F3), PC-1/PC-4 (defer), plus the DAG-card conformance re-run. Report
evidence/roundE4/E4-16.md.

## Output contract
Report to evidence/roundE4/<id>.md; return JSON {id, verdict, evidence}. Real-path discipline.
No live network. No secrets.
