# Offline engineering evidence

**Status:** implementation in progress; #107–109 and #111–112 locally implemented with integrated safe checks passed; #110 blocked with uncommitted WIP; both independent review axes complete; #106 incomplete. **Updated:** 2026-09-05. **Authority:** [specification #106](https://github.com/matheusht/redteam-harness/issues/106) and its [approval/publication record](../research/harness-engineering-2026-09-05/handoff.md).

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

Execution started from clean merge `f68caf673ef9ed12aae4f6e43d64b299c5a1ecc9` on local branch `codex/implement-harness-engineering-2026-09-05`, using one **gpt-6-astra / Low** implementation worker with **Ponytail Full** and **`/implement`**. The accepted intent is trustworthy offline evidence; scope is the six approved slices with public-command synthetic acceptance, intact source records and a small reviewed diff. The [goal prompt](../research/harness-engineering-2026-09-05/implementation-goal-prompt.md) retains the constraints and resolved `docs/wiki/` location. No runtime replacement, operational changes, historical recomputation or model experiments belong to this work.

Slice #107 replaces the README's whole-repository scaffold status with dated current navigation and marks the original architecture summary as historical, linking the implemented record model and decision index. The already-repaired entrypoints and draft pins are unchanged. Historical decisions remain intact.

The existing [conformance checker](../../tools/check-conformance.py) now offers `--engineering-guidance`, running only the fixed active-reference checks, mirror check and existing pin check. Its default check set retains its behavior and includes the new navigation check. A narrow option is necessary because the default command also invokes operational and historical checks outside this goal; no generic crawler or selector framework was added.

Verified locally: `python3 tools/check-conformance.py --engineering-guidance` (12 checks, 0 failures); `python3 tools/engineering-guidance-test.py` (real CLI controls for missing destinations, removed setup references, mirror drift, preserved historical prose, stale draft refresh and authorized-drift refusal); `python3 tools/overlay_pins.py check --json` (0 failures, 0 stale, current readiness record still unauthorized); Python compilation and whitespace checks. The [log](log.md) records the red/green evidence and initial failed broader invocation. These are #107 evidence, not a completed #106 review or full-suite pass.

Slice #109 adds the [offline study report](../study-report.md), an explicit version-1 definition and supplied-observation contract at `python3 tools/study-report.py --study … --observations …`. It binds observations to the exact definition bytes, retains every case/arm/repeat assignment and separates output inventory, supplied independent eligibility assessments, case outcomes, contamination, declared/observed configuration and receipt accounting. The tool reuses the existing safe-offline reader, duplicate-key rejection and canonical JSON/hash conventions; it imports no reducer or execution service.

Study, development and maintenance remain separate. The frozen scope explicitly covers ordinary execution plus preparation, useful assistance, retries, interruption, recovery, synthesis, grading, reporting, cleanup and accounting. Receipts declare actor/role, activity, attribution and measurement source. Identical redelivery is counted once; conflicting identity fails. Missing values remain unknown, explicit N/A needs a reason, known overlap/nesting stays qualified, and explicit sourced allocations can establish a nonoverlapping account. Complete totals require metric-specific scope evidence, complete applicable measurements and nonoverlap; an all-known receipt inventory alone is insufficient. Unreconciled imports remain separate. Known budget overruns are visible; unknown totals cannot establish budget adherence.

On source baseline `3c5c8a847e330e89e6cf48ecf14c3cb1022e3bf3` plus this slice, `python3 tools/study-report-test.py` passed **50 synthetic public-command checks**, including full/partial/unknown accounts, all case states, arm/repeat coverage, successful assistance and execution, duplicate/conflicting/cross-case identities, overlaps/allocations, imports, aliases/loading, definition binding, decimal ceilings and input/file-inventory immutability. Compilation and bounded documentation-link/whitespace checks passed. The [log](log.md) records commands and limits. This report checks supplied records; it does not prove their references, freeze timing, loading, independence or actual-work completeness independently, and it computes no comparison winner. The executable fixture supplies accounting examples for both preparation packets; neither candidate comparison has executed.

Slice #108 adds the [Q02 admission contract](../q02-admission.md) to the existing public command.
Measurements expose source-bound inventory; a separately byte-bound attributed assessment declares
eligibility, frozen-rule compatibility and package-to-root-cause mapping. M1 retains package units;
M6 counts groups. Missing support is inconclusive, malformed evidence is a bounded input error, and
present malformed dimensions are validated before incomplete-input handling. Old loose input cannot
receive a fresh decisive verdict. The checkpoint, decision branches and license remain unchanged.

Verified on source baseline `ade080e64861b5390633fa39d8aaffef491d8f2b` plus the slice: **99 synthetic
public/admission controls**, existing private frozen-rule/checkpoint tests, and the three existing
Q02 quarantine regression checks exercised in isolation with plain lock files. The tests cover
multiple admitted packages per root cause, unsupported/excluded layouts, missing versus malformed
integrity, mismatched references and source/quarantine races before stdout or worksheet publication.
No historical result was recomputed; declared compatibility/blinding is not independent proof.
The [log](log.md) records exact checks and their limits.

The [recovery packet](comparison-experiments.md#implemented-recovery-packet) now implements #111 preparation with eight public-reporter checks plus schedule/trace controls. Candidate execution remains UNSTARTED. #110 remains blocked after two automatic possible-cybersecurity-risk blocks; two uncommitted WIP files are preserved and no reconstruction slice was completed. The [communication packet](comparison-experiments.md#implemented-communication-packet) implements #112 preparation with seven concrete bundle controls and nine public-command checks; its nine supplied technical assessments are explicitly synthetic, and no agent experiment ran. The integrated safe acceptance set passed for these five committed slices; both independent review axes are complete. Missing representative launch/configuration prevents a later ordinary-session claim; it does not block the offline implementation or synthetic packet preparation.

The existing Python CI job now includes one step for the seven permitted guidance, study-account, Q02 and preparation-packet commands. On source commit `b1088ae0f09dac7f3a2137a060e487b87da1c3b7` (tree `5246e987e9bf7d87c48057376388625b144aff2a`), all seven passed locally, along with the current pin/readiness check and compilation of the eight changed committed Python files. The [integration log](log.md#2026-09-05--five-slice-integration-incomplete-overall-goal) records exact commands and limits. This is not full CI or reconstruction acceptance. The narrower #110 attempt reported 13 checks before final validation, documentation and commit were blocked; those observations do not establish completion. Its two WIP files remain outside this acceptance and commit.


## Final handoff

- **Five slices locally implemented:** #107 guidance, #108 Q02 admission, #109 study account,
  #111 recovery preparation and #112 communication preparation. Their acceptance sources are
  described above; the [integration log](log.md#2026-09-05--five-slice-integration-incomplete-overall-goal)
  records the passing bounded acceptance set.
- **Two independent review axes complete:** both reviewed committed base
  `f68caf673ef9ed12aae4f6e43d64b299c5a1ecc9` through HEAD
  `68ed657b60fd81c9a67d877d0b4c7ffd94d057a8`. Standards found no actionable finding or documented-standard
  breach. Spec found no additional verified acceptance gap, scope creep or actionable wrong behavior
  in the five committed slices. Reviewers read code, protocols and public tests; they did not rerun
  suites or experiments, and did not independently cover every packet value. These results support
  only the five-slice boundary.
- **#110 and full #106 remain INCOMPLETE:** two automatic possible-cybersecurity-risk blocks stopped
  reconstruction work. The two untracked WIP files remain preserved outside acceptance. The narrower
  attempt's reported 13 checks are partial progress only. Resolving the automatic execution block is
  required before that slice can resume; operator approval or a model change alone does not override
  safety restrictions.
- **Both candidate experiments remain UNEXECUTED:** effective configuration, actual-run budgets,
  grading isolation and run authorization must be established before execution; adoption requires
  later repeated evidence. Prepared packets and passing account checks establish no candidate benefit.
