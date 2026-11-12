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
| Executable dependency or output loses its mode, or archived mode changes | Keep the approved executable bit in the checked package and reject later mode drift. |
| Secret-like output | Reject the result, retain only hashes and a redaction flag; never save raw command output. |
| Workspace, output, process, time or memory limit exceeded | Stop, remove the exact owned container, and report the bounded failure. |
| Host crashes after a create, start, exec or output-read dispatch | Durable pending action remains `unknown_effect`; a second build call must not repeat it. Reconciliation checks and removes the exact owned container, retains the uncertain action, and charges the full approved build duration as an upper bound. |
| Incomplete container cleanup or changed source after execution | Never emit `ready`; retain the journal, run root, and exact cleanup failure. |
| Successful commands but missing selected output | Report blocked with the missing path; never mark a security result. |

## Public end-to-end scenario

Run `PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_native_setup_builder_e2e.py --output /tmp/native-setup-builder-e2e.json` with a working local Docker daemon, an already-local `busybox:1.37` image, `ssh-keygen`, OpenSSL and Go. The scenario creates a fresh harmless multi-file source, compiles the local relay source, prepares synthetic signed setup authority, and fabricates stopped v1 and v2 setup receipts. It signs the separate offline-build amendment and approval, invokes the public `setup-build` CLI twice against real local Docker, and saves input pins, output hashes, journal and cleanup observations. It exercises missing stop proof and dependency, changed approval and source, active/inconsistent provider ledgers, executable mode preservation and drift, in-container source/dependency readback, no automatic retry, and synthetic pending-action reconciliation. It labels fabricated setup-turn, stop, and host-crash records. It does not call a provider or target service, kill a real builder process, or qualify a real model turn. Other matrix rows are implementation boundaries, not observed scenario passes.

Pass `--keep-root /absolute/new/private/dir` to retain the synthetic checked
v1 `run/` and v2 `linked-run/` for a downstream local transition scenario. The
fixture's signing private key is removed before the scenario returns. The JSON
receipt gives both run-root paths. Do not treat these fabricated setup records
as provider or target evidence.

Expected success: `controls/setup-checked/receipt.json` has
`kind=native-setup-checked-v1`, `status=ready`, hashes for source, frozen setup,
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

Run `python3 tools/native_setup_builder.py setup-build --run-root <stopped-setup-root> --approval <signed-authority.json> --dependency-catalog <catalog-dir>`. The builder creates one bounded, network-none container, journals each Docker effect before dispatch, checks the mount source and in-container source/dependency bytes, probes runtime and dependencies, runs the approved recipe on a disposable copy, reads selected outputs twice with their executable bit, then removes the exact labeled container. A failed or uncertain effect does not become `ready` and the same run cannot automatically dispatch a second build. Use `setup-build-status` for the pending action and cleanup state. If the host died, run `setup-build-reconcile --run-root <stopped-setup-root>` to inspect and remove the exact owned build container; it retains uncertain actions and reports an upper bound for charged build time. It never retries the build or grants new authority. `setup-build-status --verify-checked` rechecks the ready package and current authority; add `--historical` only when verifying an already-sealed package after the grant has expired. A subsequent research run needs its own authority.
