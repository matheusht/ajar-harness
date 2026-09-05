# Engineering wiki log

Append dated entries. Record durable source ingestion, decisions, implementation evidence and corrections; keep the earlier entries intact. Maintenance conventions are in [AGENTS.md](AGENTS.md).

## [2026-09-05] create | Engineering wiki and implementation goal

The user corrected the earlier request to update an existing LLM Wiki: none existed, and they asked to start one for engineering decisions and other documentation, supplying [Karpathy's LLM Wiki note](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). Read the complete note and adopted a small repository-local Markdown wiki with an index, topic synthesis, maintenance instructions and this append-only log. The [index](index.md) records the source-content hash and reading date.

Seeded [offline engineering evidence](engineering-evidence.md) and [recovery/communication experiments](comparison-experiments.md) from the approved September 5 investigation and six-ticket handoff. Linked the existing decision and engineering indexes without claiming to have ingested or revalidated their full history. Retained original sources in place.

Added the [implementation goal prompt](../research/harness-engineering-2026-09-05/implementation-goal-prompt.md): intent/scope/non-goals/acceptance first; High reserved for planning; the user's allowed implementation model/effort pool; bounded coordination; necessary command-level end-to-end checks; permission boundaries; incremental wiki updates; and the tested/small-diff/no-unnecessary-abstraction completion gate.

Source baselines: research `6a47b64264b6bf8f1edf8923847cfc9952cd1ab8`, reviewed plan `d150f8d04fd902b48f6a5914880637d39e29a2d1`, publication documentation `ed558ad271d008195a5153bdc3dd97312dbc74f2`. Main rechecked at `0d8fe0c4ffb57a3bf1cfd5d4db013113b51d8c8d`, preserving its already-completed guidance overlap in the synthesis.

This entry records planning/documentation only. No implementation worker, model experiment, board service or runtime change was started. No claim is made that wiki maintenance has reduced effort. Production tests are unnecessary for these documentation-only changes.

Verification: a bounded Python link check covered the eight authored/updated Markdown files and resolved all 72 local destinations; every wiki page is reachable from the index. Manual review checked the six ticket references, dependency order, execution-model constraints, four public test boundaries and the explicit experiment stop. Whitespace validation passed for the staged documentation diff. No application or test infrastructure was added.

## [2026-09-05] implement | Start execution and finish guidance slice #107

Started from clean isolated merge `f68caf673ef9ed12aae4f6e43d64b299c5a1ecc9` (main `0d8fe0c4ffb57a3bf1cfd5d4db013113b51d8c8d` plus research/wiki documentation). Branch: `codex/implement-harness-engineering-2026-09-05`. Actual execution setting: one `gpt-6-astra` worker at `low`; planner remains planning-only. Applied the installed `/implement` and Ponytail Full skills, now explicitly named in the [goal prompt](../research/harness-engineering-2026-09-05/implementation-goal-prompt.md). The optional `/tdd` skill was unavailable in installed skill directories; the approved documentation seam still used a failing public check before the repair.

The current #107 body was re-read with `gh issue view 107 --repo matheusht/redteam-harness --json body,state,updatedAt`: OPEN, updated `2026-09-05T18:30:57Z`, matching the local criteria. Reused main's removal of both absent setup references and draft-pin update. Added only current-status navigation in README and the historical architecture summary, a fixed active-reference conformance check, its bounded CLI option and compact temporary CLI regression controls. Entrypoint bytes, repository pins, historical decision files and operational instructions are unchanged.

Checks on this entry's implementation diff against the source baseline above:

- `python3 tools/check-conformance.py --engineering-guidance`: red before the documentation edit (12 checks, 4 failures for the missing current pointers), then green (12 checks, 0 failures).
- `python3 tools/engineering-guidance-test.py`: passed. Temporary copies invoke the actual conformance and overlay-pin CLIs; missing destinations, mirror divergence and reintroduced setup references fail; historical scaffold prose remains allowed. Draft drift is reported as stale by the overlay CLI and outstanding by conformance, explicit draft repin succeeds, authorized drift fails and repin refuses without changing bytes.
- `python3 tools/overlay_pins.py check --json`: 0 failures, 0 stale; readiness remains `draft_not_authorized`, `execution_authorized: false`, with all four pins matching.
- A bounded inline Python check of the six changed Markdown pages resolved all 42 local link destinations.
- `python3 -m py_compile tools/check-conformance.py tools/engineering-guidance-test.py` and `git diff --check`: passed. No typechecker is configured for this small stdlib Python/docs slice.

An initial `python3 tools/check-conformance.py` invocation preceded the bounded-mode decision and stopped at `check_finding_fixtures` with `validator_unavailable` because system Python lacked the pinned JSON-schema dependencies. It is not acceptance evidence. Inspection showed the default path also includes operational and historical checks; those are outside this offline goal, and the narrow option avoids them. No blanket suite result is claimed; final safe regression/review remains pending after the remaining slices. No experiments, target/provider calls, repository pin refresh or historical result recomputation were performed by the accepted checks. Local completion of this slice does not close any tracker issue or establish the six-ticket goal complete.

## [2026-09-05] implement | Offline study account #109

Source baseline: `3c5c8a847e330e89e6cf48ecf14c3cb1022e3bf3`, clean before this slice, on `codex/implement-harness-engineering-2026-09-05`. Continued with the same single `gpt-6-astra / low` worker, Ponytail Full and `/implement`. Current #109 was re-read with `gh issue view 109 --repo matheusht/redteam-harness --json body,state,updatedAt`: OPEN, updated `2026-09-05T18:24:03Z`, matching its approved local mirror and the accounting/testing decisions in #106.

Necessity: existing `research_telemetry._sum_cost` and `flow_telemetry._coverage` preserve useful missing-measurement distinctions, but their engagement-derived denominators cannot report every frozen study assignment or all successful human activity. Reused the existing safe-offline input reader, canonical JSON, digest and duplicate-key conventions. Added one [stdout-only report command](../../tools/study-report.py), one [synthetic CLI test](../../tools/study-report-test.py) and the [public version-1 input contract](../study-report.md). No collector, database, general framework, raw-telemetry reconciler or operational importer was necessary.

The report separates assignment coverage, received/unique receipt coverage and independently supplied actual-work scope evidence. Human active duration, elapsed duration, machine effort, tokens and cost each retain their own measurement/completeness limits. Complete totals cite a declared scope and require its supplied complete-work basis, all applicable measurements and nonoverlap. Explicit N/A is separate from null unknown. All known received costs without a scope basis remain incomplete; one unknown cost remains incomplete even with complete inventory evidence. Identical receipt redelivery is deduplicated, conflicts fail, and distinct valid IDs remain separate. Known interval overlap and explicit nesting retain qualified sums unless an attributable declared allocation resolves them. Development, maintenance and unreconciled imports remain separate. The frozen phase inventory includes ordinary `execution` and every approved overhead category, without inventing work in unused phases.

Case terminal state, produced inventory, supplied independent assessment eligibility and comparison contamination remain distinct. Declared and observed configuration/provenance are visible; floating aliases and missing loading evidence are qualified. Definition hashes bind bytes, not when they were frozen. Eligibility, allocation and completeness are supplied attributed assessments, not proof inferred from a name or hash. The command computes no winner or causal effect and neither runs nor authorizes an experiment.

Checks on this slice's implementation diff against the baseline above:

- `python3 tools/study-report-test.py`: initial red check failed because the public command did not yet exist; final **50 synthetic public-command checks passed**. Every invocation uses temporary input files, actual exit status/JSON output and an exact before/after byte-and-file-inventory comparison. Cases include complete, failed, interrupted, blocked, incomplete, no-output and unobserved assignments; multiple arms/repeats; partial cost and unknown scope; duplicate delivery, conflicting copies and distinct equal-looking IDs; malformed/cross-case identities and duplicate JSON keys; overlap/nesting, sourced allocation and unknown-allocation refusal; explicit N/A; development/maintenance and unreconciled imports; loading/configuration uncertainty, late freeze and nonindependent assessment; decimal ceilings and known overruns despite unknown completeness or unresolved overlap.
- `python3 -m py_compile tools/study-report.py tools/study-report-test.py`: passed. No typechecker is configured; the tool needs no additional dependency installation.
- Bounded Markdown link check over the contract and three updated wiki pages: all 38 local destinations resolve. `git diff --check`: passed.

The command reads only the two requested offline files and emits stdout; source references are preserved but not opened. It disables import bytecode writes and creates no authority or coordination state. Historical/operational conformance and the blanket CI suite were not run. Final safe regression and independent Standards/Spec review remain pending after the remaining slices. #109 has local implementation evidence; tracker closure, remote mutation and experiments remain outside this slice.

## [2026-09-05] implement | Q02 input admission #108

Source baseline: `ade080e64861b5390633fa39d8aaffef491d8f2b`, clean before this slice, on
`codex/implement-harness-engineering-2026-09-05`. Continued with the same single
`gpt-6-astra / low` worker, Ponytail Full and `/implement`. Current #108 was read with
`gh issue view 108 --repo matheusht/redteam-harness --json body,state,updatedAt`: OPEN,
updated `2026-09-05T18:24:01Z`, matching the approved local mirror and #106 decisions 2–3.

The existing [Q02 command](../../tools/q02_compare.py) now emits inventory with version, source,
case/run and exact measurement-byte binding. Its public verdict/helper admission validates present
malformed dimensions before handling incomplete evidence. A separate source-bound attributed
eligibility assessment retains M1 legacy-package units and explicitly maps them to M6 root-cause
groups; it also records frozen-rule unit compatibility. Notes and unsupported revisions can remain
inventory when excluded. Missing support is inconclusive; wrong types, duplicates, contradictions,
blank assertions and changed bytes are bounded errors with no verdict/license. Bound waste evidence
is required only when asserted. Existing optional cost behavior remains unchanged.

Reused existing source locks and safe-offline readers. Removed unused loose package-reading helpers;
kept the private frozen rule for rule-only self-tests. Named root/arm identity, source bytes and
quarantine are explicitly rechecked under the same locks immediately before publication, alongside
input/reference byte rechecks. No rejecting post-publication context exit or shared kernel API
change was added. [The input contract](../q02-admission.md) documents the supported legacy layout,
references and declarations. A blinding or compatibility declaration remains attributed evidence,
not independent proof. The frozen checkpoint, threshold, license and historical probes are unchanged.

Checks against the baseline plus this slice:

- `tools/q02-admission-self-test.py`, using the existing main-checkout `.venv/bin/python`: first red
  because `measure` lacked case/run arguments; final **99 disposable benign controls passed**.
  The real CLI covers complete bound input, all required missing/malformed dimensions, distinct
  package/group units, unsupported/excluded layouts, missing/changed references and waste binding.
  Additional public-helper and command hooks cover source/quarantine/reference publication races.
- `q02_compare.py --self-test` with that interpreter: passed the unchanged checkpoint and private
  frozen-decision controls. These are separate from admission acceptance.
- The three existing Q02 checks from `quarantine-self-test.py` were executed in isolation from its
  unrelated suite. A temporary wrapper used their unchanged check bodies with disposable plain-lock
  directories and a malformed quarantine marker, replacing only kernel-initializing fixture setup.
  Preregistration quarantine before output, root rename during measurement and final-admission
  quarantine before stdout/worksheet all passed. This is not a blanket quarantine-suite result.
- Python compilation, `git diff --check` and a bounded link check over the input contract and changed
  wiki pages passed. No typechecker is configured; no dependency installation was required.

These checks create no live sessions, initialize no record kernel and recompute no historical result.
Source files and the portable checkpoint remain untouched. No tracker mutation or experiment was
performed. #108 has local implementation evidence; #110–112 and final safe regression/independent
review remain pending.

## 2026-09-05 — #111 recovery comparison preparation

On clean implementation baseline `ea3e5c69222c9a1a471915af56bf9485429b53ea`, the same single
`gpt-6-astra / Low` worker continued Ponytail Full and `/implement`, with no nested delegation.
The approved [#111 packet](../experiments/recovery-v1/README.md) now contains synthetic document
v1/v2, a scheduled correction, recorded-but-unsupplied result, cooperative pause, and simulated
artifact write/loss-before-receipt accounts. Three cases are paired across the present baseline
and the historically inspected OpenAI Agents Python SDK pin. Persisted no-summary rollover is
separate and optional. Required contract, fixed case ordering/access, isolated reference grading,
whole-study overhead/repair ceilings, development/maintenance allocation and readiness/stop rules
are explicit. No effective run configuration or run authorization was supplied.

The present baseline's `tools/work_queue_driver.py` and `tools/claude_work_session.py` Git blob IDs
match the historical research baseline `6a47b64264b6bf8f1edf8923847cfc9952cd1ab8`: respectively
`0a068b53f735f323207277dd6399de95fbaa9c57` and `796a27be735f4b57f1753f72ac7d40c69c7aca32`.
This was checked with `git rev-parse <revision>:<path>` for each pin/path, without reading or
executing those internals. Historical source/test inspection remains the provenance; neither
blob equality nor the SDK pin proves an installed configuration or ordinary-session behavior.

Checks on this baseline plus the slice:

- `python3 tools/recovery-packet-test.py`: initial red because the packet definition did not exist;
  final schedule/access/grader/trace assertions and **8 real public-command checks passed**. Includes
  all six illustrative cases, deterministic output, a complete fictional scope, missing case,
  unknown measurements, failed/contaminated output, unknown loading, malformed binding and rejected
  extra schema fields. Source metadata remains linked through references, not a reporter extension.
- `python3 tools/study-report.py --study docs/experiments/recovery-v1/definition.json --observations
  docs/experiments/recovery-v1/observations.json`: accepted; six assigned/observed outputs, zero
  independent eligibility passes, incomplete metric totals and candidate execution UNSTARTED.
- `python3 tools/study-report-test.py`: existing **50 synthetic public-command checks passed**.
- `python3 -m py_compile tools/recovery-packet-test.py`, `git diff --check`, and a bounded check of
  **49 local links** across packet Markdown and the changed topic/index/evidence pages passed.
  Packet tests compare both source and temporary input bytes/file inventories before and after.

The fixture counts and receipts are illustrative, not measured implementation labor. Source
citations/expected traces cannot earn candidate passes. No adapter, runtime, dispatcher, persistence
backend, provider/model call, actual crash, engagement access or remote mutation was performed.
The public reporter is unchanged. Local standards/spec inspection found no remaining slice issue;
final independent review and broader safe regression remain pending with #112.

Separate status: #110 remains pending after an automatic safety check blocked its implementation
attempt. No #110 artifact was committed; this entry does not mark that slice complete or retry it.
Recovery candidate execution remains **UNSTARTED**. Missing representative ordinary-session launch
configuration limits future claims, not completion of this preparation packet.
