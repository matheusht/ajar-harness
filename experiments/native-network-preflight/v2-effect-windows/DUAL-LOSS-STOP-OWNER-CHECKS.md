# #161 owned exact-set stop owner — failure inventory before code

Decision: a run-scoped host stop owner must survive simultaneous launcher and
CONNECT SIGKILL, freeze the sealed Docker producer set, then publish run REVOKED.
This is a dummy-only owned component check; it grants no T02/native qualification,
provider contact, target access, or retirement of existing controls.

Raw evidence is the pinned #174 source, the prior owned dual-loss receiver receipt,
exact Docker inspect state, run marker bytes, and independent receiver rows. The
smallest serious alternative is to leave dual loss explicitly unsafe. Docker
`--rm` cannot help while the daemon-owned producer remains running. A separate
run-scoped host process is justified only if the checks below close that gap.

## Interface and invariants

- `v2_connect.py` prepares a sealed run, starts an independent exact-set owner,
  waits for its ready acknowledgement, then starts any producer. The owner holds
  only a read end of the CONNECT lifetime pipe; CONNECT exit/SIGKILL makes EOF.
- The owner also observes the original monotonic deadline and durable stop request.
  It receives the bounded manifest and state path, validates identity before
  acknowledgement, and acts on only those exact producer IDs.
- A private `stop.lock` serializes owner, CONNECT watcher, and launcher fallback.
  The existing `dispatch.lock` closes final sends at STOP_REQUEST/STOPPING. Producer
  start and READY publication share `stop.lock`. The held lock FD is inherited by
  the exact Docker start CLI so takeover waits for an in-flight CLI. A durable
  START_IN_FLIGHT marker remains if CLI completion is uncertain; takeover freezes
  the exact set but publishes UNSAFE, never REVOKED, in that case.
- If the inherited Docker CLI hangs after both Python processes die, its Python
  subprocess timeout dies too. Publish STOP_REQUEST before waiting for `stop.lock`.
  Bound that wait; on timeout, publish STOPPING and UNSAFE under `dispatch.lock`
  without claiming a freeze. Never leave a false REVOKED or an open dispatch gate.
  An unreleased CLI can still start a producer later, so cleanup must release it
  and remove only the nonce-owned exact resource.
- The stop winner writes STOPPING, freezes/rechecks the whole exact set, then writes
  REVOKED. Any Docker/identity/logging failure writes UNSAFE, never REVOKED. A
  second writer must preserve the first terminal outcome. Provider REVOKED is only
  provider admission state. Run markers and manifest stay outside producer mounts.
- Already-dispatched requests may settle later. The receipt separately counts an
  inert request held *before* dispatch and a fresh request after stop. Neither may
  reach the receiver after verified stop. There is no recall or blind retry claim.

## E2E checks, before implementation

1. Use one nonce-labelled, created/stopped pinned producer on an internal Docker
   network, a separate pinned receiver, a private host gate, and retained research
   bytes. Prove a positive receiver effect before any fault. Save exact host PIDs,
   owner PID, manifest digest, Docker IDs, hashes, marker contents and order.
2. Arm a pending direct effect. SIGSTOP launcher and CONNECT, then SIGKILL both.
   The independent owner must survive, observe lifetime EOF, durably write STOPPING,
   verify the whole producer set paused/exited, and only then write REVOKED. Before
   releasing the gate, inspect exact state. After release, pending and distinct
   fresh effect counts stay zero. Receiver and unrelated shared resources survive.
3. Repeat with only launcher killed and only CONNECT killed. Both incumbent stop
   paths remain safe; shared stop locking must prevent conflicting terminal state.
4. Inject partial startup loss and startup timeout. Before owner acknowledgement,
   no producer may run. If a completed first start is held before READY, takeover
   freezes the exact set. If the Docker start CLI is still in flight across both
   host kills, owner waits for it, freezes, and retains UNSAFE for uncertain daemon
   completion. Repeat without releasing the CLI until a bounded UNSAFE terminal
   appears: STOP_REQUEST must close dispatch, no REVOKED or READY may appear, and
   the owner must exit. A false REVOKED or runnable producer after a verified
   marker fails.
5. Inject pause and kill failure on an exact producer. Preserve provider closure,
   STOPPING and UNSAFE; require no run REVOKED and record actual runnable state.
6. Hold a CONNECT upload after charge/before send, stop, then release: upstream
   receives no new bytes. A request already sent before stop is classified as
   in flight, irrespective of when its response arrives.
7. Verify prior run markers/history remain, retained research hash is unchanged,
   and cleanup removes only nonce-owned exact resources and host processes. Save
   redacted command, source hashes, expected/actual results, and cleanup proof.
8. Managed stop proof must work whether the CONNECT watcher or independent owner
   wins the shared stop lock, including when watcher detection arrives after the
   freeze. Do not require provider `stop_detected` before producer freeze, and do
   not treat provider REVOKED as run proof. Accept only a valid run REVOKED proof
   tied to RUN.json's exact manifest digest and ordered producer IDs, with
   STOP_REQUEST <= STOPPING <= freeze <= REVOKED and exact Docker reinspection.
   A missing or tampered owner event cannot substitute for that proof. Missing
   or false run REVOKED, UNSAFE, wrong producer set/digest, or a runnable exact
   producer must fail. Provider admission closure remains a separate check.

The topology cannot promise zero effect from the instant of SIGKILL to the first
durable STOP_REQUEST or freeze: a runnable producer may act in that interval. The
test's staged gate makes the measured pending/fresh effects deterministic; report
the residual latency and do not state an instantaneous revocation guarantee.
