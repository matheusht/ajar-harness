# Native setup host builder: failure-first scenario

This is the #202 offline host-builder slice after #208 has frozen a setup
proposal and stopped its run. A checked build is a runtime preparation result,
not a security finding or permission for research. The signed setup-only scope
does not authorize target build by itself. A second, signed offline-build scope
amendment and a separate signed build approval bind the exact build effect.

## Failure matrix written before implementation

| Condition | Expected check before an effect or final result |
| --- | --- |
| Missing, unsigned, expired, mismatched scope amendment or approval | Reject before Docker; the original setup scope and both new signatures must match the independently pinned operator key. |
| Changed original target, setup receipt, recipe, or threat model | Reject before Docker; use the #208 frozen source and output hashes. |
| Target network or broader effect requested | Reject before Docker; only `network=none` offline build of the owned disposable copy is admitted. |
| Image or catalog changed, missing or symlinked dependency | Reject before Docker; image ID and full catalog tree must match the signed pins, and every proposed dependency must be supplied. |
| Docker reports a different bind source or exposes bytes unlike the signed source/catalog | Reject before recipe execution; read back both mounted trees inside the container and compare their hashes. |
| Active provider tunnel or inconsistent per-tunnel bytes in a stopped v1 setup | Reject a new build effect even when the last turn's aggregate receipt matches. |
| Source, executable dependency, or output mode changes | Sign the source mode map before build, retain approved dependency modes and the output executable bit, and reject later drift. |
| Docker daemon changes or container boundary differs | Pin the daemon identity, inspect the full network, resource, mount, user and healthcheck envelope before start, and refuse effects or cleanup on another daemon. |
| Secret-like output | Reject the result, retain only hashes and a redaction flag; never save raw command output. |
| Workspace, output, process, time or memory limit exceeded | Stop, remove the exact owned container, and report the bounded failure. |
| Host crashes after a create, start, exec or output-read dispatch | Durable pending action remains `unknown_effect`; a second build call must not repeat it. Reconciliation checks and removes the exact owned container, retains the uncertain action, and charges the full approved build duration as an upper bound. A fresh signed approval must bind all prior attempt receipts and cumulative charged time before another build. |
| Incomplete container cleanup or changed source after execution | Never emit `ready`; retain the journal, run root, and exact cleanup failure. |
| Successful commands but missing selected output | Report blocked with the missing path; never mark a security result. |
| Host dies after the complete checked package is renamed but before the journal says `ready` | Keep the build single-use. Reconcile only after checking the exact package, signed authority, stopped setup and resource receipts, acknowledged action journal, pinned Docker daemon and absent owned container. Mark that journal `ready` without a second build. Changed bytes or unavailable readback remain held. |

## Public end-to-end scenario

Run `PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_native_setup_builder_e2e.py --output /tmp/native-setup-builder-e2e.json` with a working local Docker daemon, an already-local `busybox:1.37` image, `ssh-keygen`, OpenSSL and Go. The scenario creates a fresh harmless multi-file source, compiles the local relay source, prepares synthetic signed setup authority, and fabricates stopped v1 and v2 setup receipts. It signs the separate offline-build amendment and approval, invokes the public `setup-build` CLI against real local Docker, and saves input pins, output hashes, journal and cleanup observations. It exercises missing stop proof and dependency, changed approval and source modes, active/inconsistent provider ledgers, executable mode preservation and drift, in-container source/dependency readback, pre-start boundary verification, wrong-daemon cleanup refusal, exact cleanup of a real synthetic crash container, no automatic retry, and a new signed retry that carries prior charged time. It injects a process exit immediately after the checked-package rename, then tests fail-closed adoption and readback without a second build. It labels fabricated setup-turn, stop, and host-crash records. It does not call a provider or target service, kill a real builder process, or qualify a real model turn. Other matrix rows are implementation boundaries, not observed scenario passes.

Pass `--keep-root /absolute/new/private/dir` to retain the synthetic checked
v1 `run/` and v2 `linked-run/` for a downstream local transition scenario. The
fixture's signing private key is removed before the scenario returns. The JSON
receipt gives both run-root paths. Do not treat these fabricated setup records
as provider or target evidence.

Expected success: `controls/setup-checked/receipt.json` has
`kind=native-setup-checked-v1`, `status=ready`, hashes for source bytes and modes, frozen setup,
both signed authority objects, image, recipe, threat model, outputs and
dependencies, plus exact cleanup and a remaining setup allowance observation.
The script exits zero only when its checks pass and writes the JSON artifact.

## Host use

`setup-build-approval-template` takes the stopped setup run root, exact
digest-pinned image ID, a private catalog directory, workspace/memory/time
limits, at least one selected regular output path and approval times. The
catalog directory contains `catalog.json` with kind
`native-setup-dependency-catalog-v1` and entries of `id`, `path`, `sha256`, and integer Unix `mode`;
each selected file is under `payload/<id>`. Its entries must exactly match the
proposal's `offline_dependencies` list. The template returns two unsigned
objects: `scope_amendment` and `approval`. The operator signs each object with
the same pinned SSH identity and namespace used for setup, embedding an
`operator_signature` proof in each. Save them together as
`{"kind":"native-setup-build-authority-v1","scope_amendment":...,"approval":...}`.
Keep the private key outside the run and source trees.

Run `python3 tools/native_setup_builder.py setup-build --run-root <stopped-setup-root> --approval <signed-authority.json> --dependency-catalog <catalog-dir>`. The builder creates one bounded, network-none container, journals each Docker effect before dispatch, checks its resource envelope before start, reads back the mounted source and dependencies, runs the approved recipe on a disposable copy, saves selected outputs, and removes the exact labeled container. A failed or uncertain effect does not become `ready`; the same approval cannot dispatch a second build.

Use `setup-build-status` for the pending action and cleanup state. If the host died, run `setup-build-reconcile --run-root <stopped-setup-root>` to inspect and remove the exact owned build container. It retains uncertain actions and charges the full approved build time as an upper bound. If cleanup is unresolved, correct the daemon or resource problem and run reconciliation again. After complete reconciliation, generate a new template and sign both new objects. They bind prior attempt receipts and cumulative charged time. `setup-build` archives the settled attempt before a fresh effect.

`setup-build-status --verify-checked` rechecks the ready package and current authority; add `--historical` only when verifying an already-sealed package after the grant has expired. A subsequent research run needs its own authority.
