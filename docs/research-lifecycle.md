# Research lifecycle — attempts, bounded negatives, evidence bundles

This layer extends the Decision-0006 record kernel with the pre-action and post-oracle halves of an
attempt, a first-class bounded negative result, and content-addressed evidence bundles. It is
implemented in `tools/run-engagement.py`, schemas `schemas/research-lifecycle.schema.json` and
`schemas/negative-result.schema.json`, and the capability matrix `engine/operation-capabilities.json`.

It records what was tried and why a result is bounded. It does not grant authority, accept a claim,
or change a coverage/closure verdict.

All four commands below are **notebook** operations: broker role, local process-bound provenance,
signed scope, and no operator console. Attempts and bundles additionally require the active
environment reference. The actor and session are derived from the calling process
(`local-uid-<uid>:broker`, `session-posix-<uid>-<sid>`). A child process that owns a different POSIX
session cannot present them, so run the sequence in the process that owns the identifiers (as
`tools/run-work-queue.py` does for its broker actions) rather than recomputing them from a separate
shell.

## 1. Attempts have a start and a finish

### `attempt-start` — before any target contact

```sh
.venv/bin/python tools/run-engagement.py attempt-start \
  --engagement <engagement> \
  --attempt-id <attempt-id> \
  --environment-ref <active-environment-ref> \
  --surface "<what surface this attempt touches>" \
  --plan "<bounded plan for this attempt>" \
  --started-at 2026-10-23T12:00:00Z \
  --expected-evidence <ref> --stop-condition "<stop condition text>" \
  --actor-role broker --actor-id <local-broker> --session-id <session>
```

Required: `--engagement`, `--attempt-id`, `--environment-ref`, `--surface`, `--plan`,
`--started-at`, `--actor-role broker`, `--actor-id`, `--session-id`.
Optional: `--hypothesis-ref`, `--recorded-at` (defaults to `--started-at`), repeated
`--expected-evidence` and `--stop-condition`, `--rationale`.

The command appends one immutable event, `event-<attempt-id>-start`, of type `attempt.started` with
payload `{entity_id, status: "started", attempt}`. The embedded `attempt` object carries
`attempt_id`, `hypothesis_ref`, `environment_ref`, `surface`, `plan`, `started_at`,
`expected_evidence`, `stop_conditions` (the lifecycle `attempt_start` definition). It fails closed
when the environment is not the active one (`attempt_start_environment_not_active`), the hypothesis
does not exist (`attempt_start_hypothesis_missing`), the attempt was already finished
(`attempt_start_already_finished`) or already started (`attempt_start_already_recorded`), or
`recorded_at` precedes `started_at` (`attempt_start_time_order_invalid`). It emits the canonical
`start_ref`.

`attempt.started` (like `negative_result.recorded`) is admitted only through this command.
`append-event` rejects it with `canonical_notebook_command_required`, so a start cannot be forged
through the generic event path.

### `attempt-finish` — after the oracle

```sh
.venv/bin/python tools/run-engagement.py attempt-finish \
  --engagement <engagement> --file attempt-result.json --start-ref event-<attempt-id>-start
```

`--file` is the attempt-v2 record body (the same body the legacy `append-attempt` command accepts) plus
`cost_status`; it must carry `operation_class: "notebook"`, and its `actor` must match
`provenance.actor`. `provenance.actor` must be the local broker principal and `provenance.session_id`
the local session derived from the calling process; anything else fails with
`runtime_provenance_not_principal_bound`. `cost_status` is one of:

| value | meaning |
| --- | --- |
| `measured` | instrumented counters (tokens, model/tool/target/wall seconds, calls) |
| `estimated` | derived or apportioned from non-instrumented evidence |
| `unavailable` | no cost data exists for this attempt |

`cost_note` is an optional free-text qualifier. Cost status is descriptive; it is not a closure or
admission gate.

The command refuses the result unless the start exists and is an `attempt.started` event
(`attempt_start_missing`), the started `attempt_id`/`hypothesis_ref`/`environment_ref` equal the
result's (`attempt_start_binding_invalid`), the result does not precede the start
(`attempt_start_precedes_attempt`), the attempt is not already in the attempt ledger
(`attempt_already_finished`), and a `start_ref` written in the body agrees with `--start-ref`
(`attempt_start_ref_mismatch`). It stamps `start_ref` onto the attempt and returns it.

The reducer re-validates every present `start_ref` at reduction time
(`attempt_start_binding_invalid`). `start_ref` remains nullable in the attempt schema so historical
records still reduce. The public `append-attempt` command now requires a `start_ref` and a valid
`cost_status`; the internal `append_attempt` helper remains available for historical replay and
tests. An attempt result without a start is **not** a canonical loop result: the loop either starts
the attempt first or does not run it (see `engine/loop.md`).

## 2. `record-negative` — a bounded negative result

```sh
.venv/bin/python tools/run-engagement.py record-negative \
  --engagement <engagement> --file negative-result.json \
  --actor-role broker --actor-id <local-broker> --session-id <session>
```

The proposal is one `negative-result` record (`schemas/negative-result.schema.json`, derived from
the lifecycle `negative_result` definition). Every key is required; unused pointers are explicit
`null`:

```json
{
  "negative_result_id": "negative-...",
  "scope_hash": "sha256:...",
  "recorded_at": "2026-10-23T12:15:00Z",
  "status": "bounded",
  "goal_status": "open",
  "hypothesis_refs": ["hypothesis-..."],
  "attempt_refs": ["attempt-..."],
  "evidence_bundle_ref": "artifact-...",
  "coverage_ref": "event-coverage-lane-...",
  "provenance_ref": null,
  "reproducibility_ref": null,
  "limits": ["what this negative does not bound"],
  "residual_candidates": ["leads the negative does not dispose of"],
  "review_ref": null,
  "operator_signoff": null,
  "rationale": "why the bounded attempts justify a negative"
}
```

Checks performed by the command:

- schema validation, then a secret-shape scan of the canonical proposal bytes
  (`secret_shaped_negative_result`);
- `scope_hash` equals the active signed-scope hash (`negative_result_scope_mismatch`);
- `status` is exactly `bounded` (`negative_result_status_invalid`);
- `attempt_refs` is non-empty and every ref is a finished attempt in the attempt ledger
  (`negative_result_attempt_ref_invalid`); those attempts may predate start binding;
- every `hypothesis_refs` entry exists (`negative_result_hypothesis_ref_invalid`);
- `evidence_bundle_ref`, when set, is a registered artifact
  (`negative_result_evidence_bundle_invalid`);
- `coverage_ref` must name a `coverage.lane_recorded` event, `provenance_ref` a
  `provenance.recorded` event, `reproducibility_ref` a `reproducibility.recorded` event
  (`negative_result_lifecycle_ref_invalid`);
- `review_ref`, when set, resolves to a committed review record and its `record.committed` event
  (`negative_result_review_ref_invalid`);
- `operator_signoff`, when set, is normalized to an id and must equal the normalized `operator`
  named in `scope.md` (`negative_result_operator_signoff_mismatch`). It is an attestation field,
  not an authority grant.

Success appends `event-<negative_result_id>-recorded` of type `negative_result.recorded` with
payload `{entity_id, status: "bounded", negative_result}`, `entity_refs` covering the attempts,
hypotheses, bundle, lifecycle refs and review, and the bundle as an evidence ref.

The record is deliberately non-claiming:

- it creates **no** finding, no claim, no coverage verdict, and no artifact;
- `goal_status` is a declared disposition. `open` is the normal value for a bounded negative; the
  schema also admits `closed` and `not_applicable`, and none of them has any mechanical effect. A
  negative result never closes an objective or the engagement;
- the schema's other `status` values (`superseded`, `reopened`) exist for later records; this
  command admits only `bounded`.

## 3. `register-bundle` — an external evidence bundle, by manifest

```sh
.venv/bin/python tools/run-engagement.py register-bundle \
  --engagement <engagement> \
  --source-dir /absolute/path/to/external-evidence \
  --artifact-id <artifact-id> \
  --relative-path evidence/bundles/<artifact-id>.manifest.json \
  --created-at 2026-10-23T12:10:00Z --recorded-at 2026-10-23T12:10:00Z \
  --actor-role broker --actor-id <local-broker> --session-id <session>
```

The external source directory is resolved to a real directory. The command walks it recursively,
rejects any symlink entry inside it (`bundle_source_symlink`), scans every regular file with the
harness secret-shape patterns, and fails closed on a hit (`bundle_secret_content`, naming the
relative path and classes). An empty tree fails (`bundle_source_empty`).

It then writes one canonical-JSON manifest — the only bytes that enter the engagement — and
registers it through the ordinary `classify-artifact` / `register-artifact` clear-local path
(`application/json`, sensitivity `internal`, redaction `redacted`, acquisition `source_inspection`,
producer/session and active environment bound):

```json
{
  "schema_version": 1,
  "bundle_id": "<artifact-id>",
  "source_root": "/absolute/path/to/external-evidence",
  "created_at": "2026-10-23T12:10:00Z",
  "file_count": 3,
  "total_bytes": 4096,
  "files": [{"path": "run/log.txt", "sha256": "sha256:...", "size": 1024, "mode": 420}],
  "redaction_scan": {"files_scanned": 3, "secret_classes": []}
}
```

`--relative-path` must be engagement-contained and start with `evidence/`; an existing destination
fails (`artifact_bytes_precede_classification`). The result reports `artifact_id`, manifest
`sha256`, `file_count`, `total_bytes` and `relative_path`.

Limits: the manifest proves identity (path, digest, size, mode) at registration time. It does not
copy, retain, or later re-verify the external bytes — if the external directory moves or changes,
the digests no longer resolve. The secret scan is shape matching over the scanned bytes, not proof
that a bundle is secret-free, and the manifest is a clear-local artifact for that reason.

## 4. Companion lifecycle events

These three events are ordinary notebook events written with `append-event`
(`operation_class: "notebook"`, session provenance). The capability matrix admits `orchestrator`,
`reviewer` or `broker`, but `append-event` binds every notebook event to the local broker principal
it derives from the calling process (`local-uid-<uid>:broker`), so the writing session is that
broker session in practice. Their payloads are fixed by `schemas/engagement-event.schema.json`:

- `provenance.recorded` — payload `{entity_id, status: "recorded", provenance}`, where `provenance`
  requires `source_commit`, `source_manifest_sha256`, `live_build_id`, `binding`
  (`exact|normalized|different|unknown`), `normalizations[]`, `source_observed_at`,
  `live_observed_at`.
- `coverage.lane_recorded` — payload `{entity_id, status: "recorded", coverage}`, where `coverage`
  requires at least one lane `{name: source|local_js|native|live|edge, status:
  tested|blocked|not_applicable|not_started, evidence_refs[], blocked_reason}`.
- `reproducibility.recorded` — payload `{entity_id, status: "recorded", reproducibility}`, where
  `reproducibility` requires `command`, `seed`, `inputs[{path, sha256, retained}]`,
  `output_sha256`, `replayable`, `notes`.

A negative result cites whichever of these it used through `coverage_ref`, `provenance_ref` and
`reproducibility_ref`. These events are research-lifecycle annotations: they are not finding
claims, and `coverage.lane_recorded` does not fold into the engagement coverage/work-queue state
that gates terminal transitions.

## 5. What this does not change

This layer adds **no closure bypass**. Ordinary `close` and the operator override
(`engagement.ending_overridden`) still require the same operator authority plus the existing closure
gates — terminal coverage, cleanup, report acceptance, and memory disposition. The override only
records a deliberate ending with the exact blocking work left visible; it does not relax those
gates, and no computed blocking work is discarded. A `negative_result.recorded` event is a
notebook record that the reducer does not consult for coverage or work; a negative result can be
part of the evidence behind an operator's decision, but it can close the engagement record only
through those existing operator gates.

Likewise: no finding is created or filed, no claim state changes, no candidate is closed or reopened
by these records, and `register-bundle` grants no authority over the external bytes it describes.

## 6. End-to-end shape

```sh
attempt-start            -> event-<attempt-id>-start       (before target contact)
attempt-finish --start-ref event-<attempt-id>-start        (after the oracle; cost_status required)
register-bundle          -> evidence/bundles/...json       (source tree stays external)
record-negative          -> event-<negative-result>-recorded
```
