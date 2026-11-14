# M4 evidence and review control unit

This extends the [v2 contract](oslit-v2-contract-2026-11-14.md) in the same journal.
It implements controller ordering and provenance checks. The saved E2E results use
protected **engineering simulations**; they do not establish native capture,
process containment, provider execution, patch effectiveness or research acceptance.
Runtime/environment integration and M5 accounting remain separate work.

## Record ownership

`engagement_controller.py` remains the sole state owner. `engagement_evidence.py`
validates typed requests and reduces their existing journal events. There is no
second mutable evidence database. Frozen packets, executor observations, outputs,
source snapshots and runtime owner receipts are content-addressed objects. Replay
and export verify every referenced object. Each object is at most 4 MiB; frozen
configuration/schema/manifest contract files retain the parser's 16 MiB bound.
Oversize evidence fails before an event can reference an unreadable object.

Claims (`unconfirmed`, `supported`, `independently_confirmed`, `refuted`,
`needs_review`), task/search state, and cleanup (`pending`, `verified`, `unresolved`)
remain separate. A worker's success text, numeric score or zero exit status cannot
confirm a claim. Supersession retains prior bytes. Instrument/experiment/claim or
contrary-publication supersession invalidates dependent claim, patch and closure
review, including the fresh reviewer's check experiments; an unrelated
publication does not invalidate every conclusion.

## Worker requests

The existing authenticated `submit` path accepts these additional types. Each has
an exact payload shape in `engagement_evidence.validate_request`; unknown fields
are rejected. Actor and role still come from the private host endpoint.

| Request | Durable meaning |
| --- | --- |
| `instrument_register` | Immutable artifact, metric, reset procedure and conditions |
| `experiment_record` | Instrument, candidate, probe and conditions bound to protected execution/output observations |
| `experiment_compare` | Comparable input, metric/instrument, conditions, permissions and environment profile; no global score ranking |
| `claim_propose` | Explicit effect, causal control, optional independent replay, contrary publications and affected resources |
| `strategy_challenge` | Specific contradiction, repeated same experiment or strong-lead dismissal, with frozen evidence references |
| `review_request` | Lead-selected pending reviewer, immutable packet and affected resources |
| `review_result` | Assigned fresh reviewer, exact packet, checks, contrary evidence and independent execution references |
| `review_response` | Lead action tied to task/experiment/review, or substantive evidence-backed disputed rebuttal |
| `closure_request` | Goal-sensitive internal ending, named remaining work and bounded reason |
| `patch_propose` | Goal-authorized diff applied to verified original bytes, with frozen original/patched manifests and file objects |

A review worker must be pending with no prior session or review assignment when
its packet is frozen. Starting it uses a globally unused native session ID. Claim
acceptance requires a relevant control and a clean replay executed by that
reviewer in a different session and environment instance, together with explicit
measurement, permission, control, replay and completeness judgments. Host checks
establish provenance; the fresh reviewer still judges causal meaning.

Patch acceptance requires original/patched pairs for effect, causal control,
normal function and a relevant variant. Both arms use the same probe/candidate,
comparable conditions and separate clean environment instances. The fresh reviewer
executes the paired checks. Patch manifests come from protected host readback,
not a worker declaration. Patch freezing rejects unsafe/binary/symlink diffs and
limits the snapshot to 16 MiB total and 4 MiB per file. Larger sources are an
explicit unsupported snapshot case, not an accepted patch.

Strategy delivery must be observed while the lead dispatch is pending. A completed
settled decision counts once and only for obligations delivered to that dispatch.
Two unanswered opportunities require replacement. A substantive response does not
count as nonresponse; a rebuttal remains disputed and holds affected work for fresh
review. Revocation alone cannot permit replacement: exact runtime stop and
owned-environment readback are required, while unknown resource holds and unrelated
specialists remain. Broad goals cannot close at a first claim with unresolved work.
A rejected closure creates a reopen obligation. Finalization rechecks current work,
review, dispatch settlement, stopped workers and verified cleanup.

## Protected host APIs

None of the following APIs is available through worker `submit` or selected by a
model-supplied actor field. Each observes only an exact admitted grant. The runner
must call them from the relevant native/environment owner, not copy unverified
worker descriptions into them.

- `prepare_worker_dispatch(worker_id, generation, workspace, *, seconds, resources,
  adapter_id)` atomically binds preparation workspace and reservation. Identical
  retry returns the same grant. Preparing workers have no worker-request rights.
- `record_worker_started(..., owner_receipt=None)` and
  `record_worker_session(..., reason, owner_receipt=None)` freeze an optional
  `native-runtime-owner-v1` receipt. Session replacement requires settled work.
  The receipt pins the signed raw runtime-profile digest and observed process
  identity. An absent receipt cannot establish stop or replacement.
- `register_support_inputs(grant, inputs)` takes a host-only mapping of logical ID
  to `{path, manifest_sha256}` before environment preparation. It verifies and
  freezes manifest/file bytes. Environment support pins must match either the
  signed runtime bundle or this exact registered support set. Per-run public CA,
  controller bridge and methodology files grant no target permission.
- `record_environment_observation(grant, environment_profile_id, observation,
  output=None, *, effect_id, account_refs=())` freezes intent/results against
  signed input, effect, accounts, profile, instance and support identities. Late
  results can attach only to a recorded operation. Cleanup intents may act only
  on an already observed owned instance.
- `record_environment_output(grant, environment_profile_id, operation_id, output)`
  freezes safe bytes only when their digest matches that operation's result.
- `record_experiment_execution(grant, environment_profile_id, operation_id,
  measurement)` binds actual executor-observed `{instrument_id,
  instrument_sha256, candidate_sha256, probe_sha256, conditions, reset,
  clean_start}`. Generic shell output plus worker-declared hashes cannot provide
  this binding. The runner must independently capture the executed files and
  clean-start state; until that integration exists, experiments remain unsupported.
- `record_patch_execution(grant, environment_profile_id, operation_id, patch_id,
  arm, manifest)` binds protected actual-copy readback to the frozen `original`
  or `patched` manifest. A model-provided manifest is not valid host evidence.
- `record_obligation_delivery(obligation_id, worker_id, generation, *, dispatch_id)`
  records actual delivery before completion; `record_decision_checkpoint(grant)`
  records one settled decision opportunity.
- `revoke_worker(worker_id, generation, *, reason)` removes controller authority.
  `record_worker_stopped(grant, environment_profile_id, readback)` then requires
  `{environment, runtime}`. The environment has exact identity and status
  `stopped`/`absent`, with no unsettled creations. Runtime readback must identify
  the current session and `owner_receipt_sha256`, and assert observed
  `process_exited: true`, `child_absence: verified`, `capabilities_revoked: true`.
  One stopped environment cannot hide another still-running owned instance.
- `record_environment_cleanup(grant, environment_profile_id, readback)` requires
  exact identity, `status: clean`, and `owned_workspace: container_removed`.
  `replace_lead(worker_id, generation, *, profile_id=None)` requires the review
  obligation and verified stop. `finalize_closure(closure_id)` requires current
  reviewed closure, settled effects, stopped workers and verified cleanup.

Environment readback callbacks preserve `support_inputs`. Result-only
`read_workspace_manifest` and `read_artifact` callbacks use `path` plus
`manifest_sha256`/`files` or `output_sha256`/`bytes`; their actual values are returned
to the protected host caller, never inferred from a model's prose. These method
implementations are owned by the environment integration work.

## Repeatable verification and limits

Run from the repository with Python 3 and `ssh-keygen`:

```sh
python3 evals/native-qualification/smoke/check_engagement_evidence_e2e.py --output /tmp/m4-evidence.json
python3 evals/native-qualification/smoke/check_engagement_team_e2e.py --output /tmp/m4-team.json
python3 evals/native-qualification/smoke/check_engagement_journal_recovery_e2e.py --output /tmp/m4-journal.json
```

The first command records source digests, all scenario results and simulation
classification. The suite creates ephemeral signed fixture inputs, uses the real
controller request path, freezes outputs, exercises review/closeout, exports
results and removes temporary keys/workspaces. Initial missing-feature failures
and discovered-regression failures were saved before their corresponding fixes.
The two retained suites cover the six team scenarios and nine journal regressions.
No provider, real target, Docker daemon or remote host is contacted.

Continuous worker reservations, renewal versions, invocation admission within
long-lived workers, private source-instance resource concurrency, native delivery,
actual measurement/patch capture and restart after real host-process loss require
runner/M5 integration. These local passes do not complete those milestones or the
operator-owned fresh-target research test.
