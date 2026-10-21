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

All 11 runs passed on the local macOS Docker host. Dual launcher and CONNECT
SIGKILL, and each single-loss control, wrote STOPPING then REVOKED only after
the entire sealed set was paused or exited. The independent receiver had one
positive effect before the fault and no staged pending or fresh effect after
the verified stop. A loss during completed partial startup also froze the set
before REVOKED. An in-flight Docker start with uncertain completion stayed
UNSAFE after freeze. Injected stop-command failure left a runnable producer,
one fresh receiver effect, and UNSAFE; injected owner-log failure froze the set
but also stayed UNSAFE. The late CONNECT send check held an upload after charge
and before dispatch; stopping the run prevented those bytes from reaching the
upstream. Unsafe provider reopen was denied. All tracked Docker resources
were absent at cleanup; the dual-loss and partial-start checks also verified
the stop-owner and CONNECT host processes exited. The retained research hash
was unchanged.

The dual-loss scenario stages the pending effect behind a private gate before
killing both host processes. There is still a real interval between SIGKILL
and the owner's durable stop request and freeze; already-dispatched effects
cannot be recalled, and an unstaged producer could act in that interval.
This evidence proves the tested gated boundary and fail-closed outcomes, not
instantaneous zero effect at the moment of host death.
