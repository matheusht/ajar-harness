# Communication comparison preparation v1

**Prepared document packet; agent experiment UNEXECUTED.** This implements
[#112](https://github.com/matheusht/redteam-harness/issues/112) preparation using the unchanged
[offline study-report contract](../../study-report.md). There is no board service or agent runner.
The prior [research](../../research/harness-engineering-2026-09-05/message-board.md) motivates the
comparison; it supplies no experiment result.

The [manifest](manifest.json) fixes source digests, case/arm order, role assignments, release points,
notice limits, grader bundles and exclusion rules. [Definition](definition.json) and
[observations](observations.json) are accepted by the same public command:

```sh
python3 tools/study-report.py --study docs/experiments/communication-v1/definition.json \
  --observations docs/experiments/communication-v1/observations.json
python3 tools/communication-packet-test.py
```

The admitted synthetic account supplies nine eligible artificial outputs, not nine candidate passes.
Loading, independence and completeness in that account are invented fixture assertions. The actual
`effective_configuration` and `run_authorization` in the manifest are absent. No real worker or
provider has received a bundle. The declared freeze time is an illustrative chronology; this
packet's commit fixes preparation bytes. A later run needs a witnessed pre-output manifest of the
protocol, source/reference files, installed model/revision, runtime, instructions, settings and
budget before any outputs. Never tune the key, assignments or budget after inspecting outcomes.

## Concrete cases and bundles

| Case | Source task | Initial sources | Late release |
| --- | --- | --- | --- |
| Complete | Kite-display announcement from a complete source set | [display](inputs/complete/display-v1.md), [notes](inputs/complete/display-notes-v1.md) | [bounded lunch observation](notices/complete-5.json) |
| Complementary | Combine attendee need with stock; calculate spare sheets | [attendance](inputs/complementary/attendance-v1.md), [stock](inputs/complementary/stock-v1.md) | [bounded restocking observation](notices/complementary-5.json) |
| Late | Revise booklet-binding details after a draft | [initial session](inputs/late/binding-v1.md), [materials](inputs/late/materials-v1.md) | [revision v2](releases/late/binding-v2.md), [correction notice](notices/late-5.json) |

All sources are invented harmless workshop text. Each case has its own evaluation source family;
none is development material or reusable answer memory. The common [worker brief](inputs/brief.md)
contains the task rules, with no answer key. Do not mount this entire packet in a worker session.
Manifest entries enumerate exact initial worker files and exact later releases. The final answer
examples in `finals/`, references in `grader/`, assignment mapping, observations and full manifest
are curator/reviewer material, outside worker inputs. Workers receive only their task instruction
and current-case released source files; no future correction or other-case source/answer is allowed.

All three arrangements have access to the complete released source set at the same event ordinal.
Every parallel role may inspect all those sources; initial assignment is a reading priority, not a
permission restriction. Request/read cost counts. Serial gets the full initial set immediately.
Direct and board use identical worker-a/worker-b priorities, coordinator access and directed update
opportunities. The only addition in board is the bounded feed; it cannot add primary sources or
extra workers. The serial worker, direct coordinator and board coordinator receive the same supplied observation
notice at ordinal 3 and the same external observation/correction at ordinal 5. These fixed examples
are common scheduled inputs; the board does not get a private extra hint. The direct coordinator
may immediately forward it and inspect all sources. No forced latency handicaps that baseline.

The concrete [complete](coordination/complete.json), [complementary](coordination/complementary.json)
and [late](coordination/late.json) handoff examples contain short independent first observations and
capable curated coordinator packets. They are synthetic coordination examples, not initial worker
inputs or observed agent commits. Both parallel arrangements must commit their own short independent
observations at ordinal 2 before receiving peer conclusions or curation at ordinal 3. A future pilot
must preserve the actual committed bytes/times; the test checks the prepared example and schedule
only. The serial worker also commits its initial note before the shared stage. No path withholds
needed evidence from the serial worker or suppresses ordinary coordinator follow-up.

## Schedule, notices and source authority

Run cases in order complete, complementary, late; serial, direct, board within each; one repeat.
Use a fresh case state. Event order is fixed: 1 sources; 2 independent first observations;
3 common observation, direct handoffs/curation and optional board discovery; 4 initial draft; 5 external observation or
correction to all arrangements; 6 primary-source check and revision coordination; 7 final;
8 anonymized grading. Event ordinals, not worker speed, determine release. Count preparation and
coordination of every scheduled input. Workers cannot inspect their final reference in advance.

Each case currently has two notices, at most **five short notices total per packet** in any future
pilot, including corrections and reposts. The combined observation/applicability/uncertainty text
is capped at 400 characters per notice. No eviction creates new slots; retain predecessors and
rejected notices. Reads, empty lookups and posting consume the same total budget as ordinary work.
No feed lookup or service is implemented here.

Every supplied notice names task, author, source version, observation, applicability, uncertainty,
release ordinal and primary source. The [old-time notice](notices/late-3.json) is correct for
binding-v1 but stale after release 5; [its correction](notices/late-5.json) names `late-n1` as
predecessor. Preserve both, and the source-check/correction timeline in the manifest. Repetition
or acknowledgment never overrides a primary source or establishes comprehension.

Record these separately, with attributed evidence and unknowns retained:

- **Retained:** exact notice/version exists in the task artifacts; that says nothing about delivery.
- **Delivered/read opportunity:** exact notice is in the received packet or retrieval response;
  it does not prove attention, understanding or correct use.
- **Used:** a subsequent source check or final change cites the notice and primary source.
  A copied citation without a source check is a provenance gap.
- **Correct:** independent reference assessment validates the affected claim at the applicable
  revision/time. The old-time notice is stale at final grading even though initially source-correct.
- **Useful:** paired evidence attributes a better output or equivalent-quality effort reduction
  to the validated notice. This remains unknown in every supplied notice account.

The manifest's delivery assertions are illustrative schedule accounts, not actual model receipts.
A withheld-notice comparison would be a separately budgeted new run, not proof of internal reasoning.
Necessary independent source checking is never labeled waste merely because it repeats a read.

## Fixed grading and access checks

Fix the references first: [complete](grader/complete.md), [complementary](grader/complementary.md),
[late](grader/late.md). The curator alone holds the mapping from assignment to neutral output name.
For each case, the grader receives exactly `reference.md` plus three designated final outputs named
`output-a.md`, `output-b.md`, `output-c.md`. It receives no arm labels, manifest, peer discussion,
self-assessments, instructions from workers, or other-case answers. Never grade initial drafts as
finals. References specify revision/citation correctness, completeness and unsupported claims.
An eligible technical output and an uncontaminated comparison are separate assessments.

The packet test materializes these exact worker/release/grader file bundles under TemporaryDirectory,
compares bytes and inventories with the manifest, and rejects source/grader crossover, other-case
files, altered release points, or drift between direct and board assignments. It checks notice
fields/limits and committed initial observations preceding curation. Negative controls demonstrate
that a leaked reference, cross-case answer and early correction fail those checks. This is executed
artifact assembly/validation, not a working access-control system or proof of future cognitive
isolation. A later run must enforce a real per-role/per-stage readable-file boundary and capture
received inputs; declarations or file hashes alone do not establish that enforcement.

## Total budgets and illustrative account

The definition fixes the synthetic configuration `synthetic-account-fixture-v1`, no model invoked,
revision `fixture-v1`, no alias, and the worker-brief hash identically for all arms. This is an
accounting fixture identity, not an installed runtime. This version permits zero model tokens and
zero total attributable dollars. A real agent pilot is blocked pending a NEW preregistration with
one exact effective model/runtime/settings configuration shared by every worker/coordinator,
explicit authorization and a reviewed nonzero resource allocation. This packet authorizes none.

Whole nine-assignment ceiling: 3,600 human-active seconds, 7,200 elapsed seconds, 14,400 summed
machine seconds, zero input/output model tokens and $0 attributable cost. Each arm gets exactly one
third, inclusive of all workers, coordinator, communication, human repair and shared overhead.
Reserve half each arm's allowance for preparation, curation, grading, repair and accounting; no
extra per-worker allowance or transfers from an unused arm. Token totals include all workers and
coordination. Count infrastructure cost; unknown cost does not prove compliance with zero dollars.
Elapsed time is a shared clock; summed worker effort is a separate metric.

Receipts in observations.json model one actor/activity per row in nonoverlapping fictional intervals:
complete-source execution, both independent workers, coordinator curation, posting, board reads,
failed lookup, repeated analysis, human repair, preparation, grading, reporting, cleanup and accounting.
The illustration deliberately serializes its receipts for simple arithmetic; it makes no parallel
latency claim. No interval aggregates concurrent workers. Direct attribution belongs to the named
assignment; study-wide overhead remains shared, with equal arm allocation only for a separately
labeled secondary comparison. Never count the same work in study and development/maintenance.
Actual overlaps require sourced partitions. Human helpful work is counted even when no repair occurs.

This is a closed-world synthetic activity inventory with invented completeness and independent
assessment declarations. It includes all fictional work, including failed and overhead activities;
it does not describe actual authoring effort or a real run. Development and maintenance contain no
fictional work, so the supplied empty-scope declarations illustrate zero only within that fixture.
Future preparation/compatibility costs belong in separate development/maintenance accounts, allocated
once by direct attribution or equal shared allocation; freeze their owners, window and ceilings
before authorization. They cannot disappear into an efficacy claim.

The public reporter retains all nine assignments and nine supplied eligible artificial outputs.
The test also supplies missing, failed, unknown-loading/usage and contaminated variations. Cross-case
answers, extra source access and extra effective budget invalidate comparison while retaining those
rows and any technical eligibility. The reporter does not enforce bundle isolation or discover
these events: attributable deviations/contamination must be supplied, while the packet checks verify
prepared-file constraints separately. Ceilings are declarations, never observations of adherence.

## Readiness, rejection and conclusion gate

Before any actual run, require explicit authorization, exact effective model/runtime/settings and
loading evidence, source/reference freeze, matched assignment/budget manifest, per-role/per-stage
access enforcement and received-input evidence, grader isolation, all labor/tool/communication
measurement sources, and named cleanup/development/maintenance owners. Reject or stop the pair for
reference/other-case leakage, extra source access, missed or unequal correction release, shared
conclusions before independent commits, extra effective budget, missing configuration/authorization,
unknown budget adherence, altered reference, or unexpected sensitive/real data. Retain affected
assignments and spent work; no silent dropping or beneficial rerun. No network/provider/paid/live
operation is authorized by this preparation task.

A mechanism pilot may advance only if a validated notice explains an improvement over capable
direct handoff within the same total budget, without a new correctness, provenance or isolation
failure. Equal complete results at equal or lower effort favor the simpler baseline. A later
adoption study must fix a practical-benefit threshold and repeated paired design BEFORE outcomes.
Three examples, fabricated trace accounts or a busy feed cannot justify adoption. This packet
establishes no model result or communication benefit; the experiment remains **UNEXECUTED**.
