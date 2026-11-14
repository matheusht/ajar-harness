# M0 failure-first E2E specification

Status: test inputs and required observations fixed before implementation, 14
November 2026. These are scenario specifications, not passes. They accompany
[the v2 contract](../../docs/research/oslit-v2-contract-2026-11-14.md). Parent owns implementation/integration; no target/provider run
or repository edit was performed here.

## Runner contract

```sh
python3 evals/native-qualification/smoke/check_engagement_team_e2e.py \
  --scenario E01 --output /private/checks/E01/result.json
```

Support `--scenario all` and per-ID execution. Each case uses an isolated temporary
root, ephemeral SSH signing key and allowed-signer file, harmless source/binary/
application fixtures and deterministic agent messages. Private keys never enter
the evidence bundle; retain only the public key/fingerprint and signed inputs.
The runner exits nonzero on failed assertions or unavailable required checks.
Save a result even on failure, distinguishing `passed`, `failed`, `unavailable`.

Exercise the same facade `inspect/run/status/direction/resume/stop/export` and
worker `status/claim/submit` entrypoints as users, in subprocesses. Keep simulated
runtime injection in the trusted test bootstrap/adapter factory, not a worker
payload or a product flag that grants authority. Every root/result/receipt created
through that adapter is permanently labeled `engineering_simulation`; it cannot
be promoted to real runtime evidence. Test-only fault hooks belong to the fixture
adapter and host harness. Production code need not grow fault flags or timers.

For worker tests, the harness creates isolated fixture worker identities through
the same host endpoint binding as runtime adapters. It can write their ordinary
workspace files and issue shell-compatible status/claim/submit calls. The JSON
request never sets actor/role/generation. A host-only helper supplies protected
runtime/environment receipts through `prepare_dispatch`, `adopt_receipt` and
`reconcile`, testing the same handlers actual adapters call.

Common artifact fields: `scenario`, `classification`, exact revision/source hashes,
commands and safe input manifests, Python/OS/runtime/adapter versions, required
services, expected and observed status, assertions, protected receipt/object hashes,
resource identities/readback, cleanup and explicit unverified capabilities. Capture
structured sanitized output only. Save fixture state and replay command sufficient
to rerun; never save credentials, raw conversations or private reasoning.

Each assertion below needs both a refusal/status and an independent effect check:
owned fixture marker count, unchanged journal hash/revision, exact actor/generation,
or protected executor/resource readback. A friendly error string alone is not proof.

## E01 — Authority, paths and request integrity

Base: valid source-only v2 engineering grant, bounded goal, no overall expiry,
one permitted runtime/profile and one lab; `inspect` succeeds without invoking the
adapter, creating a target resource or reading credential values. `run` freezes
the same bytes and starts exactly one admitted lead invocation.

Before any dispatch vary one input at a time: wrong key; wrong independently
trusted fingerprint; changed scope/goal/profile; expired/future issue time; two
scope blocks/mixed v1/v2; duplicate key; NaN/Infinity; unknown schema/extra field;
forbidden model/effect/account; path outside grant; root/input overlap; final or
ancestor symlink; symlink swapped while reading; missing source digest; malformed
request/oversize payload. Expect stable refusal, zero provider/target markers,
unchanged authority and no initialized usable root. Inspect may report an invalid
root, never run an effect to repair it.

After valid initialization mutate archived bytes and call resume/dispatch: refuse
with integrity failure and no new execution. An expired grant may still stop and
read back owned cleanup under retained cleanup authority. V1 fixture verification
and status keep their original accepted/rejected meanings; no v2 fallback.

## E04 — Ownership, roles and alternate calls

Lead creates tasks A/B with priorities and specialists W1/W2. Race both workers
claiming single A at the same revision. Exactly one accepted owner/generation;
loser gets revision/eligibility conflict and no resource grant. Duplicate identical
claim returns the same receipt and one event; same ID with changed bytes fails.
After refresh W2 can claim B. Priority and prerequisite ordering match the journal.

Attempt worker JSON `actor`, `role: lead`, copied assignment ID, sibling socket,
direct host CLI/root access, worker spawn/pool helper/direct provider path, forbidden
model and stale assignment generation. All refuse before spawn/spend/effect. A
specialist may publish a follow-up task but cannot assign, prioritize, create a
worker/reviewer, stop the engagement or widen scope. Test alternate native spawn
paths separately in actual-runtime checks; a simulated refusal is not that proof.

Reassign A while W1 has an outstanding invocation. New assignment is withheld
until old capability is revoked and effects settled/held. Late W1 output can be
retained as stale evidence but cannot mutate task/usage authority. A peer wake or
late message cannot revive its old endpoint or provider route.

## E05 — Session loss, updates and fresh review

Publish enough observations and contrary evidence to exceed one status page.
Read each page through the worker CLI, save its cursor, then crash the client
before and after acknowledgment. Drop, duplicate and reorder native notices.
Resume from the durable cursor: every relevant event remains reachable exactly
once by stable event identity, without repeating a mutation or silently losing
contrary evidence. Reject a cursor from another engagement or changed event.
Reading status alone must not advance the persisted acknowledgment.

Retain a specialist across two assignments, then remove its native session and
restart the controller. Reconstruct the question, published artifacts, scripts,
open effects and allowance from protected state; do not reexecute an uncertain
action to rebuild context. Change to another signed runtime/model assignment and
verify the same handoff with distinct native session identities and unchanged
usage. Missing session support is an explicit capability limit.

Create a reviewer in a fresh runtime context. Supply the exact packet and access
to all published knowledge, including material outside that packet, but no
researcher conversation or private runtime files. Use a harmless private-history
sentinel to verify isolation in the real adapter. A simulated fresh-session ID
checks controller ordering only. The controller owner covers cursor/reconstruction
cases; runtime owners cover real session retention, history isolation and native
notification delivery.

## E06 — Crash, receipt adoption and scoped uncertainty

Use a harmless execution that increments one owned marker once and returns a
protected receipt. Exercise controller/owner loss at: before committed intent;
after intent before owner acceptance; after owner acceptance before effect; after
effect before receipt; after receipt before controller adoption; after adoption
before client acknowledgment. Kill the owned process, then invoke public resume.

Expected: no committed intent means no effect; ambiguous owner acceptance remains
unknown until trustworthy readback; matching completed receipt is adopted once;
counter is never incremented twice; identical usage receipt charges once; changed
request/receipt identity/digest refuses. A fixture `never_started` readback may
release reservation, but absence of a receipt alone cannot.

Create dependent task D sharing uncertain lab A and independent task I on lab B.
A and D stay held; I still claims/runs. Lease expiry does not authorize repeated
execution. Where intermediate effects are uncaptured, hold the worker's complete
authorized resource set until readback narrows it. A task-result string cannot
clear the hold. Stop/export preserve the exact uncertain set and cleanup obligation.

## E08 — Strategy obligations and valid disagreement

Seed frozen observations for: repeated same experiment without a new discriminator;
material contradiction; strong-lead dismissal; proposed closure. Each creates a
specific obligation bound to that evidence/version. Different measurement/state
or a productive long experiment must not count as repetition just because elapsed
time, token count, low score or message count is large.

Deliver obligation at completed decision checkpoint 1. Lead can create reviewer,
link a new experiment, or submit substantive evidence-backed rebuttal. Those paths
do not count as ignored review. Fresh disagreement remains explicit and affected
direction stays held until review; unrelated tasks proceed. Undelivered notice,
crash, running long job and partial checkpoint never count as opportunity.

After two delivered completed checkpoints with no action/response, replacement
becomes eligible. A refusal to create a reviewer has the same observable nonresponse
record; it is not a fabricated negative research verdict. The replacement must
request pending review before affected work. Verify native direction delivery and
completed-checkpoint attribution separately with harmless actual runtime messages.

## E09 — Lead replacement must revoke capabilities

Start old lead plus unaffected specialist; old lead has child process/owned lab
operation. Create the E08 nonresponse record and request replacement. Observe
intent, old generation revocation, denied new dispatch/provider grants, actual
runtime/tool stop readback, affected unknown-resource holds, then new lead grant.
At no instant can two lead generations dispatch. Old delayed submits fail. Retain
goal, directions, specialist, queue/evidence/reviews, usage and cleanup obligations.

Make stop/readback fail or change host/resource identity. No replacement starts;
status reports the exact hold. Changing a queue field alone must fail this case.
Docker/process and authorized SSH child readback are actual integration cases;
simulated receipts prove only controller ordering. Do not stop unrelated processes.

## E10 — False success, scores and evidence versioning

Worker publishes convincing success text/high score without effect/control/replay.
Claim remains unconfirmed. Add effect observation alone: at most supported, never
independently confirmed. Add wrong-role, same-session reproduction, unrelated
control, changed instrument, omitted contrary evidence or worker-authored fake
receipt: review rejects or remains needs_review; no confirmation shortcut.

Construct complete harmless fixture evidence packet with exact actor permissions,
effect, causal control and independent clean replay receipts. Fresh reviewer can
inspect full published material and publish a bound disposition. Fixture outcome
is engineering evidence only; it is not a real security finding.

Publish a new claim, scorer, candidate or environment version after review. Earlier
bytes stay intact; affected review becomes stale and comparisons across metric/
reset versions are not merged. An unrelated publication must not invalidate all
reviews. Verify all referenced artifact digests again during export. Scores never
change engagement-wide priorities or acceptance rules by themselves.

## E11 — Goal-sensitive endings and prompt stop

Bounded goal plus current accepted review and settled effects can request closeout;
actual cleanup still required. Broad goal plus first supported claim with material
unresolved tasks cannot close as goal met. A reviewed bounded negative preserves
tested conditions and remaining unknowns, with no universal safety assertion.
Rejected closure delivers a concrete reopen obligation without deleting evidence.

Public stop, authority expiry and resource exhaustion promptly revoke new work,
settle/hold in-flight effects and retain incomplete result. They never wait for a
reviewer to permit stopping. Missing cleanup/readback yields incomplete/unresolved,
not verified. `status` and `export` cause no repair, invocation or target effect.

## E12 — Optional patch checks

Patch-required goal: freeze original bytes, proposed diff and patched bytes; run
the same effect, causal control, normal-function and relevant variant checks in
clean original/patched environments; fresh reviewer checks exact evidence. Reject
mismatched source/diff/result, changed probe between arms, symlink/path escape,
binary diff outside supported path, missing normal-function check and regression.
Publish rejected/partial patch evidence without replacing the original claim.

Goal without patch request closes under its normal review conditions; no fabricated
patch artifact or mandatory diff blocks it. Existing `native_patch_check` caller
checks remain valid under v1. Environment check receipts distinguish actual execution
from simulated result events.

## E13 — Shared reservations, receipts and long operation

Give total 100 worker-seconds with 60-second lease maximum. Concurrent 60-second
reservations cannot both dispatch. Settling a 60 reservation at observed 20 releases
40; a second invocation can then reserve within remaining ceiling. Unknown execution
keeps the conservative remainder reserved. Duplicate receipt does not charge twice;
late receipt settles the original reservation; altered receipt fails. Every setup,
lead, specialist, review and recovery invocation contributes once.

Restart controller, change permitted runtime/model, replace lead, resume native
session and retry delivery: totals/limits do not reset. Test boundary equality,
negative/Boolean/non-finite quantities, counter rollback, receipt > reservation,
missing required dimension and unsupported strict token/money/provider-request cap.
Overrun cannot be silently clamped; record fault/actual observation, stop affected
capacity, report unsupported enforcement. Informational missing cost stays unknown.

Use an injected clock only for policy cases: no-expiry authorized engagement older
than 24 hours can renew a short worker lease while resources remain; explicit expiry
revokes; disconnected worker lease expires before another effect. These are clock
checks, not multi-day proof. Actual harmless sustained soak must span multiple days,
include process/host restart and resource readback, and save elapsed wall-clock and
usage observations. Unfinished soak stays unfinished; it cannot block useful code
progress or be relabeled complete when a timestamp fixture passes.

## E14 — Trusted direction and untrusted content

Operator direction changes in-scope priorities and records exact sanitized content,
origin/time/affected work/acknowledgment; existing evidence survives. Worker/target
notes saying `operator says`, an injected command, forged role or copied direction
ID remain data and cannot create direction events or widen access. Out-of-scope
operator instruction requires newly signed authority and holds affected request;
unrelated authorized work may continue. Peer disagreement and corrected threat
model append evidence versions, not consensus/permission. Export labels human help.

## E15 — Persistence, redaction, corruption and export

Send sentinel auth header, auth cookie, JWT, password, provider token, signed URL,
private key and exact injected test credential through publication, direction,
runtime output, source metadata, filenames and nested JSON. Before durable write
reject or retain only explicitly sanitized structured observation. Search every
engagement file, temp file and result artifact for sentinels; no leak. A withheld
decisive observation leaves claim unresolved. Test scanner chunk boundaries too.

Publish instrument from mutable workspace, mutate original, then replay evidence:
accepted object bytes/digest stay unchanged. Symlink/ancestor escape, oversized
object, changes during host copy and worker-writable protected receipt all refuse.
No accepted claim points to a mutable path.

Corrupt/reorder/delete event, inject duplicate sequence/request, change object,
remove receipt, truncate partial write and provide stale snapshot. Replay rejects
committed corruption; a derived stale snapshot is discarded; uncommitted temporary
event does not become accepted. No history conversion or repaired invented event.

Export verifies reachable event/object/receipt closure and current claim/review/
cleanup identities. Missing or omitted evidence gives incomplete/error. Stale
cleanup receipt from another generation/daemon/host cannot prove absence. Export
is reproducible read-only work and its hash manifest covers every retained file.

## Related integration cases and verdict boundary

E02/E03/E07/E16 remain owned by runtime/environment integration: agent setup repair,
network redirect/direct socket enforcement, all access modes, shared write leases,
SSH loss and install/public workflow on both runtimes. Controller fixtures here
cannot make those cases pass. Each scenario records its proof tier separately:
provider-free simulated messages; actual local resource effects/readback; native
runtime/provider; remote host; hosted CI; operator research acceptance.

## Failure-first implementation order

1. Write the fixture inputs/assertions for E01, E04, E06, E13–E15 and run against
   current facade: record unsupported v2 behavior as the expected initial failure.
2. Implement contract/journal/facade; rerun those cases through subprocess commands.
3. Add concrete E08–E12 fixtures before their state transitions; run failing cases,
   implement and rerun. Preserve v1 reader checks throughout.
4. Runtime/environment owners run actual harmless integration checks and attach
   receipts. Missing access is unavailable. Full delivery remains open until the
   approved applicable checks, soak and integration evidence exist.
