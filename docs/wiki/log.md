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

## 2026-09-05 — #112 communication comparison preparation

On clean baseline `43eab2e8edaffb6ca3f00179c007a7ea6dcf0788`, the same single
`gpt-6-astra / Low` worker continued Ponytail Full and `/implement`, with no nested delegation.
The [communication packet](../experiments/communication-v1/README.md) supplies three harmless
workshop-document cases: complete sources, complementary evidence and a scheduled late correction.
All three arrangements retain complete source access: serial, capable curated direct handoff,
and the identical parallel arrangement plus bounded notices. The source-key distinction is physical
in the prepared artifacts: worker sources, later releases, curation examples, grader references and
illustrative finals occupy separate paths enumerated and byte-bound by a manifest.

The packet fixes case/arm ordering, role assignment, independent initial commits before curation,
matched external observation/correction releases, exact grader bundles, five notices per packet,
and total shared budgets including workers, coordinator, reads/posting, curation and human repair.
Each notice retains source version, uncertainty and provenance; the stale time notice survives beside
its named correction. Retention, delivery opportunity, use, correctness and usefulness remain distinct.
An acknowledgment does not establish comprehension. The permitted progression remains a mechanism
pilot followed, only if justified, by a preregistered repeated paired study; no adoption is authorized.

Checks on the baseline plus this slice:

- `python3 tools/communication-packet-test.py`: initial red because manifest.json was absent; final
  **7 bundle controls and 9 real public-command checks passed**. It copies exact allowed files into
  temporary worker/release/grader bundles and compares bytes/inventories. Negative controls reject
  leaked grader material, other-case answers, premature corrections and unequal parallel assignment.
  Notice fields/caps, source revisions, committed observations, grader output names, matched
  configuration, release schedule and source hashes are checked against the prepared data.
- `python3 tools/study-report.py --study docs/experiments/communication-v1/definition.json
  --observations docs/experiments/communication-v1/observations.json`: accepted all **9 assigned and
  observed** cases, with **9 supplied eligible artificial outputs** and complete fictional metric
  totals. The account's loading, completeness and independent assessments are invented fixture
  assertions, not actual observations. No candidate receives a measured success from this result.
- Public-command adverse controls retain contaminated technical eligibility for cross-case leakage,
  extra access and extra effective budget; missing/failed work and unknown loading/cost stay visible.
  A positive token receipt exceeds the frozen zero-token ceiling. Wrong definition binding and added
  reporter fields fail; no reporter schema change was needed.
- `python3 tools/recovery-packet-test.py`: existing schedule/trace checks and **8 public-command checks
  passed**. `python3 tools/study-report-test.py`: existing **50 public-command checks passed**.
- `python3 -m py_compile tools/communication-packet-test.py`, `git diff --check`, and a bounded check
  of **75 local documentation links** across the packet README and changed topic/index/evidence pages
  passed. Tests preserve packet source bytes/inventory and report-input bytes/inventory.

Local standards/spec inspection found no remaining slice issue. These are concrete artifact/account
checks, not a runtime access-control test, model experiment, proof of actual grading independence,
measured authoring effort or communication benefit. Effective runtime configuration and run
authorization are absent; the agent experiment remains **UNEXECUTED**. No provider, paid/live call,
board service, adapter, execution runtime, engagement access or remote mutation was performed.
The existing reporter and #111 source files are unchanged. #110 remains blocked/pending after its
separate automatic safety check; final integration/safe regression and independent review are next.


## 2026-09-05 — five-slice integration, incomplete overall goal

The five local slices #107, #108, #109, #111 and #112 are implemented. This bounded integration
adds one step to the existing Python job in `.github/workflows/conformance.yml`; it introduces no
runner, framework, job or service and preserves the other workflow steps. The same Astra Low /
Ponytail Full worker performed the integration without nested delegation. Source revision checked:
`b1088ae0f09dac7f3a2137a060e487b87da1c3b7`, committed tree
`5246e987e9bf7d87c48057376388625b144aff2a`. Only CI wiring and these factual wiki pages change
in the integration; the checked committed Python and packet data remain unchanged.

Each command below ran once in the integration, using the existing interpreter
`/Users/matheusvsky/Documents/trab/llm-redteam-harness/.venv/bin/python` (denoted `$PY` below),
with no dependency installation. Every command exited 0:

- `$PY tools/check-conformance.py --engineering-guidance`: 12 checks, 0 failing.
- `$PY tools/engineering-guidance-test.py`: public CLI navigation, mirror, history and draft/frozen
  pin controls passed.
- `$PY tools/study-report-test.py`: 50 synthetic public-command checks passed.
- `$PY tools/q02-admission-self-test.py`: 99 public controls passed.
- `$PY tools/q02_compare.py --self-test`: frozen checkpoint/rule self-tests passed.
- `$PY tools/recovery-packet-test.py`: schedule/access/trace controls and 8 public-command checks
  passed; candidate execution UNSTARTED.
- `$PY tools/communication-packet-test.py`: 7 bundle controls and 9 public-command checks passed;
  agent experiment UNEXECUTED.
- `$PY tools/overlay_pins.py check --json`: 0 failures, 0 stale; current readiness is
  `draft_not_authorized`, `execution_authorized: false`.
- `$PY -m py_compile tools/check-conformance.py tools/communication-packet-test.py
  tools/engineering-guidance-test.py tools/q02-admission-self-test.py tools/q02_compare.py
  tools/recovery-packet-test.py tools/study-report-test.py tools/study-report.py`: passed.
- A bounded inline `python3` Markdown-link check over `docs/wiki/{index,engineering-evidence,comparison-experiments,log}.md` verified 65 local destinations and their supplied heading anchors.
- `git diff --check`: passed.

The earlier #108 entry preserves the three targeted Q02 regressions: preregistration quarantine
before output, root rename during measurement and final-admission quarantine before stdout/worksheet,
using disposable plain-lock fixtures. Those earlier results were not rerun or broadened here.
No default conformance command, whole CI, operational suite, historical recomputation, candidate
experiment, target/provider/model/paid call or remote mutation was performed. Packet preparation
is complete; actual recovery and communication candidate experiments remain unexecuted.

Correction to the prior pending #110 status: two attempts were blocked by automatic safety checks.
The narrower attempt reported 13 checks, but final validation, documentation and commit never
completed. Preserve that as observed progress only. Two uncommitted WIP files,
`tools/inspect-dossier.py` and `tools/dossier-inspector-test.py`, remain preserved and excluded from
integration testing, compilation, staging and this commit. Neither file was read or changed during
this integration. There is no reconstruction acceptance or completed #110 slice. Independent
Standards and Spec review of the committed five-slice diff remains pending; the overall #106
six-ticket goal is INCOMPLETE.


## 2026-09-05 — independent review and final bounded handoff

Two independent read-only review axes completed over committed base
`f68caf673ef9ed12aae4f6e43d64b299c5a1ecc9` through HEAD
`68ed657b60fd81c9a67d877d0b4c7ffd94d057a8`:

- Standards: no actionable finding or documented-standard breach. Existing input/canonicalization
  reuse, Q02 consolidation/deletion, scoped CI and preserved wiki history/status fit repository rules;
  no speculative refactor was advised.
- Spec: the known #110 acceptance remains incomplete. No additional verified acceptance gap, scope
  creep or actionable wrong behavior was found in committed #107, #108, #109, #111 or #112.

Reviewers inspected actual code, protocols and public tests. Neither reran suites or experiments;
review did not independently cover every packet value. Both left blocked WIP untouched. These
results support five locally implemented slices with integrated acceptance passed, not full #106
completion. Earlier pending-review entries remain as dated observations, superseded by this entry.

The same Astra Low / Ponytail Full worker updated only current wiki status and the concise
[handoff checklist](engineering-evidence.md#final-handoff). #110 and full #106 remain INCOMPLETE
because of two automatic possible-cybersecurity-risk blocks. Its two untracked WIP files remain
preserved, unread, unrun, unchanged and excluded from staging/commit. The reported 13 checks from
the narrower attempt remain partial progress; final validation, documentation and commit did not
complete. The actual next requirement is resolution of the automatic execution block before #110
can resume. Operator approval or changing models alone does not override safety restrictions.

The recovery and communication packets remain preparation only; both candidate experiments are
UNEXECUTED. Future effective configuration, actual-run budgets, isolation/authorization and repeated
evidence remain prerequisites for execution or adoption as applicable. No code or packet data changed,
no acceptance suite was rerun, and no remote mutation or issue closure was performed. Handoff checks
are limited to changed wiki local links/heading anchors, current-status consistency and whitespace.

Bounded inline `python3` verification passed all 67 local links/heading anchors across the four
changed wiki pages and confirmed consistent current review/incomplete status. `git diff --check`
passed. Executable inputs are unchanged, so the existing integrated acceptance evidence is retained.


## 2026-09-08 — #110 read-only inspector and bounded integration

Correction to the September 5 handoff: the two automatic possible-cybersecurity-risk errors were
execution observations, not a demonstrated finding that this offline engineering task was prohibited.
The parent had converted those observations into a blanket stop. After the user's September 8
clarification and reassessment of the actual ticket/WIP, scoped work resumed through normal tools.
No safety bypass or alternate execution route was used. The current operations and checks below
succeeded; the old errors remain part of the dated record, including the narrower attempt's reported
13 checks and its unfinished validation/docs/commit at that time.

The same `gpt-6-astra / Low` implementation worker continued Ponytail Full and `/implement`, without
nested delegation, from HEAD `5267ced0747cd33c9441db73e90b7258a0ebc46b` (tree
`eb9cce5a2af30395efa79346125b94a6e062281d`). The two preserved WIP files were reused. The completed
[inspector](../dossier-inspector.md) invokes existing bound reads, read-only reduction, reference index
and pure projections, buffers the result until final admission checks succeed, and prints JSON only.
No shared reducer, index, lock, view, schema, operational gate or filing-lifecycle code changed.

The final source bytes checked were `tools/inspect-dossier.py` SHA-256
`b319471764bdd20b395f60c03bd045a132d695792bbf419a0eab8fcdc77d7bd3` and
`tools/dossier-inspector-test.py` SHA-256
`77eb5ffc72b0d1abfc0988e356ca3b7d931f798de16ca1b46365680eb7fac802`, on that baseline plus this slice.
CI adds the public inspector test to the existing scoped Python step; no job/service/framework or
dependency was added. The command documentation maps all ten acceptance criteria to output and checks.

The resumed inspection found and fixed a concrete optional-input defect: duplicate-key JSON raises
`RecordError`, which the WIP's separate-supplement catch did not handle. It now marks that supplement
invalid beside admitted base evidence; indexed duplicate/malformed/colliding records still reject
base admission. Invalid duplicate-key snapshots remain failed projections. Supplied stale task labels
and loading stay visibly attributed/stale; exact current, exact older and mismatched external revision
bindings remain distinct. Source environment, outstanding citation-review reasons/subjects and report
supersession events are explicit. No inference from external spelling or a supplied decision changes
claim state.

Static workshop fixtures use plain disposable files and a preexisting plain lock, with no lifecycle,
initializer, publisher or writing renderer call. The additional outstanding-review fixture initially
failed `review_material_not_in_input_set`, then `review_freshness_not_bound`; its declared inputs and
prior review-run binding were corrected to satisfy the unchanged reducer. Focused development checks
then passed 21 and 23 public invocations. The final acceptance run below occurred once after the final
executable edit. Every public invocation compares source bytes and file/directory inventory and supplied
input bytes; final identity rejection prints no valid summary. The original three presentation omissions
are recovered in the new output, while existing generated-view bytes remain compatible.

Using the existing interpreter `/Users/matheusvsky/Documents/trab/llm-redteam-harness/.venv/bin/python`
(denoted `$PY` below), without installing dependencies, every final command exited 0:

- `$PY tools/dossier-inspector-test.py`: static admission and **23 public-command checks passed**;
  no source mutation.
- `$PY tools/check-conformance.py --engineering-guidance`: **12 checks, 0 failing**.
- `$PY tools/engineering-guidance-test.py`: public navigation, mirror, history and draft/frozen pin
  controls passed.
- `$PY tools/study-report-test.py`: **50 synthetic public-command checks passed**.
- `$PY tools/q02-admission-self-test.py`: **99 public controls passed**.
- `$PY tools/q02_compare.py --self-test`: frozen checkpoint/rule self-tests passed.
- `$PY tools/recovery-packet-test.py`: schedule/access/trace controls and **8 public-command checks
  passed**; candidate execution UNSTARTED.
- `$PY tools/communication-packet-test.py`: **7 bundle controls and 9 public-command checks passed**;
  agent experiment UNEXECUTED.
- `$PY tools/overlay_pins.py check --json`: **0 failures, 0 stale**, readiness `draft_not_authorized`,
  `execution_authorized: false`.
- `$PY docs/research/harness-engineering-2026-09-05/checks/reconstruction_probe.py`: original six-view
  baseline bytes matched; all three omitted-fact variants remained byte-identical; the visible-revision
  positive control changed only progress. Temporary outputs were removed. This is a pure historical
  renderer probe, not an operational replay or historical finding recomputation.
- `$PY -m py_compile tools/inspect-dossier.py tools/dossier-inspector-test.py`: passed.

No default conformance command, whole CI, operational suite, real engagement, provider/target/model/paid
call, historical finding recomputation or remote mutation ran. These are synthetic metadata and packet
accounting checks, not operator-time savings, verified outside outcomes or proven cognitive independence.
The earlier five-slice independent review retains its exact scope. New #110/integration independent
Standards and Spec review is pending, so final #106 acceptance is still incomplete. Both experiment
packets remain UNEXECUTED; effective configuration, actual-run budget, isolation/authorization and later
repeated evidence remain prerequisites for execution or adoption as applicable.

Final bounded documentation verification passed 74 local links/heading anchors across the command
documentation and four wiki pages, and confirmed consistent current review-pending status.
`git diff --check` passed. No executable files changed after the final acceptance run.


## 2026-09-08 — all six scoped local slices accepted

Separate Astra Low Standards and Spec reviews completed over exact base
`5267ced0747cd33c9441db73e90b7258a0ebc46b` through source HEAD
`a0f6a480028b630fbb85dd1fbfa448dca28d8767`. Standards found no actionable violation; dense
summary/reference-selection code was not a justified refactor. Spec found no verified missing or
partial #110 criterion, scope creep or wrong behavior: all ten criteria are represented, existing
review-hash selection is followed, indexed base failures remain failures, optional-input failures
are qualified, and stdout waits for final source identity checks.

Both reviewers inspected code, public tests, documentation and shared read contracts. Neither reran
tests or claimed real-world benefit, cognitive independence or actual loading. The earlier five-slice
reviews remain pinned to `f68caf673ef9ed12aae4f6e43d64b299c5a1ecc9` through
`68ed657b60fd81c9a67d877d0b4c7ffd94d057a8`. The already-passed September 8 execution hashes and
commands above correspond to final source commit `a0f6a480028b630fbb85dd1fbfa448dca28d8767`.

All six scoped local slices are accepted with integrated tests and both independent review axes done.
This supersedes the earlier dated pending-review status; previous entries are preserved. Both candidate
experiments remain UNEXECUTED. Their effective configuration, actual-run budget, isolation/authorization
and later repeated evidence remain prerequisites for execution or adoption as applicable. This work
performed no issue closure or remote mutation; remote issue state was not re-queried. This final update changes only
four existing wiki pages, so no acceptance suites were rerun and no code, tests or packet data changed.

Bounded verification passed 72 local links/heading anchors and current acceptance-status consistency
across the four changed wiki pages. `git diff --check` passed. Remote issue state was not rechecked.


## 2026-09-10 — PR scope preparation

The user separately authorized pushing the named implementation branch and opening a PR against main.
Fetched origin/main is `fd40756c304c80acd14f541f5447e229a7b510c3`, already the merge base/ancestor of
`feb6604c1649a8690f4696aab8bf521aa3da4386`; no main integration was required. The actual remote-main
diff included inherited pre-implementation stop-hook changes from local history. Only
`tools/claude-stop-hook.py` and its test were restored to origin/main to exclude that unrelated
operational behavior from the PR. Existing history and all approved engineering research, publication
records, six implementation slices, synthetic packets and wiki evidence remain. No engagement path
is present in the final changed-file set.

`git diff a0f6a480028b630fbb85dd1fbfa448dca28d8767 --` over the scoped executable files/tests,
shared record readers, schemas, requirements and both packet directories was empty. The source-pinned
September 8 integrated acceptance evidence therefore remains applicable; those suites were not rerun.
The existing interpreter ran `tools/check-conformance.py --engineering-guidance`: 12 checks, 0 failing,
including mirror/current draft pins. `git diff origin/main -- tools/claude-stop-hook.py
tools/claude-stop-hook-test.py` was empty after the scope correction. The operational stop-hook suite
and default/full conformance were not run.

The approved research retains one intentional trailing-whitespace line in the canonical captured
`q02-whitespace-waste-description.stdout` probe. Whole-PR `git diff --check` reports that historical
input/output evidence; it was not rewritten to conceal its original bytes. New preparation changes
pass whitespace checks. No other inherited changed path was identified outside the approved
research/guidance/implementation deliverable. No issue closure or merge is authorized by publication;
the two requested new review passes are separate from the prior local acceptance record.


## 2026-09-10 — clarify inspector code digest in PR review

At PR source HEAD `84c2ecec70cd88386c6b34080747af53cdfb2e90`, the phrase “inspector's source-byte
hash” was read as an aggregate dossier hash. The existing top-level `inspector_sha256` already hashes
the inspector Python file; `source.file_digests`, scope/ledger hashes and directory identity describe
the dossier. The #110/#106 contract requires source identity/digests, not a new aggregate snapshot
contract. Command documentation now names these existing fields explicitly. No executable or test
changed, and prior source-pinned acceptance remains applicable; no suite was rerun for this wording
clarification. Local documentation links/anchors and whitespace were checked before commit.


## 2026-09-11 — future evaluation applications and XBOW comparison

Added [future evaluation applications](future-evaluations.md) and linked it from the index at the user's
request to preserve useful cases for later work. The page synthesizes the prior Gill/MCP and Madhu
series comparison, plus the September 11 reading of XBOW's guardrails article/whitepaper and the
user-supplied X excerpt. Mutable external sources and the pinned harness-kit revision are identified
on the page. Local contracts were checked at `6fd04bfbc128b95d201b38f82dc467e7c05fdcfb`.

The backlog names benign manipulated conditions, expected observations, metrics and existing hooks.
It separates evaluation jobs, independent grading, evidence quality and whole-trajectory economics;
reuses the prepared recovery/communication packets; and records the documented gap between our
containment and XBOW's described egress/action controls without claiming comparative efficacy.
The persistence critique and all additional experiments/controls remain recommendations, not adopted
doctrine or implementation. Both prepared candidate experiments remain UNEXECUTED.

Only this topic, index and append-only log changed. Local links/anchors, status/conclusion wording
and whitespace were checked; no runtime/test/packet/source records changed, no experiment ran and
no acceptance suite was rerun. No remote mutation is part of this documentation slice.


## 2026-09-13 — preserve frozen history and repair delivery CI

PR #113 run `34515196852` stopped at the canonical v3 checker pin. Its expected SHA-256 was
`85d18ca3588d4ba3a3b80494dbbdb18c8233cbc1a483b8d1e21bed573d410ea3`; base `fd40756c` already had
`d2314ffbea18c320a5c965050a4c7f0356b5f674d48315c769c4c267b07ae911`, and the PR checker has
`8bac09dee0e54e5b42cd56e8942f69e6c76d4d7d243190a2f2376c65ce0bbdcd`. The PR changes that input too;
this is not dismissed as an unrelated baseline failure. The other five frozen inputs remain intact.

Following the existing builder's rotate-CAMP_ID guard and v2→v3 supersession convention, the current
campaign is now v4 (`behavioral-canonical-v4-2026-09-13`). It was built from committed source
`a63eef8f65a6274f75d730e8da5adf5bd88cfb78` with the existing builder, updated only for the new revision
identity/date/note. The workflow and active README point to v4. Every preexisting v3 byte is preserved;
only its new supersession note is added. All five candidate definitions and patch bytes, the seed and
non-checker pins are unchanged. No old result was regraded, and no v4 candidate run or efficacy claim
was created. Later changes to any frozen input require another explicit revision, never in-place
refresh of this historical pin. No evaluator/scorer/gate behavior was weakened.

Using the existing main-checkout `.venv/bin/python` interpreter, the following local checks passed on
that source plus this rotation, each with exit 0:

- `tools/build-behavioral-campaign.py`: built five candidates.
- `tools/hash-campaign-inputs.py --check evals/behavioral/campaigns/behavioral-canonical-v4-2026-09-13/campaign-manifest.json`:
  intact; `tools/hash-campaign-inputs.py --self-test`: passed.
- A disposable copy passed the real hash-check CLI, then failed with exit 1 after only its copied
  checker bytes changed. Direct comparisons proved unchanged v3 tracked bytes, normalized candidate
  definitions, all five patches, seed and non-checker pins. No new test framework was added.
- The eight scoped commands passed: `tools/check-conformance.py --engineering-guidance` (12/0),
  `tools/engineering-guidance-test.py`, `tools/study-report-test.py` (50),
  `tools/dossier-inspector-test.py` (23), `tools/q02-admission-self-test.py` (99),
  `tools/q02_compare.py --self-test`, `tools/recovery-packet-test.py` (8 plus controls),
  `tools/communication-packet-test.py` (7 bundle/9 public checks).
- Every command in the eight previously skipped workflow steps passed with `--self-test`:
  `tools/score-routing.py`, `tools/score-false-discovery.py`, `tools/run-hermetic-bola.py`,
  `tools/run-hermetic-fakemodel.py`, `tools/run-hermetic-api.py`, `tools/run-qualification.py`,
  `tools/obfuscation-converter.py`, `tools/stego-converter.py`, `tools/covert-channel-converter.py`,
  `tools/covert-channel-evidence.py`, `tools/tollbooth-digest-adapter.py`,
  `tools/casebook-retrieval-index.py`, `tools/encoding-robustness-eval.py`,
  `tools/generate-payload-proposal.py`, `tools/payload-proposal-hermetic-test.py`.
- `python3 -m py_compile tools/build-behavioral-campaign.py` and new-change whitespace checks passed.

These are offline/synthetic self-tests, not real engagement/provider/model execution. Prior scenario
packet experiments remain unexecuted. The pending `a63eef8f` wiki assessment is included in publication.
Full hosted CI will validate the pushed head separately; no merge or issue closure occurred here.

## [2026-10-23] consolidate | Product direction, native research and evidence limits

At the operator's request, reviewed the product/engineering discussion and current
documentation before recording the north stars and updating agent navigation.
Implementation and experiment follow-up remain deferred. Source baseline:
`cf8b213aa9979297def3b71f8f63a05dcc7945d6`; isolated documentation branch:
`codex/harness-direction-docs-20261023`. The dirty primary checkout and candidate
implementation branch were read as evidence and not edited by this slice.

Added [product and engineering direction](product-and-engineering-direction.md),
[dated native status](native-research-status.md), and an
[October discussion record](../research/research-direction-discussion-2026-10.md).
Preserved the detailed [source review](../research/native-session-source-review-2026-10.md)
with a historical-status notice and corrected relative code links. Its body retains
the original research claims and later-choice pointers; this is not a new online
source verification. Requested but unfinished reading leads stay explicitly open.

The synthesis records model/provider independence, native research as the chosen
direction, within-run adaptation, depth and useful partials, continuity, fresh
review, shared limits, optional diagnostic comparison, and deletion before added
mechanism. Root entrypoints remain short routers. README now reflects the domain-neutral
product. The wiki separates October direction from September delivery. Dated scope
notes preserve accepted decisions and the August autonomy aspiration without
turning their old observations into current capability claims.

Source/evidence review corrected the candidate documentation: a controller now
exists but is unqualified; generic source runtimes do not prove generic model or
provider support; connection/byte/time limits do not establish monetary accounting;
review-file binding does not prove independent review. The continuation smoke calls
the controller function with a synthetic child CLI. Its tests were added after
implementation. The comparison specification's outcomes and decision rule are
unchanged; its source/test descriptions and revision-freeze instruction are clarified.
Earlier receipts keep their bytes, hashes and historical revision scope.

Verification for this documentation slice:

- Changed local Markdown destinations and heading fragments resolve; all new topic
  pages are reachable from root/wiki pointers. Root mirrors remain byte-identical,
  root sections 0–7 remain, and the changed paths are documentation only.
- Independent read-only reviews checked navigation/hierarchy and implementation
  claims. The coordinator checked the recorded operator corrections and addressed
  the review findings before final validation.
- `python3 tools/check-conformance.py --engineering-guidance`: navigation and mirror
  checks pass; the combined command exits 1 for two stale draft-study overlay pins.
  `overlay_pins.py check --json` reports the same two paths on the unchanged baseline
  and this documentation branch, with zero validation failures and
  `execution_authorized: false`. The pins were not refreshed.
- Whitespace validation and retained-review import checks pass. No application,
  controller, provider, target or hosted-CI run is part of this documentation pass.

This entry records documentation and source inspection. It does not adopt a runtime,
authorize an engagement, update target readiness, merge a branch, or close an issue.

### Correction pass (same day)

The review pass separated the root's generic three-boundary fence from the
LLM-application domain examples, which now live in
[LLM domain scope](../agents/llm-domain-scope.md). It removed the target-specific
standing-grant exception from portable root and bootstrap instructions; a
target-specific grant now belongs only in that target's signed scope. It restored a
concrete evidence test to the root prime directive, restored the installed
engineering-skills pointer, clarified explicit bootstrap invocation, aligned
repository-visibility wording, and replaced branch-specific language with the stable
candidate-route name. The attempt/negative/bundle lifecycle is recorded as a forward
pointer to PR #193 until `docs/research-lifecycle.md` lands. The direction page now
labels itself as a maintained synthesis rather than an accepted ADR.

## [2026-10-23] correct | Live research-lifecycle citations and overlay pins

PR #193 landed on main. The forward pointer is now the local
[research lifecycle](../research-lifecycle.md) link in the README, both root mirrors
and Decision 0005. This stacked branch carries the landed lifecycle document so its
links resolve before the stack reaches main. Refreshed the draft AB-readiness overlay
pins after the root guidance edit, and split the synthetic bearer sentinel in the
native T02 verifier so the repository secret scan does not mistake a negative test
for a leaked credential.

Verification: `check-conformance.py` reports 898 checks, 0 failing;
`--engineering-guidance` reports 12/12; changed-document local links and anchors
resolve; `git diff --check` is clean. No application, controller, provider, target or
hosted-CI run is part of this correction.

## [2026-11-13] decisions | Record the harness grilling through Q14

At the operator's request, saved the [Q1–Q14 decision record](../research/oslit-harness-grilling-2026-11-13.md)
and linked it from the wiki index, product direction, and 12 November foundation
brief. The source is the operator's current chat replies, including later
corrections. The record covers the research goal, agent-owned environments,
lead/specialist coordination, persistence and closure, real-target comparative
evaluation, operator directions, experiment isolation, and lead-only spawning.
Cross-engagement learning and specialist spawning remain deferred. The complete
plan is still open and implementation remains on hold.

Verification: an independent read-only comparison against the live Q1–Q14 replies
found no blocking mismatch. Added source/version and setup-reproduction details,
and retained real chaining evaluation without assuming every target contains a
flaw. Local document destinations and whitespace checks pass. The system Python
lacked the required validator; `tools/check-conformance.py` passed in the existing
pinned Python environment with `jsonschema==4.26.0`: 900 checks, 0 failing.

This is a documentation-only change. It adds no runtime behavior, authorizes no
target execution, and supplies no new research-capability or adoption evidence.

### Q15 — Ready-task ownership

Added the operator's agreement that specialists claim ready tasks from the
lead-prioritized queue, with one accountable owner per task; the lead may redirect
or reassign work. The [decision record](../research/oslit-harness-grilling-2026-11-13.md#q15--specialists-claim-ready-work)
now covers Q1–Q15. Removed the duplicated question count from the index link so
the record remains the single source of its current coverage. Q16 and the
complete implementation plan remain open. Documentation only; no runtime change
or target run.

### Q16 — Disagreement and independent review

Recorded the operator's agreement to test competing explanations and preserve
uncertainty, with independent review available during the investigation when
needed and retained for final claims and closure. The
[decision record](../research/oslit-harness-grilling-2026-11-13.md#q16--test-competing-explanations-review-when-needed)
now covers Q1–Q16; Q17 remains open. Documentation only; implementation and
target execution remain on hold.

### Q17 — Reviewer context and evidence access

Recorded the operator's agreement that a reviewer starts in a fresh context with
an evidence packet including contrary evidence, can inspect the full knowledge
base, and can run its own checks. The
[decision record](../research/oslit-harness-grilling-2026-11-13.md#q17--fresh-reviewer-context-and-complete-evidence-access)
now covers Q1–Q17; Q18 remains open. Documentation only; no implementation or
target execution.

### Q18 — Failure isolation and uncertain effects

Recorded the operator's agreement to isolate failures, preserve affected work,
check uncertain effects before retrying, and pause dependent tasks while
unaffected work continues. The
[decision record](../research/oslit-harness-grilling-2026-11-13.md#q18--isolate-failures-and-reconcile-uncertain-effects)
now covers Q1–Q18; Q19 remains open. Documentation only; no implementation or
target execution.

### Q19 — Model choice and comparison boundaries

Recorded the operator's agreement to allow different models when useful, retain
the same model in the initial native-agent comparison, and evaluate mixed-model
teams separately. The
[decision record](../research/oslit-harness-grilling-2026-11-13.md#q19--flexible-model-choice-separate-comparative-experiments)
now covers Q1–Q19; Q20 remains open. Documentation only; no implementation or
target execution.

### Q20 — Specialist continuity and handoff

Recorded the operator's agreement to retain specialists while their context is
useful, let the lead replace them, and save work so replacements can take over.
Independent reviewers retain fresh contexts. The
[decision record](../research/oslit-harness-grilling-2026-11-13.md#q20--retain-useful-specialist-context-and-preserve-handoffs)
now covers Q1–Q20; Q21 remains open. Documentation only; no implementation or
target execution.

### Q21 — Native baseline capabilities

Recorded the operator's agreement that the native baseline retains its normal
capabilities, including delegation, with the same model and access. The
[decision record](../research/oslit-harness-grilling-2026-11-13.md#q21--preserve-the-native-baselines-normal-capabilities)
now covers Q1–Q21; Q22 remains open. Documentation only; no implementation or
comparison run.

### Q22 — Real positive evidence and honest negatives

Recorded the operator's requirement for at least one independently reproduced
real finding or chain plus improvement over the native agent, while preserving
honest negative results. The
[decision record](../research/oslit-harness-grilling-2026-11-13.md#q22--require-real-positive-evidence-and-retain-negative-results)
now covers Q1–Q22; Q23 remains open. Documentation only; no implementation or
target execution.

### Q23 — Exploration and evidence integration

Recorded the operator's agreement to allow exploration with incomplete
intermediate capture when scope and cleanup stay enforced, while requiring
inspectable evidence and independent reproduction before claim acceptance. The
[decision record](../research/oslit-harness-grilling-2026-11-13.md#q23--allow-exploration-without-complete-intermediate-capture)
now covers Q1–Q23; Q24 remains open. Documentation only; no implementation or
target execution.

### Q24 — Independent measurement validation

Recorded the operator's agreement to allow tool reuse while requiring the
reviewer to independently verify permissions, effects, and controls, with another
probe when needed. Success messages alone do not establish a claim. The
[decision record](../research/oslit-harness-grilling-2026-11-13.md#q24--independently-validate-the-measurement-not-just-its-output)
now covers Q1–Q24; Q25 remains open. Documentation only; no implementation or
target execution.

### Q25 — Portable engagement contract and native capabilities

Recorded the operator's agreement to standardize the engagement contract,
preserve useful runtime-specific features, and keep research state portable. The
[decision record](../research/oslit-harness-grilling-2026-11-13.md#q25--a-portable-engagement-contract-with-runtime-specific-capabilities)
now covers Q1–Q25; Q26 remains open. Documentation only; no implementation or
target execution.

### Q26 — Evidence-triggered strategy review

Recorded the operator's requirement for fresh strategy review when evidence
shows stalled work or contradictions, with action or an evidence-backed
rebuttal from the lead. The
[decision record](../research/oslit-harness-grilling-2026-11-13.md#q26--require-strategy-review-when-evidence-challenges-progress)
now covers Q1–Q26; Q27 remains open. Documentation only; no implementation or
target execution.

### Q27 — Autonomous lead replacement

Recorded the operator's agreement to replace a lead autonomously when it
repeatedly ignores review without an evidence-backed reason, preserving the
work and one active lead. The
[decision record](../research/oslit-harness-grilling-2026-11-13.md#q27--replace-a-lead-that-repeatedly-ignores-review)
now covers Q1–Q27; Q28 remains open. Documentation only; no implementation or
target execution.

### Q28 — Equal comparison limits and actual usage

Recorded the operator's agreement to use the same generous limits in the initial
comparison, count all agent work, and report actual usage separately. Clarified
the native baseline's meaning; its exact runtime and configuration remain open.
The [decision record](../research/oslit-harness-grilling-2026-11-13.md#q28--equal-comparison-limits-and-separate-actual-usage)
now covers Q1–Q28; Q29 remains open. Documentation only; no implementation or
evaluation run.

### Q29 — Shared research instructions and test ownership

Recorded the operator's requirement to give the native baseline the same
reusable research instructions and establish value beyond them. Also recorded
the correction that the operator will provide the future fresh-target test;
the assistant is not assigned to execute it or the comparison. The
[decision record](../research/oslit-harness-grilling-2026-11-13.md#q29--share-reusable-research-instructions-with-the-baseline)
now covers Q1–Q29. Documentation only; no implementation or evaluation run.

The remaining-requirements review found sufficient direction to draft the
engineering plan. Runtime integration, research environments, autonomy/recovery,
and usable delivery remain design work for that plan; no additional mandatory
interview question was identified. Plan approval and implementation remain open.

## [2026-11-14] plan | Complete OSLit engineering design

Drafted the [complete engineering plan](../research/oslit-engineering-plan-2026-11-14.md)
against source `89bcede2c1e62573767017251e8734f211fa3573` and the operator's
Q1–Q29 decisions. It covers runtime/model integration, all supplied target access
modes, team coordination/review/recovery, and usable delivery. The plan maps
existing code to keep, simplify, replace or delete, proposes one new-route state
owner, identifies the initial-authority policy change, and specifies milestones,
failure-first E2E scenarios and a complete requirement map.

Current code inspection found an existing scope-driven setup-to-closeout path;
the older foundation brief's missing-handoff observations remain historical.
Official runtime documentation and local CLI version/help were inspected, without
starting a runtime or provider session. Two architecture candidates and independent
document review informed the synthesis. Review corrections clarified network
enforcement, early aggregate-limit enforcement and lead replacement when review
creation is ignored.

The operator owns the later fresh-target test and native comparison. This is a
proposed plan, not approval, implementation, qualification or adoption. No code,
provider call, target run or engineering E2E was performed; only document/source
checks were completed. Existing code and historical evidence were preserved.

Draft checks: local links and the Q1–Q29/E01–E16/M0–M6 maps passed; independent
review findings were corrected and rechecked; `git diff --check` passed.
Structural conformance passed 900 checks with zero failures in the existing
`/tmp/pr209-conformance-venv` environment matching `requirements-ci.txt`. The first
system-Python attempt lacked the pinned validator dependencies. No proposed E2E
scenario or operator-owned research test was run.

## [2026-11-14] direction | Codex/OMP, multi-day work and architecture guidance

The operator endorsed the complete plan's direction while rejecting OpenCode as a
required runtime and a fixed 24-hour engagement limit. Recorded that correction
in the [decision record](../research/oslit-harness-grilling-2026-11-13.md#14-november-clarification--runtimes-duration-and-architecture-guidance)
and revised the [plan](../research/oslit-engineering-plan-2026-11-14.md): Codex/OMP
supply native execution; OSLit adds missing engagement-wide coordination, evidence
and recovery. Provider credentials remain separate from runtime selection. Runs
can span days while authorized and resourced; operator deadlines are optional and
short worker leases preserve failure/revocation control.

Added a model-directed investigation example to section 7 and
[architecture AGENTS.md](../decisions/AGENTS.md) in the existing decision directory.
It captures founder intent, checks native features before adding mechanisms, and
asks founder questions only for unresolved material product choices. Updated root
mirrored pointers, architecture/decision indexes, current direction and the older
brief's planning pointer. Historical architectural and execution observations remain
dated; existing runtime gates and code are unchanged.

Read current source, official Codex app-server docs, OMP docs pinned to
`c308970263ae13744ea15ab67302e3dac840e266`, and local CLI help/version
(`codex-cli 0.166.0`, `omp/18.20.0`). These establish interfaces, not successful
integration. Independent runtime/design review passed after one stale status
pointer was corrected. Local link destinations, the full Q/E/M maps and mirrored
root instructions passed their checks.

The first structural run reported 900 checks with one stale draft instruction
pin caused by the new root pointer. Verified `execution_authorized: false` and
refreshed only that `AGENTS.md` hash using `tools/overlay_pins.py repin --apply`.
The draft remains unauthorized; no historical execution record was changed.
No provider run, target experiment or new-workflow E2E was performed.

Final checks: **900 structural checks, zero failures**, `git diff --check` clean,
208 local document destinations checked, complete unique Q/E/M maps, and exact
root instruction mirror. Results: `/tmp/oslit-engineering-plan/architecture-doc-checks.json`
and `/tmp/oslit-engineering-plan/architecture-conformance-final.log`.

## [2026-11-14] decision | Q30 and enforced native-tool coordination

Recorded the operator's approval of scored search as a technique within a task,
native-tool reuse with actual enforcement, a minimal extra interface and no code.
[Q30](../research/oslit-harness-grilling-2026-11-13.md#q30--scored-search-within-a-task-minimal-native-tool-integration)
retains the motivating paper, its evidence limits, the alternatives considered,
the chosen tradeoff and reasons to revisit it. The paper's sharing tools are
design input, not causal proof of a swarm benefit or OSLit qualification.

Updated the [plan](../research/oslit-engineering-plan-2026-11-14.md) with native
research/messaging/waiting tools and three illustrative controller operations:
status, claim and typed submit. Specified authenticated actor/role/assignment
checks, alternate spawn and retired-worker wake controls, durable relevant updates,
shared-target write leases, versioned instruments and local scorer provenance.
The shared board is a journal-derived view. Scores remain experimental feedback;
the lead's judgment and independent claim validation retain their roles.

Expanded the existing milestones and failure scenarios rather than adding a new
service or evaluator framework. The traceability map now covers Q1–Q30. Updated
architecture guidance and wiki navigation/direction, including the requirement to
preserve concise decision rationale. Independent reviews found two wording issues:
old internal call names looked like extra tools, and deferred shared evaluators
were not distinguished from permitted task-local instruments. Both were corrected.

This is a documentation revision. Current runtime code, authority gates, historical
records, study authorization and the operator-owned acceptance test are unchanged.

Validation: independent document review findings corrected; Q1–Q30 decision/map
coverage and E01–E16/M0–M6 identifiers complete and unique; local destinations and
Q30 anchors resolved; root mirror unchanged. Structural conformance passed
**900 checks, zero failures** and `git diff --check` passed. Results are in
`/tmp/oslit-engineering-plan/q30-doc-checks.json` and
`/tmp/oslit-engineering-plan/q30-conformance.log`. No live runtime behavior was tested.

### Full implementation assignment

The operator assigned the complete M0–M6 plan, native-tool reuse, enforced
boundaries and real-workflow verification, with autonomous execution. The
[delivery record](../research/oslit-implementation-2026-11-14.md) tracks that work.
The operator retains the fresh-target test and comparison. This assignment does
not change old engagement authority or supply research acceptance evidence.

## [2026-11-14] implementation | Candidate v2 delivery routing and evidence boundaries

Added the [dated v2 delivery state](oslit-v2-delivery-2026-11-14.md) and an explicit
root route to the [Codex/OMP operator guide](../agents/engagement.md). The guide now
covers private target-account references, frozen methodology/protocol export,
context reconstruction, pending owner stop and preserved historical records.
The October source-route status remains dated to its original revision.

The candidate is descended from `183199cc`; the linked source and saved receipts
retain their own checked revisions. The complete M0–M6 assignment remains open.
Actual Docker/SSH qualification, Linux model-host support, sustained multiday
operation, billed provider usage, hosted CI and research acceptance are not
inferred from local mechanics. Existing impact-artifact and escalation-review
gates remain active where the v2 mechanisms do not implement and verify them.

The conformance workflow adds seven portable provider-free v2 checks and retains
their JSON receipts by checked revision. Its Linux job is configured coverage,
not an observed hosted pass. Documentation checks cover local destinations, root
instruction equality and structural conformance; execution receipts remain
separate from this documentation update.

## 2026-11-14 — Current capture, recovery and hosted Docker evidence

Updated the v2 guide, delivery state and examples for reviewed escalation,
resource-selected capture, private target-account binding and eligible specialist
session retention through `9a26c93d`. Independent review and 900 structural checks
passed for that documentation checkpoint. The delivery state distinguishes those
changes from the actual environment proof below.

The [hosted Docker lifecycle](../../evals/native-qualification/team-evidence/real-docker-20261114/README.md)
passed 21 checks at `41a0be16`, including actual containment, artifact readback,
revocation and cleanup. The subsequent watcher-loss scenario at `fd8674b1`
reproduced a lease defect after a verified SIGKILL; the fixture cleaned all owned
resources. Both receipts bind exact source hashes and hosted run links. This is
actual Docker evidence on the disposable Ubuntu runner, separate from the seven
portable CI workflows and from the still unimplemented Linux model-host path.
The original M0–M6 scope and operator-owned fresh-target acceptance remain open.

## [2026-11-14] verify | Container-local lease fix

The actual hosted run at `3d0df8a2` passed the unchanged watcher-loss scenario
after the lease owner moved inside the container: 25 lifecycle checks and 30
guardian checks passed, with owned cleanup verified. The earlier failure at
`fd8674b1` remains preserved. The
[source-bound receipts](../../evals/native-qualification/team-evidence/real-docker-20261114/guardian-manifest.json)
establish actual container lifetime, child reaping and worker/control separation;
they do not qualify the joined native workflow, live providers or research.
The [delivery state](oslit-v2-delivery-2026-11-14.md) and
[implementation record](../research/oslit-implementation-2026-11-14.md) now state
that distinction. Documentation and evidence update only; no runtime rerun.

## [2026-11-14] verify | Actual loopback SSH environment

The hosted run at `1ec66d6d` passed 26 checks using real OpenSSH to the same
disposable host's Docker daemon. Killing the owned SSH client was followed by
a stopped container within 0.6111 seconds; all three environment cleanups passed,
and listener cleanup verified process and temporary-file removal. The
[SSH evidence](../../evals/native-qualification/team-evidence/real-docker-20261114/ssh-manifest.json)
preserves source hashes and the preceding fixture authentication failure.
This establishes transport composition, while separate remote-host/partition
behavior, joined native execution and research acceptance remain unverified.
The current implementation and delivery pages now distinguish these boundaries.
Documentation/evidence only; no additional runtime or conformance run.
