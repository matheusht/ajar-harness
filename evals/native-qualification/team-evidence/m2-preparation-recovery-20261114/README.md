# Owned preparation recovery — 14 November 2026

The native boundary records a host-owned setup phase before constructing or preparing an environment and records native admission before constructing a proxy or native process. The existing journal owns both monotonic facts. Worker submissions cannot write them.

When setup fails or its controller is lost before native admission, recovery requires the current dispatch/generation/profile/assignment, no native owner/session/invocation, no target request or auxiliary dispatch, only setup/cleanup operations, and no environment shared with another dispatch. It obtains stopped and clean readbacks for every exact owned environment. A single settlement event stops the worker, records environment cleanup, charges setup seconds, refunds the unused invocation once and releases only this dispatch's holds. In-process accounting uses elapsed monotonic time. Process-loss recovery conservatively charges elapsed wall time since setup registration, capped at the reservation. Missing phase, native admission, changed identity or uncertain cleanup remain held. Existing history is preserved.

Failure-first checks were written and run before implementation. `before.json` records the original ten scenarios, including the missing recovery/phase failures and passing uncertainty controls. During source review, the added partial-identity scenario failed because cleanup can discover a previously unknown image identity; `identity-evolution-before.json` preserves that result. The final recovery check takes a fresh stop readback after cleanup and passes all eleven scenarios.

Repeat from the repository root with Python 3 and the signed fixture prerequisites:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_engagement_preparation_recovery_e2e.py --output /tmp/preparation-recovery.json
```

Expected: `status: passed`, all eleven scenarios pass. Successful setup recovery has zero native starts, zero charged invocations, no remaining reservation/hold, and exactly one setup-time charge; repeat recovery preserves usage. Uncertain controls retain their reservation and hold. The source digests bind results to the executed code.

Composed checks: public CLI 12/12, native boundary 23/23, retained specialist 26/26, source capture 6/6 and application capture 6/6. Run each corresponding script under `evals/native-qualification/smoke` with `--output /tmp/<name>.json` to repeat. `runner-fixture-mismatch.json` records an older runner fixture that publishes task completion but never completes its native invocation. The retained-specialist implementation now waits for that completion. Its test-only correction and fresh verification are tracked separately; this artifact does not relabel the failed run as passing.

These are engineering simulations of environment/native peers with the real controller, journal and runner. Some existing capture and boundary checks exercise owned local HTTP, processes and certificates. No Docker, SSH, provider inference, hosted CI, research acceptance or long-running qualification is proved. Process-loss recovery does not delete unrecorded local TLS/staging directories; the existing in-process finish removes its own directories. The cleanup verdict here concerns the exact recorded environment and native-admission boundary.
