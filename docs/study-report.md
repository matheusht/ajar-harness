# Offline study report (version 1)

`python3 tools/study-report.py --study definition.json --observations observations.json`
reads exactly the two supplied portable JSON files and prints deterministic JSON to stdout.
It writes no files, discovers no telemetry and runs no study. Valid incomplete or contaminated
observations exit 0 with qualifications. Malformed records, duplicate JSON keys, contradictory
identities and a mismatched definition digest exit 1 with `valid: false`, an error and no report.
The ordinary safe-offline reader rejects governed or quarantined evidence paths; export and
normalize an appropriate offline input through its existing authorized workflow first.

This implements [#109](https://github.com/matheusht/redteam-harness/issues/109). The
[synthetic command test](../tools/study-report-test.py) contains the complete executable example;
[engineering evidence](wiki/engineering-evidence.md) records the implementation and checks.

## Evidence boundary

The definition's SHA-256 binds the exact bytes supplied to the observations. It does not prove
when those bytes were frozen. `frozen_at` and `freeze_source_ref` are supplied provenance;
a missing freeze reference or an output dated before the freeze remains visible. Configuration,
loading, assessment independence and actual-work completeness are also attributed supplied
statements. `source_ref` strings identify the supplier's evidence; this command preserves them
without opening or independently verifying those references. An instruction hash does not prove
client receipt or comprehension. A reviewer name alone is not an eligible independent assessment.

The report counts outputs with an explicit eligible, independent assessment whose named assessor
differs from the producer. This is **supplied assessment eligibility**, separate from case terminal
state, configuration deviations and comparison contamination. A contaminated case can retain its
technical assessment count; the contamination flag still disqualifies an unqualified comparison.
The report computes no winner, efficacy claim, statistical comparison or Q02 threshold. It echoes
the frozen permitted conclusion as a declaration, with `comparison_conclusion: not_computed`.
Synthetic accounts establish accounting behavior only, never a measured experimental result.

## Definition

Every object has the exact fields below; unknown fields are errors. IDs are nonblank ASCII letters,
digits and `_.:-`, beginning with a letter or digit. All timestamps include a timezone. Repeats and
token counts are integers. Other measurements are finite nonnegative JSON numbers; booleans are
not numbers. All six metrics must be present; use null for unknown values.

| Field | Contract |
| --- | --- |
| `schema_version`, `study_id` | Version `1`; stable study identity. |
| `question`, `permitted_conclusion` | Explicit question and maximum intended claim. Neither is inferred from outcomes. |
| `frozen_at`, `freeze_source_ref` | Declared pre-output timestamp and provenance reference, or null reference when unavailable. |
| `missing_data_policy` | Frozen policy for missing, blocked and incomplete work; rows are always retained by the reporter. |
| `grading` | `{procedure, isolation, reference_ref}`: nonblank description and fixed reference identity. |
| `source_families` | Array of `{family_id, split}`; declare development/evaluation or other intended split explicitly. |
| `arms` | Array of `{arm_id, treatment, configuration}`; intended difference is explicit. |
| `assignments` | Array of `{assignment_id, case_id, arm_id, repeat, family_id}`. Each assignment ID and case/arm/repeat tuple is unique. A case keeps one family across arms/repeats. Referenced arms/families must exist. |
| `resource_ceilings` | All six metric values, covering the **whole study account**, including workers, coordination and overhead. Null means the ceiling is unknown. Development/maintenance remain separate. |
| `accounting_scopes` | Exactly `study`, `development`, `maintenance`, each `{description, allocation_rule, included_phases}`. Description fixes the actual work covered; allocation rule is frozen before outputs. |

The study scope explicitly includes `execution`, `preparation`, `useful_assistance`, `retry`,
`interruption`, `recovery`, `synthesis`, `grading`, `reporting`, `cleanup` and `accounting`.
Development and maintenance scopes each include their own named phase. This declares coverage;
it does not require inventing a receipt for a phase in which no work occurred. Normal reading,
analysis and production of the case output belong to `execution`. Useful successful human
assistance has its own phase and does not need a fictitious correction entry. The existing
correction ledger remains a ledger of corrections.

A configuration has `{runtime, model, model_revision, model_is_alias, instructions, source_ref}`.
The identity/source strings and the alias boolean may be null when unknown; unknown remains
qualified. Instructions are an explicit array of `{id, sha256}`, with unique IDs and `sha256:`
plus 64 lowercase hex digits. An empty array explicitly declares no instruction references.
The report compares declared and observed identity fields, not their differing provenance strings.
Floating aliases and missing identity/loading evidence remain qualified.

## Observations

The top-level fields are `{schema_version, study_id, study_sha256, data_kind, cases, receipts,
scope_completeness, allocations, unreconciled_imports}`. Version is `1`, identity must match the
definition and `study_sha256` must match its exact bytes. `data_kind` is `synthetic` or `measured`;
this is the supplier's classification. Empty arrays represent missing observations, not zero work.

Each case is `{assignment_id, recorded_at, status, producer_id, source_ref, configuration, loading,
deviations, contaminated, outputs}`:

- The assignment must exist, with at most one observation. All frozen assignments appear in the
  report; an absent observation gets `unobserved`, never an inferred failure or success.
- Status is `completed`, `failed`, `interrupted`, `blocked`, `incomplete` or `no_output`. Failed or
  interrupted work may still produce an output; `no_output` cannot contain one.
- `producer_id` can be null only when there are no outputs. Configuration is the observed object
  above or null. Loading is `{status: "observed" | "unknown", source_ref}`; observed loading requires
  a nonblank evidence reference. Unknown loading may have a null reference.
- `deviations` is an explicit array of nonblank descriptions; `contaminated` is a boolean. These
  qualify the comparison without erasing outcomes, measurements or supplied technical assessments.
- Each output is `{output_id, source_ref, produced_at, assessment}`. Output IDs are unique across
  cases. Produced time cannot postdate its containing observation. Assessment is null or
  `{assessment_id, assessor_id, eligible, independent, source_ref}` with unique assessment ID,
  nonblank provenance and explicit booleans. Contradictory self-assessment marked independent fails.

## Receipts, allocation and totals

The six independent dimensions are `human_active_seconds`, `elapsed_seconds`, `machine_seconds`,
`input_tokens`, `output_tokens` and `cost_usd`. Elapsed time is not human labor; machine time is
summed worker effort, not elapsed time. A receipt describes one actor's normalized activity; use
separate receipts for concurrent workers rather than putting aggregate worker-seconds into one
shorter interval. Decimal costs are summed through decimal representations to avoid binary-float
roundoff spuriously exceeding an equal decimal ceiling.

Each receipt is `{receipt_id, assignment_id, account, actor_id, role, phase, activity, source_ref,
interval, parent_receipt_id, metrics, not_applicable}`:

- Identity, actor, role, activity and measurement source are explicit. `assignment_id: null` means
  an explicitly study-wide/shared activity within the named account, not an unattributed import.
- `account` names one frozen scope; `phase` must be in that scope. Development and maintenance
  stay in their separate accounts with the frozen allocation rule visible beside each total.
- `interval` is null or `{start, end}`. Durations cannot exceed a supplied interval. An unknown
  interval leaves positive duration sums qualified unless an explicit allocation establishes
  nonoverlap. Use a separate elapsed-clock receipt when worker intervals overlap; do not sum
  concurrent worker durations and call that elapsed time.
- `parent_receipt_id` is null or an explicit existing parent in the same account and compatible
  assignment (a shared parent may have case-specific children). Missing/cyclic parents fail.
  Positive parent and descendant measurements are recognized as potentially nested for every metric.
- `metrics` contains all six values. Null is unknown, never zero. `not_applicable` is a map of
  metric names to explicit scoped reasons; each named metric must have a null value. Those entries
  are counted separately from both measured and unknown values. Explicit zero is a known zero.
- An identical repeated receipt ID is delivery duplication and adds no work. A conflicting copy
  fails. Distinct IDs remain distinct even if all other values match. No identity is inferred from
  timestamps, message text, model names or similar-looking costs.

Known same-actor human/machine interval overlap, any elapsed interval overlap and explicit nested
receipts qualify sums. The tool only compares pairs; it does not merge intervals or reconcile raw
telemetry. Accounting scopes remain separate; there is no cross-account combined total. If the
same work belongs partly to development and partly to the study, supply the allocation explicitly
rather than treating two scope totals as independent work.

An allocation is `{account, metric, rule, asserted_by, source_ref, nonoverlapping, values}`.
`rule` must match the frozen scope rule. `values` maps **every unique scoped receipt ID** to its
allocated value for that metric. Values cannot exceed known measurements or fill unknowns; null
stays null. An explicitly true `nonoverlapping` assertion with attributable provenance permits the
allocated sum, while retaining the known overlap pairs and source allocation for review. The tool
validates this declared partition; it does not prove the allocation's factual correctness.

Scope-completeness evidence is `{account, metric, complete, asserted_by, source_ref, basis}`.
There is at most one row per account/metric. A true assertion supplies the independent accounting
scope basis that **all actual work in that declared scope** was captured, including unsuccessful
and useful work, overhead and measurement itself. A roster or list of received receipts alone is
not this basis. False or absent evidence leaves scope completeness unestablished.

Every account/metric reports separately:

1. Recorded receipts, explicitly applicable/not-applicable counts, measured count and unknown count.
2. A measured subtotal, which may still contain overlap; limits and overlap receipt IDs remain visible.
   A conservative measured lower bound uses the largest individual value when overlap is unresolved.
3. Supplied scope-completeness evidence and any allocation, with their provenance and scope description.
4. A complete total only when scope completeness, measurement completeness and nonoverlap are all
   established and no relevant unreconciled import remains. Otherwise the total is null. An explicitly
   complete empty scope or entirely explicitly inapplicable inventory can establish zero; missing
   measurements cannot. Completeness is always limited to the supplied scope and assertions.

Assigned/observed case coverage, measured/recorded receipt coverage and actual-work scope coverage
are different denominators. All received costs known without a scope basis is incomplete. A complete
activity inventory with one unknown cost is incomplete for cost even when another metric is complete.
Budget adherence reports a known overrun if the nonoverlapping subtotal or conservative lower bound
exceeds the ceiling. It reports `within_declared_scope` only with a complete scoped total; an unknown
total cannot establish compliance. Matched ceilings are declarations, not observations of spend.

Unreconciled imports are `{import_id, account, source_ref, reason, metrics}`. An unknown account is
null. They are retained separately and never added to receipt totals. An import with an unknown
account qualifies all account totals; a named import qualifies that account. Reconcile outside this
command, then supply explicit normalized receipts and remove the superseded unresolved import.
The command never derives or silently repairs that mapping.

## Run the synthetic example

This writes only the explicitly named example files in `/tmp`; it performs no study:

```sh
python3 - <<'PY'
import hashlib, json, runpy
from pathlib import Path
study, observations = runpy.run_path("tools/study-report-test.py")["example"]()
directory = Path("/tmp/offline-study-example")
directory.mkdir(exist_ok=True)
source = directory / "definition.json"
source.write_text(json.dumps(study))
observations["study_sha256"] = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
(directory / "observations.json").write_text(json.dumps(observations))
PY
python3 tools/study-report.py --study /tmp/offline-study-example/definition.json \
  --observations /tmp/offline-study-example/observations.json
python3 tools/study-report-test.py
```

These fixtures supply artificial completeness/independence declarations to test mechanics.
They establish no provider receipt, model benefit, elapsed savings or production reliability.
