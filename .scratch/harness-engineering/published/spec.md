**Status:** approved for publication on 2026-09-05. [Operator approval](https://github.com/matheusht/redteam-harness/issues/105#issuecomment-5553859692) accepts the four test boundaries and six-ticket breakdown. Implementation and experiment execution have not started.

## Problem Statement

The operator cannot reliably tell whether another instruction, retained context, agent collaboration or runtime machinery improves the harness without reconstructing scattered records and accounting for the work themselves. Present comparison inputs can omit important integrity evidence while still receiving a decisive result. Directory counts, correction counts and partial telemetry do not measure independently assessed output or complete effort. Existing summaries also omit meaningful state that is already recorded.

We need a trustworthy basis for engineering choices before adding more machinery. This specification concerns offline document research, record inspection and comparison preparation. It makes no claim about attack efficacy or ordinary-session improvement.

## Solution

Repair concrete guidance and input-admission defects, expose the evidence already retained, and give each offline comparison a complete account of assigned cases and measured work. Then prepare bounded recovery and communication experiments using that account. Retain explicit uncertainty wherever the records cannot answer a question.

The delivery consists of four small engineering changes and two experiment packets. The packets are preparation artifacts. They do not build a runtime, invoke models or adopt a message board.

## User Stories

1. As an operator, I want active setup references to resolve, so that I can follow the current engineering workflow.
2. As an operator, I want current status distinguished from dated decisions, so that old proposals do not appear implemented or newly binding.
3. As a maintainer, I want mirrored entrypoints and frozen evaluation pins preserved, so that documentation cleanup cannot silently change recorded inputs.
4. As an evaluator, I want malformed comparison records rejected clearly, so that decoding accidents do not become conclusions.
5. As an evaluator, I want missing integrity evidence reported as incomplete, so that omission cannot imply successful blinding or equal budgets.
6. As an evaluator, I want measurements and adjudication bound to the same identified source, case and run, so that individually readable files cannot be silently mixed.
7. As an evaluator, I want inventories separated from eligible result identities, so that folders and unreviewed claims do not count as independent results.
8. As an evaluator, I want overlap and waste assertions reconciled with cited inputs, so that descriptive fields do not bypass the decision rule.
9. As a maintainer, I want Q02's frozen rule and limited case-study license retained, so that an admission repair does not enlarge its scientific conclusion.
10. As an evaluator, I want a case roster fixed before outputs, so that interrupted, failed and empty cases remain visible.
11. As an evaluator, I want intended and observed configurations distinguished, so that matching declarations are not mistaken for matching execution.
12. As an operator, I want successful setup, assistance, review, repair and administration counted, so that correction events do not stand in for all human effort.
13. As an evaluator, I want unique activity identities and attributable sources, so that duplicate delivery does not inflate spend and equal-looking genuine work remains distinguishable.
14. As an evaluator, I want elapsed time, summed worker effort and active human time separated, so that parallel and overlapping work are not added incorrectly.
15. As an evaluator, I want unknown and partially measured usage explicit, so that a subtotal is never presented as a complete cost.
16. As an independent reader, I want source revision and claim-record revision identified separately, so that I can reconstruct what was actually assessed.
17. As an independent reader, I want review type, subject, input references and rationale visible, so that I can understand the recorded review relationship.
18. As an independent reader, I want a predecessor-revision adjudication explained, so that I do not incorrectly reject or accept it using a naive revision join.
19. As an operator, I want a report's current status and supersession explained from its recorded history, so that an immutable draft manifest does not mislead me.
20. As an operator, I want outside decisions attributed separately with explicit mapping limits, so that an external report number or duplicate label cannot imply current validity or remediation.
21. As an operator, I want absent, unreadable, invalid, unmapped and stale sources distinguished, so that missing evidence is not rendered as a negative result.
22. As an operator, I want the current task and corrections included only from supplied attributable context, so that pending work does not silently redefine my request.
23. As an investigator, I want declared instruction inputs, observed client loading and recorded adapter input separated, so that file presence does not prove receipt or comprehension.
24. As an operator, I want inspection to leave source records unchanged, so that explaining state does not repair, promote or dispatch work.
25. As a maintainer, I want recovery candidates compared on selected observable contracts, so that framework selection follows requirements.
26. As an evaluator, I want cooperative pause and process-loss uncertainty tested separately, so that saved conversation state is not mistaken for exactly-once artifact work.
27. As a researcher, I want a board tested against capable serial and direct-handoff baselines, so that additional workers or information do not masquerade as communication benefits.
28. As a researcher, I want retained notices, delivery opportunities, use, correctness and usefulness measured separately, so that a busy board does not look effective by construction.
29. As an independent grader, I want to assess anonymized final outputs against a previously fixed reference while peer discussion, self-grades, treatment labels and other cases' answers remain excluded, so that collaboration does not compromise the evaluation.
30. As a maintainer, I want explicit rejection and escalation criteria for each experiment, so that an inconclusive pilot does not become a platform commitment.

## Implementation Decisions

These decisions were approved on 2026-09-05. Reuse existing offline readers, validation, identity, reference and telemetry conventions where their semantics fit. No new persistence backend, dispatcher or generic framework is needed.

1. **Active guidance.** Resolve or remove the two broken setup references, and give the current architecture/status a concise, accurate entry point. Preserve dated history, the accepted entrypoint mirror, generated-view compatibility and draft-versus-frozen pin rules. Extend existing documentation checks only for these active references.

2. **Q02 admission.** Introduce one shared admission boundary before its existing rule is applied. Require explicit supported input version, correctly typed integrity answers, nonempty adjudicator identity, source/case/run binding and unique eligible package identities. The measurement, worksheet, source commitments, eligibility assessment, root-cause grouping and any asserted waste evidence must resolve to their declared bytes and identities. A declared adjudicator or blinding flag is an attributed declaration, not proof of cognitive independence. Validate malformed evidence before incomplete-evidence handling; preserve earlier checkpoint and quarantine failures.

   | Input class | Public result |
   | --- | --- |
   | Invalid JSON or duplicate keys; wrong types; nonfinite, negative or fractional count; empty/whitespace identity or present-but-blank waste assertion; duplicate package identity; contradictory mapping or referenced-byte mismatch | Bounded input error, exit 1, no verdict or conclusion license, no traceback. |
   | Missing or well-typed unsupported version; missing required identity; missing/null integrity answer; unavailable required referenced bytes; unestablished unit compatibility | Inconclusive, exit 0, explicit reasons and the frozen inconclusive license. |
   | Explicit failed blinding, cross-arm read or truncation | Inconclusive with the existing integrity reason and frozen inconclusive license. |
   | Admitted evidence | Apply the unchanged frozen rule and its existing maximum license. Optional absent cost retains current branch-specific inconclusive behavior; absent waste assertion never becomes positive evidence. |

3. **Q02 compatibility.** Measurements keep package inventory separate from evidence that makes a package eligible. M1 retains the legacy package unit, counted once per admitted package identity. M6 uses independently adjudicated root-cause equivalence groups, with explicit package-to-group mapping; it is not automatically in the same units as M1. Do not collapse multiple packages into one M1 result or require M6 group totals to equal package counts. Newly decisive input requires an attributable, source-bound eligibility assessment and established compatibility of the supplied package interpretation with the frozen rule. Unestablished compatibility, unsupported revisioned layouts and old unbound inputs remain inspectable but inconclusive. Preserve the threshold, decision branches, checkpoint checks and maximum license. Do not recompute history or reinterpret the absent private preregistration. A general offline study uses its own endpoint definitions, never Q02's threshold by default.

4. **Offline study account.** Use a compact versioned study artifact and a deterministic report over supplied files. Its frozen part names the question, permitted conclusion, assigned case/arm/repeat roster, source family split, configuration, total resource ceilings, intended treatment, grading procedure and missing-data policy. Its observations identify produced outputs, independent assessments, terminal outcomes and deviations. All assigned rows remain in the report. Produced packages, eligible results and assigned cases are distinct quantities.

5. **Work accounting.** The first report accepts normalized supplied case, outcome and receipt records, with attribution and any allocation already explicit. It does not discover calls, infer receipt identity or automatically reconcile raw telemetry. Receipts name actor/role, phase, activity and measurement source. Separate active human duration, elapsed duration and machine effort. The accounting scope includes preparation, useful assistance, retries, interruption, recovery, synthesis, grading, reporting, cleanup and measurement overhead; development/maintenance remains separately allocated. Identical receipt IDs cannot add twice; conflicting copies are invalid. Distinct valid receipt identities may represent equal-looking separate work. Known overlaps for one person or nested runtime durations prevent an unqualified sum unless an explicit nonoverlapping allocation is supplied.

   Assigned-case coverage and measured/recorded receipt coverage are different denominators. Neither proves completeness of actual work. A complete total is established separately for each metric only when supplied scope-completeness evidence, measurement completeness and nonoverlapping allocation are all established. A complete activity inventory with one unknown cost still has an incomplete cost total. Otherwise show measured subtotals and each remaining coverage limit. Any complete total is limited to its declared accounting scope and cites its basis. Imported sources without a supplied reconciliation stay separate and qualified. No advisory telemetry redesign or universal correction collector is included.

6. **Read-only reconstruction.** Produce an on-demand summary from valid admitted authoritative inputs and separately attributed supplements. Reuse existing source admission and identity protection; do not invoke writing reduction/rendering commands, create coordination state, repair missing inputs or require stale generated views to be fresh before explaining them. Show the validation basis, typed source pointers, source and claim revisions, changes, review subject/reason/inputs, current report status and historical reasons. Preserve review-type-specific predecessor/filing relationships. Existing records remain authoritative; the result is an ephemeral explanation.

7. **Supplemental context and outcomes.** Current task intent is an optional supplied reference with provenance, not an inference from scope or pending work. Record only necessary configuration metadata and availability of observed loading; unknown remains unknown. External dispositions retain external identifiers, every relevant source row, decision/recording times and available confidence. Never join them to internal report identities by field name, assume the latest row supersedes the rest or bind them to a current revision without evidence. Keep technical assessment, independent review, report acceptance, external outcome, novelty and remediation separate. Human cleanup context remains linked. Graceful supplement failure applies only to separately supplied inputs outside existing base admission. Invalid or colliding records already indexed by base admission retain that admission failure; do not skip them to manufacture valid state. A separately invalid supplement is reported explicitly beside valid base evidence, never treated as an absent outcome.

8. **Recovery experiment packet.** Prepare harmless document versions, scheduled corrections, expected trace accounts and a source-pinned protocol. The default local observation point is arguments actually received by a scripted adapter with declared client-managed history. Separate local admission, adapter invocation and unobserved provider receipt. Cover late input, recorded-but-unsupplied results, cooperative pause and loss after an artifact write without its receipt. Preserve error/termination/usage fields independently. Treat persisted no-summary rollover as an optional diagnostic until explicitly required. Compare candidate fit and maintenance obligations; select no runtime here. Preparing the packet neither implements adapters nor runs models.

9. **Communication experiment packet.** Prepare three document packets: complete sources, complementary evidence and a late correction. Compare serial complete-source work, parallel directed handoffs with a curated packet, and the identical parallel arrangement plus a bounded task-local board. Use equal source access and total budgets, counting the coordinator and communication. Externally scheduled observations and corrections become available to the serial worker, direct-handoff coordinator and board arrangement at the same declared release point; count their preparation. Commit independent initial observations before shared conclusions. Fix the grader's reference assessment first, then grade anonymized designated final outputs without treatment labels, peer discussion, worker self-assessments or other-case answers. Notices identify task, author, source version, observation, applicability and uncertainty; corrections preserve their predecessor. No cross-case reuse, durable shared beliefs, automated assignment or source-of-truth change is introduced. The packet contains a fixed notice schedule and answer key, not a board service.

10. **Experiment conclusions.** A deterministic packet check establishes accounting and isolation behavior only. A three-packet communication pilot can justify a larger study if a validated notice improves a complementary-evidence or correction outcome over direct handoff within the same budget without new correctness, provenance or isolation failures. It does not justify adoption. A larger study must predeclare a practical benefit threshold and repeated paired design. The recovery packet distinguishes satisfied, contradicted, unsupported and untested interface contracts; source inspection alone cannot award a passing execution result. Both packets remain unexecuted until their effective configuration, budget and run scope are established.

## Testing Decisions

Tests should exercise public observable behavior at four boundaries. Prefer existing highest-level checks and a few rich benign cases over per-helper suites or new frameworks.

1. **Documentation conformance:** active pointers resolve, mirrors remain identical, and authorized pin drift remains a failure. A dated historical statement is not failed merely for describing the past.
2. **Existing Q02 command:** submit valid bound synthetic evidence, explicit adverse controls, missing integrity fields, wrong types, duplicate keys/IDs, contradictory mappings, unsupported layouts and mismatched measurement/worksheet identities. Include multiple eligible packages sharing one adjudicated root cause: M1 and M6 retain their distinct units. Verify output, error behavior, blockers and conclusion license against the admission table. Preserve existing path/quarantine/publication checks. Favorable-invalid-input characterizations must change into defined rejection or inconclusive outcomes; old passing self-tests alone are insufficient.
3. **Offline study-report boundary:** a frozen roster includes a no-output case, failed case, partial cost, duplicate receipt delivery, conflicting duplicate and overlapping human activity. Verify assigned-case coverage separately from measured/recorded receipt coverage and completeness evidence. All received costs being known must still produce unknown total completeness when no independent accounting-scope basis is supplied. Malformed records fail clearly; missing measurements do not fabricate zero or disappear. Both future experiment packets must generate an admitted illustrative account and demonstrate that incomplete or contaminated examples remain qualified. These examples are explicitly synthetic, not measured experiment results.
4. **Read-only inspection boundary:** one harmless dossier distinguishes source v2 from claim revision 3, predecessor adjudication, historical revision-2 report, event-derived current acceptance, review subject/reason, external unmapped outcome, absent task context, unknown loading, separately invalid supplement and stale projection. Check unchanged source bytes and no created files or coordination state. Missing coordination remains unavailable without creating a lock; final source-identity rejection emits no valid summary. Invalid indexed records retain base-admission failure. The prior pure-renderer probe is the motivating regression example, not sufficient acceptance of this new reader.

Prior art is the existing command self-tests, documentation/mirror/pin checks, record identity and quarantine tests, reducer/view tests, conservative cost aggregation and retained synthetic research probes. Run only checks required by touched contracts and repository obligations. No target fixture, live provider, paid execution, external side effect or historical result recomputation belongs in these acceptance cases.

## Out of Scope

- Live target testing, exploit reproduction, autonomous offensive execution, operational routing/dispatch, altered gates or broader autonomy.
- Runtime replacement, provider adapters, a deployed board, model training, self-rewriting memory, external posting or paid studies.
- New database, embeddings, plugin platform, general telemetry collector or generic documentation crawler.
- Automatic external-status promotion, inferred remediation, historical record rewrites or deletion of required generated views.
- OSLit strategy and commercial claims; closing, implementing or lifting holds on existing operational architecture issues.
- Claiming model quality, production reliability, causal labor savings or architecture superiority from source review or synthetic packet checks.

## Further Notes

The ordinary launch path behind repeated instructions remains unverified. It is a required input for any later ordinary-session causal comparison, not a reason to guess or block this offline work. A floating model alias and unavailable client-loading evidence must be disclosed in that comparison.

Research resolutions are indexed by [Wayfinder: establish trustworthy harness engineering evidence](https://github.com/matheusht/redteam-harness/issues/100). The approved implementation breakdown is six vertical slices; recovery and communication preparation depend only on the offline study account. Existing filing-authority and held operational architecture work remain separate.

Research decisions: [comparison admission and accounting](https://github.com/matheusht/redteam-harness/issues/101#issuecomment-5553486080), [reconstruction and guidance](https://github.com/matheusht/redteam-harness/issues/102#issuecomment-5553486375), [recovery foundations](https://github.com/matheusht/redteam-harness/issues/103#issuecomment-5553486632), and [message-board contribution](https://github.com/matheusht/redteam-harness/issues/104#issuecomment-5553486887). Detailed research and retained benign checks are preserved in the local reviewed commit named in those resolutions; that branch has not been pushed.
