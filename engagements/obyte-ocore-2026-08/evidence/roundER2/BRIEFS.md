# Round E2-REVIEW briefs — verify the E2 escalation claims (fresh context)

Per the operator's per-round review requirement. Reviewers: fresh-context, verify claims against
the pinned source + RAW evidence; verdict per claim: verified / overstated / wrong.

## ER2-1 — verify E2-1 (money-creation resolved) + E2-10 (refund path)
Read evidence/roundE2/E2-1.md + E2-10.md. Claims: (a) the funding gates block un-funded declared
fees ("no base payment message" validation.js:1521; balance closure validation.js:2654-2656);
(b) conservation: declared burned, delta-only settlement, net cost = final (empirical: declared
1.068e15, final 17, net 17); (c) the double-application: direct double-call re-applies the delta
(balance 1e6→2e6) and the stale-watermark reprocess path re-applies too (2e6→3e6) — verify the
E2-1 raw evidence actually shows the reprocess path executing (not just a manual second call), and
confirm the sqlite immunity + MySQL-only condition; (d) no withdrawal path for the balance credit.
The money-creation question's answer is the round's keystone — verify hard. Report
evidence/roundER2/ER2-1.md.

## ER2-2 — verify E2-9 (natural-burst refuted) + E2-11 (dust capped)
Read evidence/roundE2/E2-9.md + E2-11.md. Claims: (a) composition throughput caps the rate at
~6/s (verify the measured number and the mechanism — the composer's serialized parent selection?);
(b) settlement elapsed dilutes tps (the window spans >1s); (c) the 10x estimation multiplier
credits the balance (authors who declared at the calm estimate get credited when the burst
settles — verify the direction); (d) E2-11: floor dust always destroys value; the half-up
roundings can create value but recipients are OP-only or the gain is ~50x below the cost.
Report evidence/roundER2/ER2-2.md.

## ER2-3 — verify E2-16 (Q-1 crash-loop 3/3) + E2-6 (AA path on the network)
Read evidence/roundE2/E2-16.md + E2-6.md + the raw logs. Claims: (a) the device-layer scheduled
throw crash-loops on re-delivery (3/3 cycles — verify the raw log shows the crash + the
re-delivery + re-crash); (b) the delivery path (hub/deliver mailbox → wallet processing) is real
and remote; (c) E2-6: the complete AA path executed (definition → stabilization → aa_triggers →
handleAATriggers → formula → response committed with sequence=good, identical hash on both nodes —
verify the raw log lines). Report evidence/roundER2/ER2-3.md.

## ER2-4 — verify E2-3 (issueAsset refuted) + E2-5 (issue spend proof capped) + E2-13 (archiving)
Read evidence/roundE2/E2-3.md + E2-5.md + E2-13.md. Claims: (a) the 2^53 cap window is closed on
the validation path (total caps); (b) the issue spend proof reuse is economically inert in the
reachable case; (c) the archiving unspend NOT EXISTS guards prevent double-claim. Spot-check the
decisive controls at the cited file:line. Report evidence/roundER2/ER2-4.md.

## Output contract
Report to evidence/roundER2/<id>.md; return JSON {id, verdict, per_claim: [{claim, verdict,
evidence}]}. Fresh context; verify against pinned source + raw logs; no live network; no secrets.
