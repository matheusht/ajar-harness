# Kanboard native capture adapter: checks before implementation

This adds only the target-specific host observer seam for #158/#159. It uses
the PR187 PHP app hook and collector; it does not launch OpenCode, a provider,
or a live target. The smallest serious alternative is a transport-only proxy,
which cannot establish Kanboard's authenticated actor or same-request SQLite
transition. The adapter therefore pins the existing app-side capture and
refuses an origin claim until independent process/tool evidence exists.

## Required integration

The native owner prepares `controls/observer` before creating target containers.
Only the target gets the read-only probe mount and `auto_prepend_file`; only the
collector gets a writable receipts directory under `controls/observer`. Target
and collector share a private internal network that no researcher, reviewer,
resume, or relay container joins. Target source stays a clean copy of the
original Kanboard v1.2.36 commit. The native owner must seal exact Docker IDs,
network IDs/IPs, mounts, image IDs, source hashes, and a dispatch record before
turn execution. A host observer arms a receipt window before each relevant
native dispatch and closes it after the producer has stopped.

The pinned source manifest is the 2,079-file `git archive HEAD` of Kanboard
`644ad39125b205b1432755d3b614a79068590d2c`, hashed exactly as the native
runner does with `sha256(json.dumps(inventory, sort_keys=True))`:
`056280086b353347075f0352b5826bd20ef7328854e7283e4c5cd71d7e57f839`.
It contains `data/.htaccess` and `data/web.config`, but no seeded SQLite DB.
The native plan and the operator approval must include `kanboard_capture` with
the adapter/probe/collector file hashes and source/controller pins; otherwise
`stage()` refuses. The adapter uses the plan's exact pinned Docker executable.

Call order for a runner integration:

1. `prepare` copies clean Kanboard source. `stage(root, target, s=..., q=...,
   t=..., b=...)` prepares one observer slot for `target`, `review-target-1`,
   or `review-target-2`, returning the read-only hook mount, target environment,
   PHP `auto_prepend_file` option, and collector mounts. All three target slots
   need separate collectors for independent reviewer observations.
2. Create the target with the hook mount and environment. Call
   `activate(root, target)` before the NativeRun eight-producer manifest is
   sealed. It predeclares a separate host-owner ledger, creates one internal
   observer network, attaches only that created target at a reserved IP, and
   starts one collector outside the eight-producer manifest. On any exception
   while the target remains `created`, call `abort_activation(root, target)`;
   it discovers an unsealed create by exact name and label and preserves the
   target for the runner's own cleanup. An already started target must instead
   follow NativeRun's verified stop path.
3. NativeRun starts the eight producers. The host must seed the synthetic
   private case before dispatch. Seeding `data/db.sqlite` between `prepare`
   and the current runner's `start` fails `_verified_plan(pristine=True)`;
   either seed after native startup but before the first model turn, or change
   that pristine check to allow only the declared mutable `data` subtree while
   preserving all immutable source checks. No credential may be placed in an
   OpenCode mount, prompt, output, trace, or persistent history.
4. After the durable `unknown_effect` dispatch journal and before `docker
   exec`, call `bind_dispatch(root, target, id)`. This host-inspects the
   selected researcher/reviewer/resume container, target, collector and
   network, then seals the exact session and collector prefix. It deliberately
   returns a hold for missing credential and native-origin proof. The separate
   recovery helper may arm/reconcile a one-request role grant, but cannot
   override these holds.
5. After NativeRun writes a verified `REVOKED` stop record and pauses or kills
   its eight producers, call `freeze(root, target)` to stop and hash the
   collector DB. After the runner removes its producer containers, call
   `cleanup(root, target)` to remove only the exact owned collector and network.
   A recovered owner follows the same order; partial preactivation uses
   `abort_activation`. Missing stop proof or ambiguous ownership remains held.

The current runner has not wired these calls or a redaction-safe credential
route. The observer is code-ready for integration, not native qualification.

The native researcher needs a way to authenticate without exposing synthetic
passwords, cookies, Authorization headers, or signed URLs to OpenCode prompts,
workspace, environment, tool output, native history, or provider requests.
PR187's host-client stdin path is useful for local controls only; it cannot be
credited as a native request. Until a host-controlled credential/session route
and host-verified tool/process origin are present, the adapter must return a
hold, even if app receipts and protected effects match.

## Failure conditions

| ID | Failure | Required check/result |
| --- | --- | --- |
| N01 | Source commit, controller, probe, collector, target image, or copied source changes | Reject source/build attribution before arming or on close. |
| N02 | Observer SQLite or collector writable mount is under any producer mount; researcher can join the collector network | Reject topology. The collector write path is host-owned under `controls/observer` and absent from every producer mount. |
| N03 | App hook absent, writable, wrong command/environment, or attached to wrong target/reviewer network | Reject topology; never infer instrumentation from a plausible receipt. |
| N04 | Host-client replay, another Docker exec, stale native dispatch, different role/session, or socket IP alone supplies the effect | Hold `native_origin_unproven` without a host-verified process/tool event bound to the same window. An OpenCode trace alone is not that proof. |
| N05 | Baseline B already has private Q access, T is not in Q, Q is public, or A lacks S manager role | Reject the operation before dispatch, using host-read SQLite and the app's denial control. |
| N06 | Collector row missing, reordered, duplicate, changed prefix, wrong app peer/client IP, wrong actor/route/body, or protected transition occurs outside the window | Hold or reject; preserve original rows and no automatic retry. |
| N07 | B fresh authenticated read is absent or reads a different task/actor; protected state or source changes before review | Hold result; do not call a role row alone a completed impact chain. |
| N08 | Password/cookie/header/raw body enters native storage or a saved observer result | Reject/redact and hold. Credential injection is an explicit missing prerequisite. |
| N09 | Collector/target fails, native stop is uncertain, or cleanup cannot identify exact owned resources | Hold with a fixed reason; leave originals for operator review and never infer success from absence. |
| N10 | NativeRun exits before `RUN.json`, after a partial producer start | `close_startup` accepts only `STARTUP_CLOSED` with no `RUN.json`/`REVOKED`/`UNSAFE`, the exact eight manifest IDs and owner labels, and all eight producers stopped; then it freezes the collector before producer removal. A missing/false marker, changed binding, or running producer holds. |
| N11 | Owner dies between writing `frozen.json` and setting observer ledger `frozen` | Retrying the same close must verify the immutable frozen record against the stopped collector DB and complete the ledger transition. A changed DB or record holds; it must not overwrite or silently accept either. The same retry rule applies to normal `REVOKED` freeze. |

Provider-free checks must exercise valid and mutated manifests, mount/network
isolation, source drift, stale/mismatched dispatch, unrelated collector rows,
and the deliberate no-origin/no-credential hold. The PR187 disposable Docker
E2E remains the application parity/control check; it is not a native test.

Current focused provider-free preparation check:

```sh
python3 evals/native-qualification/smoke/check_kanboard_capture_stage.py \
  --source /private/tmp/kanboard-source-644ad391 \
  --output /private/tmp/kanboard-capture-stage-NEW
```

Expected: `result.json` says `pass`, pins the source manifest, confirms the
observer sits outside the target mount, rejects source drift, and recovers a
simulated collector-create failure even when the network ID was not sealed.
This check uses a local fake Docker executable and makes zero Docker/provider
calls; runtime topology, process origin, fresh authenticated read, and live
cleanup still need a separate owned native run.

Provider-free terminal-close check (written before the close-path change):

```sh
python3 evals/native-qualification/smoke/check_kanboard_capture_close.py \
  --source /private/tmp/kanboard-source-644ad391 \
  --output /private/tmp/kanboard-capture-close-NEW
```

It must reject a false/missing `STARTUP_CLOSED`, a `RUN.json` overlap, a changed
manifest binding, a running producer, and a changed frozen record. It must
accept a verified startup close and retry the crash window after the immutable
record exists. It also retries an ordinary `REVOKED` close. The test uses a
fake local Docker executable only; it cannot qualify a live run.
