# Retained specialist context across related tasks

The runner can retain a specialist's live native session when its completed task
is followed by a ready task with exactly the same resources and runtime authority.
It first observes a completed native invocation and reads back the existing native
session. One controller event consumes the old task result, claims the next task
in lead priority order and updates only the current dispatch's assignment. The
previous grant remains in immutable history. The session, process owner, worker
generation, workspace, resource reservation and lease remain the same. Each later
model invocation is counted normally.

This transition does not assert cleanup, a fresh environment or a clean replay.
Recorded pending or unknown target effects, tool executions and auxiliary captures prevent
reuse. Same-owner `native_tools` and `network_proxy` stdio services remain recorded
as dispatched; they are deliberately kept alive, not called settled. The runtime
adapter readback establishes the same session with no active invocation or pending
host callback. It is not an inventory of arbitrary background lab processes. The
same resources remain owned and cleanup remains pending. A repeated identical owner
receipt is accepted only under the current active grant. A changed owner, expired
lease or revocation still refuses it.

Reviewers keep fresh contexts. Changed resources, missing ready work, failed native
readback and controller recovery keep the existing cleanup and reconstruction path.
The controller does not skip a higher-priority incompatible task to find one that
would permit reuse. No conversation store, new scheduler or private transcript
persistence was added.

## Repeat the checks

The signed controller/runner scenarios need Python 3 and `ssh-keygen`:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_engagement_retained_specialist_e2e.py --output /tmp/retained-specialist.json
```

Expected: 26 scenarios pass. Native owners, environments and target observations
in this suite are explicitly simulated. `before.json` records the failure-first
run before the controller/runner change; `after.json` records the final result and
source hashes. The lifecycle regression initially found a changed refusal code;
`lifecycle-before-fix.json` preserves that failure. The existing `worker_stale`
refusal for an active owner replacement was restored. All five lifecycle checks
and the other affected regressions then passed.

The two opt-in native checks require macOS, the pinned Codex 0.166.0 and OMP 18.20.0
binaries, Bun and the existing OMP SDK package. The OMP fixture also uses OpenSSL.
Pass the installed SDK directory explicitly:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_codex_native_tools.py --retain-session --output /tmp/retained-codex.json
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_omp_provider_boundary.py --retain-session --omp-sdk /absolute/path/to/node_modules/@oh-my-pi/pi-coding-agent --output /tmp/retained-omp.json
```

`native-codex.json` and `native-omp.json` observe actual native processes and tool
owners across two invocations. The second invocation includes the earlier native
conversation and reads a file created by the first invocation. Codex uses its
selected external `NativeExecutor`; OMP uses its existing `ToolOwner`. Both native
APIs already supported this operation before the controller change. Model replies
come from owned loopback fixtures, with no external provider contact. The raw
native checks do not execute the new controller transition; the signed workflow
suite exercises that transition separately.

`checks.json` records exact commands, results and exercised source hashes;
`manifest.json` binds the saved files. These checks do not establish the joined
Docker workflow, Linux ownership, SSH behavior, live provider behavior, application
reset, a multiday soak or operator-owned fresh-target research acceptance.
