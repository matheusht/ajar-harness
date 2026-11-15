# OSLit implementation assembly, November 15

Continuation update: conformance now passes all 900 checks. The scanner recognizes
only the exact path, full-file digest and known synthetic literal of each of the
three archived probes. Five failure-first regression scenarios passed; archived
bytes remain unchanged. The earlier failure below is retained as a checkpoint.
The assembly is published on `codex/oslit-integrated-e2e-20261115`. Hosted structural
conformance passed at `eedb24c9`; the full workflow later refused the stale v4
checker pin. A v5 successor preserves every preexisting v4 byte.
Neither native runtime has completed the joined workflow.

This is a local implementation candidate, not an accepted release or qualified
research workflow. It combines the source at `5d290d19`, the staged bounded
lab-state implementation and PR 211–219 source changes. `ASSEMBLY-PROVENANCE.json`
records the imported revisions. The original worktree and its interrupted Git
operation remain untouched.

Signed GET/HEAD acquisition now reaches both persistent and capture lab gates.
Its records preserve transfer provenance, separate acquisition from target-state
observations and retain unknown cleanup obligations. Independent review corrected
entrypoint routing, URL-secret checks, inventory identity types and lab-artifact
result projection. A later runtime review fixed the OMP tool validator's missing
module-scope binding. These source corrections do not establish native runtime
qualification.

The implementation broadly follows the approved design: one journal owns team
state; authority and budgets survive replacement; native adapters supply worker
execution; evidence, unfinished search and cleanup remain distinct. Delivery has
not met the plan's requirement for an observed integrated workflow on every
supported runtime and environment.

## Current local verification

GPT-6 Luna agents ran the checks on November 15. The contract, team, evidence,
runner, coordination and frozen-guidance workflows passed with their declared
local or simulated peers. Acquisition and inventory checks passed. The export
integrity, reference closure and result consistency suites passed 19, 17 and 14
cases respectively after their temporary roots were made canonical on macOS.
Production symlink rejection was preserved.

Package metadata, transport diagnostics, archive-fixture installation, startup
diagnostics, staging/lease recovery and cumulative OMP-cost scenarios passed
within their documented fixture boundaries. The offline OMP loader suite passed
61 cases after its Linux storage observation was explicitly simulated in the
existing host-side fixture. Production mount observation was unchanged; this is
not a host noexec or native loader qualification. The owned-lab-state scenario
passed 14 contained families with `physical_mount_qualification: false`.

The account workflow originally expected a closed-resolver error from a new
outer request wrapper. A diagnostic observed `worker_stale` and no target request:
authority was refused. The fixture now checks private account-resolver closure
directly; all seven account scenarios passed. Its local HTTP behavior remains
distinct from real target-account or native-container qualification.

These local checks do not establish a joined native research run. The local Docker
daemon was unavailable, no separate disposable remote host was supplied, and the
exact pinned Bun/OMP package was unavailable locally. The newer hosted checks
below exercise the assembled source; earlier receipts retain their original scope.

At the earlier assembly checkpoint, repository conformance under the pinned Python
environment completed 900 checks with one failure: the secret-shape scan flags synthetic bearer strings
in three archived diagnostic fixtures. Those historical bytes and the scanner
were preserved. That checkpoint was a release-gate failure; the narrowly pinned
scanner correction described above subsequently passed locally and in hosted CI. The initial missing-dependency failures disappeared under the correct
environment; whitespace checks passed. A separate legacy observation check also
refused its historical source pin before execution and supplies no v2 evidence.

## Hosted observations

The [assembled native run](https://github.com/matheusht/redteam-harness/actions/runs/43725604682)
at `eedb24c9` passed the Docker environment, container guardian, owned loopback SSH,
and application reset checks. Codex's executor reached verified readiness but
thread creation failed when Bubblewrap could not create a user namespace. OMP's
SDK imports, tool catalog and model version checks passed; its model process then
exited before readiness. Neither made a controlled or external provider request.
Both failed-run journals exported successfully and passed byte integrity,
reference closure and result consistency checks; cleanup was verified.

The [namespace diagnostic run](https://github.com/matheusht/redteam-harness/actions/runs/43726713247)
at `2a0f04b5` found that the runner host permits `unshare(CLONE_NEWUSER)` while the
tool container refuses it with `EPERM`. The container has Docker's seccomp filter
and no effective capabilities. This localizes the incompatibility to container
policy; it does not justify bypassing the native sandbox. OMP's new stderr
self-check hit Linux's argument-size limit before the startup diagnostic step.
The joined OMP check still ran and failed before readiness. The fixture now
passes that synthetic payload through stdin, and startup diagnostics run even if
an earlier diagnostic check fails. Sandbox settings remain unchanged. The later
[startup diagnostic run](https://github.com/matheusht/redteam-harness/actions/runs/43727095656)
at `07ac9ff2` identified OMP's exact refusal: a custom model definition requires
an `apiKey` or an explicit alternate authentication mode. The fixture now names
`OPENAI_API_KEY` as the environment reference, following the integrity-verified
18.20.0 package resolver. No key value is written to its catalog; the owned
provider still requires the synthetic credential. The next run reached the publication guard, which classified that public reference
as a credential assignment. The guard now recognizes only the exact parsed JSON
member `apiKey: OPENAI_API_KEY`; actual credential and known-secret checks retain
the original bytes. Four accepted and eight rejected cases, frozen signed inputs,
and the 75-check contract suite passed locally.

The [next native run](https://github.com/matheusht/redteam-harness/actions/runs/43731100404)
at `9415de22` passed OMP startup. Its joined invocation did not complete and made
zero controlled provider requests. Both failed journals again passed all three
export checks and verified cleanup. Codex still failed before startup. A fixed,
harmless policy comparison found two restrictions: removing seccomp allowed the
user namespace, then Docker AppArmor denied Bubblewrap's mount operation. The
both-relaxed probe hit a loopback setup error. The [pinned Codex argument builder](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/linux-sandbox/src/bwrap.rs)
requires a network namespace for this network-disabled profile; the next probe
will match those native flags. The error does not by itself identify a missing
outer capability: [vendored Bubblewrap](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/vendor/bubblewrap/bubblewrap.c)
sets up loopback before dropping final sandbox capabilities. These disposable component
diagnostics do not qualify a runtime or change production sandbox policy.

The [faithful-probe run](https://github.com/matheusht/redteam-harness/actions/runs/43732699926)
at `9430bc34` reproduced the Codex restrictions, including loopback failure with
both outer filters relaxed. The child namespace reported AppArmor profile
`unprivileged_userns`; the exact loopback denial remains unattributed. Production
sandbox settings remain unchanged. OMP startup passed; its first model invocation
finished with status `error` and `403 status code (no body)`. The provider observed
one GET during startup and no model POST. `src/config/model-registry.ts` in the
[pinned OMP package](https://registry.npmjs.org/@oh-my-pi/pi-coding-agent/-/pi-coding-agent-18.20.0.tgz)
wires builtin OpenAI model discovery at `/v1/models`; that startup request does not establish the
cause of the later invocation refusal. Bounded route and gate diagnostics are next.
Both failed-run exports again verified and cleanup settled. Docker's ancillary
workflow passed. No native work or retention qualification follows from these runs.

The [conformance run](https://github.com/matheusht/redteam-harness/actions/runs/43725604808)
at `eedb24c9` passed structural conformance (899 checks, no failures) but later
refused revision 4's checker pin. Revision 5 records the changed checker under the
existing successor procedure; a local tamper control still rejects drift and all
preexisting v4 bytes remain unchanged. A later full run at `2640d491` hit the
legacy review staging deadline before structural conformance. That same gate
passed on the earlier hosted run and locally; no timeout was widened. There is
no full hosted conformance pass yet. Neither native runtime is qualified.

## Remaining implementation and delivery

| Area | What remains |
| --- | --- |
| M0–M2 | Verify the combined contracts, controller and protected Codex/OMP workflow with the exact installed runtime packages; repair any defects exposed by that execution. |
| M3 | Exercise actual acquisition, setup failure and repair, all access modes, reset/replay and cleanup through the joined workflow. Verify loss/reconnection against a separate authorized SSH host. |
| M4 | Qualify physical owned-lab state, independent replay and cleanup in that workflow. Unsupported artifact classes still stop; existing operator gates remain active until policy adoption. |
| M5 | Run the sustained restart/multiday scenario. Provider request totals and billed spend are still unavailable; invocation and worker-second enforcement must not be described as complete monetary accounting. |
| M6 | Conformance's archived-fixture scan failure is resolved without rewriting historical evidence. Promote the candidate through required hosted checks and an operator install-to-export/cleanup handoff. Retire redundant callers only after parity. |
| Research acceptance | The operator owns the fresh-target test and fair native-agent comparison. It has not run. |

The review found no additional missing major subsystem. It did not prove every
intended behavior works. Optional capture output-directory manifests remain
unimplemented; the approved plan does not require that particular interface.
Existing transfer digests never prove that downloaded code executed.

The test branch was pushed to run hosted checks. No PR or merge was created.
Source, scenario definitions and provenance remain in the branch; hosted results
are attached to the linked runs. Local verification logs and downloaded hosted
artifacts, including source hashes, are retained separately for the handoff.
