# Read-only dossier inspector

`python3 tools/inspect-dossier.py --source /absolute/path/to/dossier` prints one JSON summary of
existing admitted records. Optional `--task-context /outside/task.json` and
`--outcomes /outside/outcomes.json` supply separately attributed context. There is no output-file,
repair, render, dispatch or admission-bypass option. See [ticket #110](https://github.com/matheusht/redteam-harness/issues/110)
and the [engineering evidence](wiki/engineering-evidence.md).

A successful invocation exits 0 with `valid: true` and `status: available`. That validates the
base record account under the existing reducer, not every supplied statement or the underlying
real-world claims. Failed source admission exits 1 with `valid: false`, `status: unavailable`
and a structured error; it emits no claims or partial valid summary. Invalid optional inputs can
appear beside valid base evidence. CLI usage errors retain argparse's normal exit behavior.

## Reading and authority

The inspector binds the named directory to its opened inode, acquires the existing record-kernel
lock without creating it, and calls the unchanged read-only reducer. It uses the existing reference
index and governed file reads. It snapshots regular-file bytes, constructs the result, rechecks
bytes/inventory and waits for the outer source context's final identity/quarantine checks before
returning anything to stdout. Missing scope/lock, quarantined evidence, malformed indexed records
and identity changes retain the existing rejection behavior. Separately supplied inputs must be
outside the admitted source and pass the existing safe-offline reader.

The top-level `inspector_sha256` hashes the inspector Python file itself. The `source` object names
the inspected dossier path and inode/device, scope and ledger hashes, and individual regular-file
digests in `file_digests`. The result also includes the last event, event-derived current state,
active source environment, and record pointers with types, paths, line numbers and digests.
JSONL record hashes and whole-file hashes remain distinct. It retains immutable claim revisions,
change reasons/events, typed review records, rationale and declared independence. Resolved review
inputs follow the reducer's time/revision selection. Predecessor adjudication can assess claim
revision 2 and support filing revision 3; report/operator review retains its typed report subject.

Reports expose immutable birth status alongside current reduced status, history and a superseding
revision event when historical. A manifest born `draft` can therefore be currently `accepted`.
Outstanding review obligations retain subject, opening event, reason and status. Human cleanup text,
report narrative and textual artifacts remain visible. None of these fields proves remediation,
retest, cognitive independence or a new filing rule. Package location remains distinct from reduced
record authority; the separate filing-lifecycle issue is unchanged.

`projections` compares stored snapshot/six generated views with bytes from the existing pure
projection functions. Each is `current`, `stale`, `absent` or `invalid`; none is regenerated. An invalid
snapshot is a failed projection, while malformed records indexed by base admission still reject the
source. The inspector does not filter those records out to manufacture an admitted result.

## Optional supplied inputs

Both inputs are UTF-8 JSON objects with `schema_version: 1`, nonblank `source_ref` and a timezone-bearing
ISO `recorded_at`. Duplicate keys, nonfinite numbers and malformed required fields are invalid.
The exact bytes are hashed; supplied data stays attributed rather than becoming record authority.

Task context may supply:

- `intent`: nonblank text or null; `configuration`: an object or null. Neither is inferred from scope,
  the work queue or the fact that this command ran.
- `loading`: `{ "status": "unknown", "source_ref": null }`, or `status: observed` with a nonblank
  source reference. An observed declaration is retained as supplied, not independently verified.
  Output loading also names its context source and context status.
- `based_on_ledger_hash`: null/absent means unknown freshness; the exact current SHA-256 means current;
  a different well-formed digest marks context stale. Its content is retained.
- `source_documents`: an optional array of `{ "artifact_ref": "...", "revision": "v2",
  "sha256": "sha256:...", "source_ref": "..." }` labels. A label needs the exact artifact ID and
  content digest to map; same spelling alone does not suffice. A mapped label from stale task context
  is marked stale. A supplied document label remains separate from a claim's numeric record revision.

Outcomes additionally require `rows`, an array of objects with nonblank `external_report_id`,
`decision` and `source_ref`. Optional `decision_at` and `recorded_at` are timezone-bearing ISO times
or null. Confidence and other supplied fields are preserved without an invented confidence scale.
Every row remains in input order, including repeated identifiers and apparently conflicting decisions.

An optional `revision_binding` object names `finding_id`, integer `revision` and `finding_digest`.
Only an exact internal revision/file-digest match maps a row; an exact old revision is stale relative
to the current claim. Missing, ambiguous or mismatched bindings remain unmapped. These labels describe
mapping, not verified external authority. External report identifiers never join internal reports by
spelling, and a duplicate/accepted decision never implies current validity, latest-row supersession,
novelty or remediation.

Input states distinguish absent argument/path, unreadable source, invalid supplied object, available
input and stale task context. External revision mapping separately distinguishes unmapped, mapped and
stale. No rows from an invalid outcomes object are interpreted. This graceful boundary is only for
separately supplied outside inputs; it does not exempt malformed/colliding JSON already in the base
index. This v1 command consumes the explicit supplement contract above, not an inferred conversion
of a legacy external-outcome file.

## Acceptance evidence

`python3 tools/dossier-inspector-test.py` constructs a disposable invented workshop dossier by writing
plain JSON/JSONL/Markdown files and a plain lock. It invokes no lifecycle/setup/publisher operation.
The fixture has source v1/v2, claim revisions 1–3, predecessor and operator reviews, an outstanding
citation review, historical/current reports and unique narrative. The public CLI passed **23 checks**
on 2026-09-08. The [wiki log](wiki/log.md) records the checked revision, integrated regressions and limits.

| #110 criterion | Output and executed control |
| --- | --- |
| 1. Admitted, ephemeral read | Real CLI uses existing bound reader/reducer; every invocation compares source bytes and file/directory inventory before/after. |
| 2. Reading basis, state and projections | Hash/identity/last-event assertions; stale, absent, invalid and current projection cases; invalid base yields unavailable. |
| 3. Document versus claim revisions | Source v2 label/content remains separate from claim r3; all three claim revisions and r3 change reason/event retained; mismatched/stale supplied labels tested. |
| 4. Typed reviews and predecessor relationships | r2 subject/input linked to adjudication supporting r3; raw rationale/independence retained; operator report subject and outstanding citation reason/status displayed. |
| 5. Current report status/supersession | r3 draft manifest with accepted event state; r2 historical reason and superseding revision event; report history retained. |
| 6. Supplied intent/config/loading | Absent context leaves loading unknown; supplied observed loading remains attributed; stale context retains explicit stale status. |
| 7. External rows and mappings | Repeated external IDs, confidence/times and same-spelled internal ID retained; exact current, exact old and mismatched revision bindings tested; claim state unchanged. |
| 8. Failure distinctions and narrative | Missing/nonfile/malformed/duplicate-key/nonfinite supplements; malformed indexed JSON and cross-type collision reject base; unique report/cleanup narrative retained. |
| 9. Public benign dossier and final rejection | All three research omissions asserted; missing lock creates nothing; quarantined source rejects; disposable final directory rename emits unavailable and no claims. |
| 10. No writes or compatibility change | Byte/inventory checks on each CLI call and input supplements; current views tested using existing pure bytes; no shared reducer/index/renderer or filing changes. |

The existing pure-render research probe still reproduces its three omissions with identical original
six-view bytes; it is historical compatibility evidence, not a new reader study. These tests establish
synthetic metadata behavior only. Supplied references, actual loading, author honesty, cognitive
independence, operator-time savings, complete activity capture and outcomes remain unverified. The
cooperative lock and byte recheck do not establish protection against every noncooperating writer.
The command keeps the bounded source in memory and includes its narrative; it adds no storage system,
background service, redaction inference or execution authority.
