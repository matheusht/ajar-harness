# Public v2 workflow wiring — 14 November 2026

The public `native_engagement.py` v2 facade now routes `inspect` through composed
preflight and `run`/`resume` through the real Runner and NativeBoundary. `stop`
first records durable revocation, then attempts recovery under the runner's sole
owner lock. If another owner holds that lock, the command reports `stopping` with
`runner_stop_pending`; the current owner remains responsible for shutdown. Status
and cleanup remain distinct, and unresolved effects keep their reservations.

Preflight checks both bundled method and protocol files and reports their digests.
For signed applications it reads `OSLIT_ACCOUNT_BINDINGS`, validates private
reference configuration, verifies referenced host environment values are present,
and immediately releases those values. References overlapping any supplied input
or runtime bundle are rejected. This does not contact a target or establish which
user a target recognizes. Native-boundary startup additionally protects controller
and worker paths, which do not yet exist during input preflight.

The new public CLI scenario starts actual Python subprocesses, creates real signed
fixture inputs, and uses the actual journal, runner, default boundary and lock. Its
configured native/environment executables are sentinels that must never execute:
the deliberately invalid bundle fails before startup. It verifies that run enters
real dispatch bookkeeping, resume does not repeat unresolved work, and stop does
not invent cleanup. A separate process holds the real runner lock for contention
checks. It also checks preserved v1 status routing and rejects a simulation switch.
No injected boundary is available through the public CLI.

Repeat from this checkout with Python 3.11+ and `ssh-keygen`:

```sh
python3 evals/native-qualification/smoke/check_engagement_public_cli_e2e.py --output /tmp/public-cli.json
python3 evals/native-qualification/smoke/check_engagement_preflight_e2e.py --output /tmp/preflight.json
python3 evals/native-qualification/smoke/check_engagement_runner_recovery_e2e.py --output /tmp/recovery.json
python3 evals/native-qualification/smoke/check_scope_only_phase_driver_e2e.py --output /tmp/v1.json
python3 evals/native-qualification/smoke/check_engagement_guidance_e2e.py --output /tmp/guidance.json
python3 evals/native-qualification/smoke/check_engagement_team_e2e.py --output /tmp/team.json
```

Expected and saved results: seven public CLI checks; 28 composed preflight checks;
three recovery groups; 18 legacy phase cases; five guidance cases; six team cases.
The preflight suite supplies private fake references and an owned Unix listener,
proves no native executable/daemon/network dispatch, and simulates the unsupported
Linux host branch. Red results precede the public wiring, guidance/account checks,
and reference-plane guard. The pre-existing recovery scenario now checks durable
stop separately from pending owner cleanup, then verifies the owned specialist's
stop receipt. Its manually created lead has no owner receipt, so global cleanup
correctly remains unverified. The recovery, team and legacy phase cases use their
explicit simulated boundaries; they do not establish native containment.

Complete native execution with Docker/SSH, real provider behavior, target identity,
and research qualification remain unverified by this unit. The deliberately
unavailable public fixture is a fail-safe execution check, not a delivered research
result or clean environment claim.
