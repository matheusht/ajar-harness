# Round E4-REVIEW briefs — verify the E4 terminal claims (fresh context)

Final verification round. Verify against the pinned source + RAW evidence; do not trust summaries.

## ER4-1 — verify the F4 demotion + the M1 correction
Read evidence/roundE4/E4-1.md + E3-10.md + E2-9.md + evidence/lab/e310-exp.js. Claims: (a) the
demotion is correct (honest-author freeze unreachable); (b) E4-1's correction: M1 ("count=1
always") was too strong — E2-9 produced count=22 with the last ball fixed at mci 0 (a real lag
state); the true protections are M2 (wall-clock elapsed dilution for honest units) + the funding
bound + self-frosting; (c) verify the E4-1 independent e310 re-run (fee=17 per step). Verdict:
demotion stands with the M1 correction / needs further correction. Report
evidence/roundER4/ER4-1.md.

## ER4-2 — verify E4-2 (attacker cost inert, end-to-end) + E4-6 (severity audit)
Read evidence/roundE4/E4-2.md + the raw hub log (/tmp/e32-hub.log or evidence/lab/e32-flood.js) +
E4-6.md. Claims: (a) the flood experiment at mainnet parameters demonstrates NO impact of any
kind (attacker or victim) — verify the raw log shows the flood chain settling with trivial fees;
(b) the severity audit: 001 Medium confirmed by the E3-1 demo (verify the demo's raw log lines:
BYPASS-CONFIRMED vs bounce), 003 Low ceiling confirmed; (c) no severity inflation anywhere.
Report evidence/roundER4/ER4-2.md.

## ER4-3 — verify E4-14 (lifecycle) + E4-16 (pattern promotions) + E4-13 (handoff)
Read evidence/roundE4/E4-14.md + E4-16.md + E4-13.md. Claims: (a) the gates pass for 001/003
after revision (re-run tools/finding_lifecycle.py gates on both packages); (b) 004's refutation
is recorded inside the package (check the unproven/obyte-2026-08-004/REPORT.md REFUTATION
section); (c) the conformance check passes with the DAG cards (re-run tools/check-conformance.py);
(d) the handoff package is complete and accurate. Report evidence/roundER4/ER4-3.md.

## ER4-4 — verify E4-15 (covered-dry audit)
Read evidence/roundE4/E4-15.md + rounds.md. Claims: (a) every family is exhausted or blocked with
a decisive control (spot-check 3-4 families: signature, main-chain, private payments, formula);
(b) the primitive registry has no unattempted composition; (c) the blind round produced no new
in-scope family; (d) the ladder questions remain covered-dry; (e) the coverage statement's
characterization of the escalation phase is accurate. Verdict: covered-dry verified / a gap
exists (name it). Report evidence/roundER4/ER4-4.md.

## Output contract
Report to evidence/roundER4/<id>.md; return JSON {id, verdict, per_claim: [{claim, verdict,
evidence}]}. Fresh context; verify against pinned source + raw logs; local only; no secrets.
