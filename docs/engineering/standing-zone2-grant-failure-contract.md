# Standing local Zone-2 artifact grant: failure contract

Recorded before the implementation change on 2026-10-10. The acceptance
workflow is `.venv/bin/python tools/standing-zone2-grant-e2e.py --output
/private/tmp/standing-zone2-grant-e2e-<fresh-run>` from the repository root.
Use the harness virtualenv and `/usr/bin/ssh-keygen`. It creates only inert
synthetic files in a temporary directory and uses a fresh, ephemeral SSH key to
sign its synthetic scope. The public `run-engagement.py` CLI handles artifact
classification, creation, scope proposal and re-attestation, authority request
and resolution, and `check-resume`. Synthetic operator cleanup and
fresh-confirmation records may be seeded through the kernel's private append
function; that setup is **not** evidence that their public operator commands work.

| Failure mode | Required check |
| --- | --- |
| The standing grant is absent or its containment exceeds the local artifact ceiling. | Zone-2 classification fails before destination bytes exist. The old fresh-confirmation route remains usable with a separate exact confirmation. The existing signed-scope gate still applies. A signed scope confined to local `/tmp/` with prior cleanup, but without an `engagement/evidence/` grant, also fails classification. |
| A signed impact-authorized scope omits the four standing fields or explicitly chooses fresh per-act confirmation. | A filled authorization block derived from `engagements/_TEMPLATE/scope.md` without standing fields, and a scope with the complete explicit fresh tuple (`fresh`, `no`, `none`, `yes`), each accepts a public exact `confirm-zone2` event and then classifies, creates, and resumes one artifact. Neither grants autonomous standing creation. |
| A signed scope claims standing mode with an incomplete four-field tuple. | Classification fails closed before bytes or artifact rows exist. It cannot silently fall back to fresh mode. |
| Scope.md is edited after attestation, a stale permit is reused, or the environment changes. | `check-resume` may still accept the intact old attestation while the edit is a draft, but creation denies the drifted scope bytes before writing. A different active environment also denies classification. |
| A later `scope.attested` event repeats the same signed scope hash, so an older attestation ID is mistaken for the current grant. | After synthetic re-attestation and a new local preflight, metadata naming the old scope event cannot classify or create bytes. A permit issued before supersession also cannot create bytes; the artifact ledger stays empty. The fixture uses a private operator append for this same-hash event and does not prove public re-attestation authority. |
| Public re-attestation races a pending Zone-2 artifact creation. | Make a valid classified creation and approve the exact public `reattest-scope` action. Seed its exact pending journal both before and after the exclusive destination write to model the two crash windows. Public re-attestation must deny before changing `scope.md`, the snapshot, any event or artifact ledger, or the scope snapshots. The same journal and old permit must then let `create-artifact` finish, and `check-resume` must pass. A separate no-pending public re-attestation control must succeed. |
| A completed artifact record has a stale exact pending journal when cleanup later closes. | Recreate the original exact journal after a successful artifact commit, close its separate cleanup obligation, then retry `create-artifact` with the same metadata, permit, and bytes. It must return the existing record with `resumed: true`, remove the journal, preserve evidence bytes and the artifact ledger, and pass `check-resume`. |
| A crash leaves an exact pending Zone-2 journal before destination bytes exist, then scoped cleanup tries to settle the open obligation. | With no effect, public scoped `not_applicable` denies; with the fixed inert effect present, public `blocked` and `completed` deny. All denials identify exact `create-artifact` recovery and preserve the open obligation and scope bytes. Retrying creation with the original permit and bytes clears the journal, after which scoped settlement and `check-resume` succeed. |
| A cooperative cleanup or environment writer interleaves after artifact bytes but before artifact registration. | The exclusive file write and immutable artifact registration must share one engagement lock transaction, so another compliant writer cannot change the bound state between them. The exact journal-and-bytes crash-window E2E verifies recovery from an interrupted transaction; code inspection verifies the lock boundary because a deterministic CLI interleave would need a test-only hook. |
| A later valid scope re-attestation shares the exact timestamp of an earlier artifact's declared creation. | Create two standing artifacts, then append a publicly approved new scope attestation with `recorded_at` equal to the second artifact's `created_at`. Historical replay must bind both artifacts to the earlier scope by the classification event's ledger sequence and accept `check-resume`; equal timestamps do not retroactively bind them to the later scope. |
| A scoped cleanup closes after artifact registration with the same timestamp as the artifact's declared creation. | Publicly open the v2 scoped obligation, create two bound evidence artifacts, then create and remove the fixed inert effect. Record completion with `recorded_at` equal to the second artifact's `created_at`. Historical replay must keep the earlier open cleanup binding, preserve both immutable artifact records, and pass `check-resume`. A cleanup that closed before classification or strictly before the artifact's declared creation still blocks creation. |
| A decision-0006-v2 standing grant also names a signed scoped cleanup root. | Public broker `record-cleanup --scoped` opens an exact local obligation without an authority request. Two evidence artifacts bind that opening and remain immutable. Public `create-scoped-effect` writes only the fixed inert effect under the signed root; public scoped completion removes that effect and verifies absence. Evidence bytes and records remain present and `check-resume` passes. The v1 scoped-cleanup contract remains available. |
| A v2 scope has only the scoped cleanup grant, or the signed root/effect identity changes. | Public scoped cleanup refuses v2 without the complete standing `local_only_v1` tuple. A wrong or moved root, a different effect name or bytes, and any arbitrary transient effect fail closed without making a cleanup completion claim or changing evidence. |
| Planned hash or size differs from stdin bytes. | Creation rejects the bytes, leaves destination absent, and writes no artifact ledger row. |
| Cleanup obligation is missing, closed, or points to the wrong cleanup event or obligation ID. | Classification or creation denies before destination bytes exist; an open exact obligation is required. |
| Artifact metadata backdates creation before the referenced cleanup obligation opened or before the active environment preflight. | Keep the classification event after the prerequisite events so the ledger has valid monotonic time, but declare an earlier artifact `created_at`. Classification or creation must reject before writing destination bytes, the pending journal, or an artifact ledger row. The exact cleanup and environment preflight must precede the artifact's declared creation time. |
| Destination path is outside `evidence/`, contains traversal, or resolves through an alias. | Classification denies without writing outside the engagement. |
| Metadata or bytes contain a secret shape. | Classification or creation denies; neither the secret nor a destination artifact is persisted. |
| A malformed or non-local containment claim is accepted as a standing grant. | Classification denies a separately signed scope whose containment does not specify local `engagement/evidence/`. The positive case writes inert local files only; it supplies no target or network action. |
| A successful artifact is not bound to the signed scope, environment, planned bytes, cleanup and classification. | Creation commits one immutable record with those exact references; `check-resume` accepts the resulting ledger. |
| A standing grant silently collapses to a one-time confirmation after its first use. | Two distinct Zone-2 artifacts can be classified and created under the same signed `local_only_v1` scope, with no per-artifact operator signature after initialization. Both records bind the same prior open cleanup obligation and retain their own exact byte and classification digests. |

Acceptance requires all positive and negative cases to pass. A negative case
must inspect the destination and ledger, not just a nonzero CLI exit code. The
script saves `results.json` and `commands.jsonl` in the requested output
directory. `results.json` must report all cases and include each created
artifact's scope, environment, cleanup, byte, and classification binding. The
fresh-mode and negative fixtures sometimes seed operator cleanup through the
private kernel append path because the ordinary public `record-cleanup` command
requires an exact async authority request and operator resolution. The v2
scoped cleanup positive uses the public broker command. This is a local
synthetic check, not a live target or provider claim.
