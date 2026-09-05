# Q02 input admission

[Q02](../tools/q02_compare.py) remains a limited prompt-ablation case-study tool. Its portable
checkpoint, threshold, decision branches and maximum conclusion license are unchanged. Version-1
admission distinguishes source inventory from adjudicated eligibility before applying that rule.
It does not recover the absent private preregistration, recompute historical outcomes or authorize
an engagement. [Specification #106](https://github.com/matheusht/redteam-harness/issues/106) and
[ticket #108](https://github.com/matheusht/redteam-harness/issues/108) define this repair.

## Measurement and worksheet

Use existing, coordinated offline sources with `arm-a/` and `arm-b/` directories. The root and
both arms must already have their record lock; measurement does not initialize authority state.
Keep measurement, worksheet and assessment files outside the source arms so they do not change
the committed source inventory.

```sh
python3 tools/q02_compare.py measure --engagement /absolute/offline-source \
  --case-id benign-case-1 --run-id paired-run-1 \
  --worksheet /absolute/review/worksheet.json > /absolute/review/measurements.json
python3 tools/q02_compare.py verdict --measurements /absolute/review/measurements.json \
  --worksheet /absolute/review/worksheet.json
```

`measure` emits `schema_version: 1`, case/run IDs and a `source` object containing the absolute
root, per-arm maps of relative file paths to lowercase SHA-256 digests, and `sha256`. The latter
hashes the root and arm maps as UTF-8 JSON with sorted keys, two-space indentation and a final
newline. The record lock itself is excluded. Each arm exposes `package_inventory`, candidates,
severity and existing cost proxies. Inventory includes packages represented by files; an empty
directory does not become a result.

The generated worksheet pins the exact emitted measurement bytes in `measurement_sha256` and
copies `source_sha256`, case and run IDs. Preserve the measurement bytes. Renaming its source
root, editing source files or reformatting the measurement requires a newly bound review.
Omitting `--case-id` or `--run-id` allows inventory inspection but leaves admission inconclusive.

Fill the worksheet's nonblank `adjudicator`; explicit boolean `blinding_held`; and explicit
boolean `run_record.ran_concurrently`, `cross_arm_read_occurred`, and `limit_truncated_an_arm`.
Sequential runs additionally name `sequence_order_if_sequential` as `arm_a_then_arm_b` or
`arm_b_then_arm_a`. These are attributable declarations, not independent proof of blinding.

## Eligibility and root-cause units

Set `eligibility_ref` to an object with `path` and `sha256`. Reference hashes always identify exact
file bytes. Absolute paths resolve directly; relative paths resolve from the worksheet's directory,
including references inside an assessment. The eligibility JSON contains:

- `schema_version: 1`, `case_id`, `run_id`, `adjudicator`, `measurement_sha256` and `source_sha256`,
  matching the worksheet and measurement.
- `compatibility`: `M1_unit: "legacy_packages"`, `M6_unit: "root_cause_groups"`, an explicit boolean
  `compatible`, and a nonblank `basis` explaining the adjudicator's frozen-rule compatibility
  assessment. A true flag and its basis are supplied evidence, not a machine reconstruction of
  the private preregistration.
- `packages`: exactly one assessment for every inventory item. Each contains `arm` (`arm_a` or
  `arm_b`), `package_id`, and boolean `eligible`. Eligible packages additionally carry a nonblank
  `root_cause_group`; excluded packages cannot carry a group. A shared group ID means the same
  defective decision/root cause under the original worksheet rule.

M1 counts eligible package IDs once **within each arm**. The same ID in both arms is valid. M6
counts sets of adjudicated groups: intersection for `both_arms`, and set differences for
`arm_a_only`/`arm_b_only`. Fill those nonnegative integer counts in `M6_overlap`; contradictions
with the mapping are errors. Three A packages and one B package can share one group: M1 is 3/1,
M6 is 1 shared and 0/0 unique. M1 is never collapsed into the group count.

The supported eligible layout is `findings/<package_id>/finding.json`, matching the existing
[finding schema](../schemas/finding.schema.json), with absent schema version or version 2,
matching finding/package ID, confirmed confidence, all three oracle flags true and non-withdrawn
status. A `revisions/` subtree is unsupported here. Notes-only, schema-incompatible and unreviewed
revisioned packages cannot silently enter M1. They may remain inventory when explicitly excluded.
This eligibility interpretation does not prove a finding, promote it or settle filing authority.

## Optional waste and cost

A null or absent `M7_waste.waste_class_a_avoided_that_b_hit` supplies no positive evidence. A present
assertion must be nonblank and requires `waste_ref` with the same path/hash shape. That JSON repeats
the eligibility binding fields, supplies an identical `assertion`, and a nonempty `source_refs`
array of resolvable path/hash objects. Missing evidence makes admission inconclusive; changed
bytes are an error. No circular worksheet/assessment hash is required.

Waste-round and M6 counts accept only nonnegative integers, never booleans or fractional values.
`M5_subagents` retains the existing prose-extracted proxy from `progress.md`; absence stays unknown.
It is neither token usage nor total labor. Optional missing cost/waste retains the frozen rule's
branch behavior: missing cost cannot prove the cost clause; absent waste cannot prove the waste
clause. A gap of one without cost evidence remains inconclusive.

## Outcomes and protections

Malformed JSON, duplicate keys/IDs, wrong types, blank identities/assertions, contradictory mappings
and byte mismatches exit 1 with a bounded input error and no verdict/license or traceback. Present
malformed dimensions are checked before returning an incomplete-input result.

Missing or unsupported integer versions, missing identities/integrity answers, unavailable required
references, unsupported eligible layouts and unestablished unit compatibility are inconclusive,
exit 0, with explicit blockers and the frozen inconclusive license. Old unbound measurements remain
inspectable but cannot receive a fresh decisive verdict. Explicit failed blinding, cross-arm reads
and truncation retain their original blockers.

Both public `verdict` and the `decide` helper use the same admission. Bare dictionaries supplied
to `decide` lack exact measurement bytes and cannot be decisive. Source identity, file bytes and
quarantine are rechecked immediately before output under the existing root/arm locks; assessment,
waste and input bytes are also rechecked. No rejecting context exit is added after publication.

[The public regression test](../tools/q02-admission-self-test.py) uses disposable benign files and
plain existing locks, never kernel initialization or target/provider calls. Run it with the
repository's pinned JSON-schema dependencies. `q02_compare.py --self-test` separately retains
private frozen-rule and checkpoint regression tests; that old self-test alone is not admission
acceptance. The historical research probes remain unchanged.
