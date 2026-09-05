## Parent

[Spec: trustworthy offline engineering evidence](https://github.com/matheusht/redteam-harness/issues/106)

## What to build

An evaluator supplies a compact frozen study definition and normalized case, outcome and receipt records, then receives one deterministic report of assigned work, independently assessed output, accounted human effort, available compute and completeness limits.

## Acceptance criteria

- [ ] The versioned study definition fixes the question, permitted conclusion, assigned case/arm/repeat roster, source family split, grading/isolation procedure, treatment difference, configuration and total resource ceilings before outputs. Reuse compatible existing conventions rather than a new evaluation framework.
- [ ] Report every assigned row, including no-output, failed, interrupted, blocked and incomplete cases. Keep assigned cases, produced inventory and eligible assessed results distinct. Extra or contradictory identities are invalid.
- [ ] Record declared versus observed runtime/model/instruction identity and provenance. Missing loading evidence and floating aliases stay qualified; a file hash does not prove receipt or comprehension.
- [ ] Accept supplied normalized activity receipts for preparation, useful assistance, retries, recovery, synthesis, grading, reporting, cleanup and accounting work. Identity, attribution and any allocation are explicit inputs; automatic raw-telemetry reconciliation is outside this slice. Preserve the correction ledger's purpose.
- [ ] Keep active human duration, elapsed time and machine effort separate. A known overlap or nested duration prevents an unqualified sum unless a supplied nonoverlapping allocation resolves it. Record development and maintenance separately with an explicit allocation rule.
- [ ] Duplicate delivery of one receipt identity cannot add work twice; conflicting copies fail. Equal-looking observations with distinct valid identities may represent separate work. Keep unattributed or unreconciled imported sources separate and qualified rather than deriving identities or combined totals.
- [ ] Display assigned-case coverage, measured/recorded receipt coverage and scope-completeness evidence separately. The roster cannot enumerate omitted calls or human activities. A complete total requires scope completeness, measurement completeness and nonoverlapping allocation for that metric, and cites its declared scope. All received costs known without scope evidence remains incomplete; complete activity inventory with one unknown cost also remains incomplete for cost.
- [ ] The public offline report boundary accepts a synthetic control with explicit accounting-scope completeness evidence and retains a failed/no-output/partial-cost case. Include all-received-costs-known but completeness-unknown, malformed identities, conflicting receipts and unresolved overlap. Do not hide assigned rows or imply observed receipt coverage proves all actual work.
- [ ] Produce only requested offline outputs. Do not create a collector, database, model runner, authority state or historical backfill. Do not infer a study winner from Q02's threshold or message count.

## Blocked by

None (can start immediately).

## Review basis

Existing telemetry provides useful advisory evidence. The missing piece is the complete assigned-study account, including work that never produced a candidate or correction.

Approved on 2026-09-05 as part of the [six-ticket breakdown](https://github.com/matheusht/redteam-harness/issues/105#issuecomment-5553859692). This ticket is open implementation/preparation work; research checks are not completion evidence.
