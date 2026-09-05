# Offline engineering evidence

**Status:** accepted implementation plan, not implementation-complete. **Updated:** 2026-09-05. **Authority:** [specification #106](https://github.com/matheusht/redteam-harness/issues/106) and its [approval/publication record](../research/harness-engineering-2026-09-05/handoff.md).

## Decision

Build a trustworthy account of inputs, output and total work before deciding whether more runtime or communication machinery is useful. Four small engineering changes and two experiment-preparation packets are approved. The [goal prompt](../research/harness-engineering-2026-09-05/implementation-goal-prompt.md) carries the execution constraints and final acceptance checks; the full specification remains the source of detailed criteria.

| Slice | Need and accepted behavior |
| --- | --- |
| [#107: Guidance](https://github.com/matheusht/redteam-harness/issues/107) | Accurate current-status navigation, preserving dated decisions, the entrypoint mirror and pin rules. Reuse the reference removal already present in main. |
| [#108: Q02 admission](https://github.com/matheusht/redteam-harness/issues/108) | Distinguish malformed, incomplete and admitted inputs before applying the existing frozen prompt-ablation rule. Keep package counts and independently assessed root-cause groups in their distinct units. |
| [#109: Study account](https://github.com/matheusht/redteam-harness/issues/109) | Retain every assigned case and attributable normalized work record, with metric-specific completeness limits. This supplies the common report boundary for both experiment packets. |
| [#110: Reconstruction](https://github.com/matheusht/redteam-harness/issues/110) | Explain existing revisions, review relationships, current report state and qualified supplements through a read-only summary, preserving admission and identity protections. |
| [#111: Recovery packet](https://github.com/matheusht/redteam-harness/issues/111) | Prepare benign cases and a source-pinned comparison protocol after #109. |
| [#112: Communication packet](https://github.com/matheusht/redteam-harness/issues/112) | Prepare serial/direct-handoff/board cases with fair accounting and isolated grading after #109. |

The first four slices are independent. The two packets depend on #109 only; Q02's frozen threshold does not evaluate the general study. See [experiment choices](comparison-experiments.md) for why neither runtime adoption nor a deployed board is approved here.

## Evidence and its limits

The research inspected production source at `6a47b64264b6bf8f1edf8923847cfc9952cd1ab8`. The reviewed research/specification snapshot is local commit `d150f8d04fd902b48f6a5914880637d39e29a2d1`. Its [validation record](../research/harness-engineering-2026-09-05/validation.md) distinguishes executed checks from inspected sources and tests.

- [Evaluation research](../research/harness-engineering-2026-09-05/evaluation.md) demonstrated favorable public-Q02 outcomes for invalid synthetic inputs and counts that did not establish independent eligibility. Existing self-tests passing did not establish admission correctness.
- [Reconstruction research](../research/harness-engineering-2026-09-05/reconstruction.md) demonstrated omitted report/review/change facts in six pure-rendered views. This establishes a presentation gap; operator-time savings remain unmeasured.
- [Instruction research](../research/harness-engineering-2026-09-05/instructions.md) identified broken pointers and mixed temporal status. It did not identify the effective launch/configuration of the sessions that needed repeated instructions.

Main subsequently reached `0d8fe0c4ffb57a3bf1cfd5d4db013113b51d8c8d`; this was rechecked when seeding the wiki. That commit removes the two broken setup references and refreshes the draft pin. The [handoff](../research/harness-engineering-2026-09-05/handoff.md) records the verified overlap. Treat those defects as repaired in that revision, not as work to repeat. This does not establish the remaining six-ticket implementation complete.

## Distinctions future changes must preserve

| Evidence | What it does not establish by itself |
| --- | --- |
| An assigned case or a produced folder | An independently eligible result. |
| M1 package count | M6 root-cause equivalence count or compatibility with a different endpoint. |
| Every received receipt is measured | Every actual activity was captured. Completeness additionally needs an accounting-scope basis and nonoverlapping allocation, separately for each metric. |
| A configuration declaration or file digest | Actual client loading, adapter receipt or model comprehension. |
| An external report identifier or decision | An internal report identity, current claim validity, novelty or remediation. |
| An immutable report's birth status | Its current event-derived status. |
| A synthetic public-command pass | Provider reliability, causal labor savings or model-quality improvement. |

These distinctions come from the approved specification and the linked evaluation/reconstruction evidence. They are constraints on interpretation, not reasons to invent new infrastructure.

## Verification and open work

Acceptance uses four public boundaries: existing documentation conformance, Q02, the offline study report and the read-only inspector. Both packets pass illustrative complete and adverse accounts through the study report. The [goal prompt](../research/harness-engineering-2026-09-05/implementation-goal-prompt.md) specifies the necessary end-to-end cases and the tested/small-diff/no-unnecessary-abstraction completion gate.

No new implementation acceptance result is recorded yet. The next worker must recheck current source and ticket comments, implement only missing approved behavior, and add exact command/revision/result evidence here. Missing representative launch/configuration prevents a later ordinary-session claim; it does not block the offline implementation or synthetic packet preparation.
