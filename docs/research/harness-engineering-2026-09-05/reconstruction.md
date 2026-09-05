# The smallest trustworthy reconstruction view

Research for [issue 102](https://github.com/matheusht/redteam-harness/issues/102), 2026-09-05. Inspected checkout: `6a47b64264b6bf8f1edf8923847cfc9952cd1ab8`, branch `codex/research-harness-engineering-2026-09-05`. Production tracked files were initially clean; pre-existing `.scratch/` was left alone. This note is research, not an accepted implementation specification.

## Decision

The smallest compatible addition is one **read-only reconstruction summary**, produced on demand from existing records. It should combine the useful facts already available in reduced state with exact record pointers and a separately labelled external-outcome section. Task intent must remain a separate, attributed input. A missing current request must be shown as unknown, not inferred from pending work.

This would replace manually stitching together progress, review/report indexes, external-outcome tables and copied status summaries. It would not replace authoritative records or change session construction, filing, gates, dispatch, or closure. Existing files and exact lookup are adequate for the demonstrated reconstruction problem. No measured retrieval or storage limit justifies another backend here.

**Measured:** three changes to important synthetic input facts leave all six existing generated views unchanged. **Inference:** a more complete projection could reduce reconstruction work. Operator-time savings and a causal explanation of repeated supervision remain unmeasured.

## Where authority and information actually live

| Question | Current source and important distinction |
| --- | --- |
| Which evidence state is current? | The reducer reads event, attempt and artifact ledgers, resolves references, checks causality and committed files, then derives state. A stored snapshot is a projection, not independent authority. [Reducer input](../../../tools/engagement_state.py#L2486), [file commitments](../../../tools/engagement_state.py#L1731). |
| Which source was assessed? | Scope hash and active environment reference are exposed in progress. Source identity, Git commit and dirty-tree identity are in the referenced environment record. A finding revision is a revision of the claim, not a source-code revision. [Environment identity](../../../schemas/environment-preflight.schema.json#L57), [progress](../../../tools/engagement_views.py#L55). |
| Why did a claim change? | Current finding state retains revision, digest, adjudication review/event, change reason and revision event. Progress renders only ID, revision and status. [State](../../../tools/engagement_state.py#L3309), [projection](../../../tools/engagement_views.py#L51). |
| What was reviewed? | Review records contain type, subject, finding revision, inputs, input hash, rationale, conflicting evidence, verdict and independence declarations. Exact input digests are checked separately. A signature or declared fresh context is not proof of cognitive independence. [Review fields](../../../schemas/review.schema.json#L7), [input binding](../../../tools/engagement_state.py#L2423), [semantic checks](../../../tools/engagement_records.py#L331). |
| Which review revision belongs to a filed revision? | Claim adjudication can review predecessor revision 2 and support filing revision 3. State explicitly records `reviewed_revision` and `expected_filing_revision`. Operator report review instead concerns the report's revision. Do not impose one naive “every review revision equals latest finding revision” join. [Adjudication projection](../../../tools/engagement_state.py#L3251), [report binding](../../../tools/engagement_state.py#L2840), [operator review](../../../tools/reporting.py#L71). |
| What is the report's current status? | The immutable manifest is created with `operator_status=draft` and `historical_reason=null`. Accepted/submitted status and later supersession are derived from events. A superseded report becomes historical in reduced state; its manifest is not rewritten. Reading the manifest's birth status as current would be wrong. [Manifest creation](../../../tools/reporting.py#L35), [status events](../../../tools/engagement_state.py#L3315), [supersession](../../../tools/engagement_state.py#L3363). |
| What did an outside party decide? | `dispositions.jsonl` is a separate ledger. Its `report_id` means an **external** report identifier, not the internal manifest ID. `finding_ref` may be an ID or package path; no explicit finding-revision field binds the outcome. Source reference and confidence may be absent. [Schema](../../../schemas/disposition.schema.json#L7). |
| Is cleanup complete? | Structured cleanup retains obligation ID/status. Human `cleanup.md` has additional artifact, date and revert information and is expressly retained. Mechanical cleanup completion does not establish remediation or retest. [Reducer](../../../tools/engagement_state.py#L3209), [human template](../../../engagements/_TEMPLATE/cleanup.md), [projection boundary](../../../tools/engagement_views.py#L119). |

The renderer's review index discards subject, reason, review reference and obligation status, retaining only count and review type. Its report and submission indexes are bare IDs. Those are **present but poorly presented** facts, not missing evidence. [Current renderer](../../../tools/engagement_views.py#L92).

By contrast, an unrecorded user correction, missing external receipt, unknown outcome-to-revision mapping, absent independent assessment, or absent remediation evidence cannot be recovered by improving a summary. The inspected state model contains scope and recorded work, but no general current user-request/history contract. This does not prove no client retains such information; instruction loading and client-context capture are separate research lanes. [State fields](../../../tools/engagement_state.py#L2475).

## External outcomes need a separate, qualified join

The kernel's defined ledgers and final `source_hashes` cover events, attempts and artifacts; external dispositions have their own reader and interpretation. Changes to that file therefore need their own provenance in a composite view. [Ledger definitions](../../../tools/engagement_state.py#L42), [source hashes](../../../tools/engagement_state.py#L3374), [external reader](../../../tools/disposition_ledger.py#L82).

The existing reference index is a locator, not proof of record type, commitment or external authority. It indexes JSON identities by field names; an external disposition with `report_id` can receive the generic `report` identity. Retain path/schema namespace when resolving links. Never join external and internal reports solely because their field names match. [Identity selection](../../../tools/engagement_records.py#L521), [index entries](../../../tools/engagement_records.py#L649).

Draft review exposed a further boundary: base reduction builds that index over root JSONL and recursive JSON. Malformed or colliding external records inside that admitted source can already invalidate base admission. Gracefully showing a failed supplement beside valid state is therefore limited to separately supplied inputs outside that boundary. The inspector must preserve existing base failures rather than skip indexed records to manufacture a valid summary. It must also wait for final source-identity checks before emitting a valid result; missing coordination stays unavailable without creating a lock. [Base index construction](../../../tools/engagement_state.py#L2495), [admitted read](../../../tools/engagement_state.py#L1333).

The external reader skips inaccessible sources and malformed JSON rows; its human table omits provenance and confidence, while JSON output retains parsed fields and a file:line pointer. “No rows returned” must not be displayed as “no external outcome exists.” The new summary should distinguish absent, unreadable, invalid, unmapped and merely unverified data. [Reader](../../../tools/disposition_ledger.py#L82), [table](../../../tools/disposition_ledger.py#L199).

Preserve every relevant external row and its source, confidence, recording time and decision time. Do not invent latest-row supersession or current-revision attribution where no explicit binding establishes it. Keep technical validity, independent review, report acceptance, external disposition, duplicate relationship and remediation separate. The schema/help's general statement that duplicates prove validity is too strong to use as an inference rule for an unverified or ambiguously mapped row. [Outcome/provenance fields](../../../schemas/disposition.schema.json#L73), [novelty description](../../../schemas/disposition.schema.json#L133).

## Smallest compatible shape

The proposed read-only result needs four sections:

1. **Reading basis:** code revision, source locators/digests, last event and ledger identity, validation result, stale projections, unavailable inputs. Freshness means “matches these inspected sources,” not “all relevant facts are known.”
2. **Task context:** current request/correction reference and its version or digest, intended deliverable and limits, only when supplied by an attributable source. Label this separately from evidence and scope authority. Otherwise show `current task not supplied`; do not reconstruct it from a work queue.
3. **Evidence relationships:** each relevant claim's source identity and current record revision; change reason and event; typed review subject/input links; report revision/current status/supersession; recorded unresolved obligations with subjects and reasons. Group relationships instead of requiring the reader to join bare IDs mentally.
4. **Outside outcomes and remaining unknowns:** separate rows with provenance and explicit mapping confidence; human cleanup pointers; remediation/retest unknown unless a specific source supports them. No automatic status promotion or next-action dispatch.

Use the existing identity-bound read path and reference locators. A small deterministic formatter can consume admitted state plus a bounded read-only supplement. It should emit to the caller without publishing another mutable status file. Existing `render` and `reduce` CLI commands **write** projections; they are not substitutes for a read-only inspector. `check-resume` checks freshness but emits only event count and ledger hash. [Read boundary](../../../tools/engagement_state.py#L1333), [reduce writer](../../../tools/run-engagement.py#L1847), [render writer](../../../tools/run-engagement.py#L1965), [resume output](../../../tools/run-engagement.py#L2972).

A current-state inspector need not require already-generated files to be fresh before explaining their staleness. It must still require valid admitted authoritative inputs before calling the reconstructed kernel state valid. Preserve quarantine, root identity and existing-lock requirements. Do not create locks, rebuild views, repair records or fall back to unvalidated state to make the inspector succeed. Present an explicit unavailable/invalid result. The existing cooperative lock does not establish safety against every noncooperating writer. [Read admission](../../../tools/engagement_state.py#L1304), [public reduction](../../../tools/engagement_state.py#L3431), [resume verification](../../../tools/engagement_state.py#L3501).

## Benign measured probe and acceptance case

After reading the complete renderer, this research executed only its unchanged `_bullets` and `render_views` function definitions, extracted with Python AST. It supplied `Any` and the unchanged sentinel constant. No production module, kernel transition, gate, session, target, provider, report writer or view writer ran.

The handcrafted input describes document claim `DOC-1` at revision 3, an outstanding citation review, a historical revision-2 report, and a draft revision-3 report. It is a renderer input, **not a schema-validated or kernel-admitted engagement**. Each variant changes one presentation dimension while other input remains fixed.

| Input change | Result across the six generated views |
| --- | --- |
| Revision-3 report: draft → accepted | Byte-identical outputs |
| Outstanding review: different subject and reason | Byte-identical outputs |
| Finding: different change reason | Byte-identical outputs |
| Positive control: visible finding revision 3 → 4 | Output changes |

Renderer SHA-256: `70ba222a527c284a9dab9151fcb27f035f030a16c401939a0cada168de8bc729`.

Lasting evidence is retained under [checks/reconstruction/](checks/reconstruction/): the [baseline synthetic input](checks/reconstruction/snapshot.json), four named variant JSON files, six [baseline output files](checks/reconstruction/rendered/), and [original results](checks/reconstruction/results.json). All twelve files were copied byte-for-byte from the original temporary run. The variant files are `report_draft_vs_accepted.json`, `review_subject_and_reason.json`, `finding_change_reason.json`, and `visible_revision_positive_control.json`. The original results retain their original temporary directory as historical provenance; reproducing the check does not depend on that directory.

The [saved reproducer](checks/reconstruction_probe.py) is a newly reconstructed invocation, not a byte-identical copy of the original inline command. It reads the retained inputs, checks the renderer SHA-256 before executing its two AST-extracted functions, verifies the exact six-file output set and baseline bytes, and compares every output for every variant. It writes its outputs into a `TemporaryDirectory`, removed on exit, and imports no production modules. From the repository root:

```sh
python3 docs/research/harness-engineering-2026-09-05/checks/reconstruction_probe.py
```

The saved invocation was rerun successfully: all six baseline outputs matched the retained bytes; each of the first three variants left all six unchanged; the positive control changed only `progress.md`. A plain `rg -n` search in the original run found the omitted status, revision, reason and review-link fields in `snapshot.json`; the generated report index contained only two report IDs. This demonstrates information loss in these projections. It does not measure reviewer speed, prove a historical wrong decision, or identify the cause of repeated supervision. The reproducer is documentation evidence for this limited result, not a replacement renderer or a kernel admission test.

The future acceptance case should require an independent reader to recover these distinctions from one benign dossier:

- Source document revision and claim-record revision are named separately.
- Current claim is revision 3. A predecessor-revision adjudication is explained using its review type and filing relationship.
- Revision-2 report is historical. Revision-3 report's current acceptance comes from its event history, despite an immutable draft manifest.
- Review subject, reason, source reference and recorded independence status remain visible.
- A mock outside “duplicate” row with an external report number and no revision binding remains externally reported/unmapped. It does not prove revision 3 valid or remediated.
- An absent task request, missing receipt, unreadable source and stale generated view produce different descriptions.
- The read leaves all dossier bytes unchanged and creates no coordination or operational state.

These are proposed acceptance criteria, not results of an implemented replacement view or a blinded reader study.

## Deletion options and reversal conditions

Replace duplicate manual current-status summaries only after the reconstruction summary covers their necessary facts. Keep dated narrative containing unique intent or observations; link it and label its authority. Keep human cleanup content, immutable manifests/reviews, explicit external outcomes, and scrubbed knowledge. A projection can replace repeated transcription, not the original evidence. The current six generated files participate in resume validation; deleting them would require a separate compatible change, not ad hoc removal. [Renderer outputs/checks](../../../tools/engagement_views.py#L129), [resume contract](../../../tools/engagement_state.py#L3501).

Legacy package location versus revision-state authority remains the separate, held [issue 85](https://github.com/matheusht/redteam-harness/issues/85). This view must expose the distinction; it must not decide a new filing contract or treat location as a universal proof label.

Revisit this design if a blinded benign reconstruction comparison shows no reduction in errors or total preparation/review effort; if essential task context remains unavailable; if a proven concurrency/consistency requirement makes file-based reading more complex than a small transactional store; or if the summary conceals uncertainty or compromises independent review. Measure current files plus exact search against the proposed summary before adopting storage. No evidence here establishes that embeddings, a graph, a database, or a second context ledger would supply the missing facts.

## Exact reading and execution coverage

Full reads in this lane: research `SKILL.md`; root `AGENTS.md`; `docs/architecture.md`; `docs/decisions/README.md`; `tools/engagement_views.py` (169 lines); `tools/reporting.py` (95); `tools/disposition_ledger.py` (368); `schemas/disposition.schema.json` (144); `schemas/report-manifest.schema.json` (115); template progress, cleanup and memory/winners files; issue 102 and issue 85 bodies/status through read-only GitHub CLI.

Sampled source ranges: `engagement_records.py` 1–83, 328–342, 508–704; `engagement_state.py` 1–52, 1304–1444, 1731–1769, 2423–2454, 2475–2526, 2840–2907, 3140–3430, 3431–3529; `run-engagement.py` 1844–1865, 1885–2005, 2970–3005; `finding-v3.schema.json` 1–155; `review.schema.json` 1–155; `environment-preflight.schema.json` 1–127; Decision 0006 1–132; `record-review-atomicity-test.py` 220–315. Searches located other definitions/tests/schema fields but do not count as full reads. The remainder of these files and the full state-snapshot schema were not fully read. Referenced `docs/agents/domain.md` and `docs/agents/issue-tracker.md` are absent; instruction-loading analysis belongs to the parent research lane.

Only the described pure-renderer probe and its reconstructed saved invocation ran. The existing atomicity test was inspected, not executed. No production files, tracker state, engagement records or company documents were changed by this lane. The added script and synthetic fixtures belong to this research note. No performance, end-to-end recovery, independent-reader efficacy or operator-time claim is made.
