# Owned dual-loss stop-owner result, 2026-10-21

This is a local, Docker-only component result. It exercises the exact sealed
producer set with inert effects and a separate receiver. It is not a provider
run, a target run, T02 qualification, or a complete native-readiness claim.
The machine-readable, redacted [receipt](OWNED-DUAL-LOSS-RECEIPT-2026-10-21.json)
records the commands, result hashes, source hashes, check counts, markers,
receiver cases, and cleanup state. Each local `/tmp/issue161-*/result.json`
contains the detailed checks and a frozen copy of the tested source.

Run each receipt command from the repository root with a **new, nonexistent**
`--output` path. Docker must be running, with the pinned OpenCode and PHP image
digests available locally; Python 3 and the Docker CLI must be on `PATH`.
The scripts create nonce-labelled private Docker resources and verify their
identity before removing them. A passing run exits zero and writes `result.json`
with every check passed, `cleanup_complete: true`, and
`source_pins_stable: true`. Injected startup and stop failures can print an
expected traceback while the E2E script still exits zero after verifying the
fail-closed outcome.

All 12 runs passed on the local macOS Docker host. Dual launcher and CONNECT
SIGKILL, and each single-loss control, wrote STOPPING then REVOKED only after
the entire sealed set was paused or exited. The independent receiver had one
positive effect before the fault and no staged pending or fresh effect after
the verified stop. A loss during completed partial startup also froze the set
before REVOKED. An in-flight Docker start with uncertain completion stayed
UNSAFE after freeze. In the separate inherited-CLI hang check, STOP_REQUEST
closed dispatch while the CLI held `stop.lock`; the owner published STOPPING
and UNSAFE after the bounded lock wait, with no freeze claim or REVOKED. On
release, that CLI started one producer, which remained runnable under UNSAFE
until owned cleanup. Injected stop-command failure left a runnable producer,
one fresh receiver effect, and UNSAFE; injected owner-log failure froze the set
but also stayed UNSAFE. The late CONNECT send check held an upload after charge
and before dispatch; stopping the run prevented those bytes from reaching the
upstream. Unsafe provider reopen was denied. All tracked Docker resources
were absent at cleanup; the dual-loss and partial-start checks also verified
the stop-owner and CONNECT host processes exited. The retained research hash
was unchanged.

The managed stop readback now uses a proof written by whichever stop path won.
The freeze timestamp comes from `producer_stop.py` immediately after its final
exact-set Docker reinspection, and run `REVOKED` carries that timestamp, the
manifest digest, and ordered IDs. The managed check compares those bytes with
`RUN.json`, the sealed manifest, and fresh Docker state. The owned dual-loss
run had no provider `producer_set_frozen` event but passed the run proof; the
single-parent-loss run had that event and passed too. False revocation, wrong
digest or IDs, bad marker order, an UNSAFE marker, missing run REVOKED, and a
runnable exact producer were rejected. Removing the owner event log did not
change a valid run proof. Provider admission closure remains a separate check:
the marker was absent in the killed-CONNECT controls and present in the
surviving-CONNECT parent-loss control. The no-Docker cloud source/pin checker
passed against the current manifest. The complete managed OpenCode rehearsal
was not run here because its pinned derived image is unavailable locally.

The dual-loss scenario stages the pending effect behind a private gate before
killing both host processes. There is still a real interval between SIGKILL
and the owner's durable stop request and freeze; already-dispatched effects
cannot be recalled, and an unstaged producer could act in that interval.
An inherited CLI that never releases cannot be frozen by this owner: it gets a
bounded, truthful UNSAFE marker, and it may start a producer later. This
35-second stop-lock bound may also classify a slow but healthy stop as UNSAFE.
That is conservative, but does not prove the producers stopped. This evidence
proves the tested gated boundary and fail-closed outcomes, not
instantaneous zero effect at host death or complete #161 stop assurance.
