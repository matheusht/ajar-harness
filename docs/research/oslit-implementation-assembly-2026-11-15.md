# OSLit implementation assembly, November 15

Continuation update: conformance now passes all 900 checks. The scanner recognizes
only the exact path, full-file digest and known synthetic literal of each of the
three archived probes. Five failure-first regression scenarios passed; archived
bytes remain unchanged. The earlier failure below is retained as a checkpoint.
The assembly is published on `codex/oslit-integrated-e2e-20261115`. Hosted structural
conformance passed at `eedb24c9`; the full workflow later refused the stale v4
checker pin. A v5 successor preserves every preexisting v4 byte. The full hosted
conformance workflow subsequently passed at `9415de22` and `dd63fe81` (899 structural
checks, zero failures; v5 frozen inputs intact). OMP completed the joined workflow at
`f244b003`, with subsequent passes including `c1fa3a77`. Both Codex and OMP completed the full
joined workflow at `e93a4fd9`; each saved result has 21 passing checks and verified
cleanup. Full conformance passed all 37 steps at `c1fa3a77`, including the schema
cache repair. Conformance for the later guarded-send fix is still running.

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
execution; evidence, unfinished search and cleanup remain distinct. Both pinned runtimes now have an observed joined source workflow against an
owned deterministic provider. That does not complete the plan's wider acceptance
across every access mode, environment, concurrent team workload and long run.

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

The [header diagnostic run](https://github.com/matheusht/redteam-harness/actions/runs/43736379813)
at `00850047` isolated OMP's invocation refusal to `network_header_name_invalid`:
the proxy rejected the request before any model POST reached the provider.
The integrity-verified OMP 18.20.0 client adds `session_id` for OpenAI sessions;
the incoming parser rejected underscores although the forwarding parser already
accepted them. The one-line repair aligns the two token rules. The local owned-TLS
workflow now passes all 22 checks, including forwarding `session_id` and retaining
duplicate, framing, size and control-character refusals; the existing seven-check
TCP gate workflow also passes. These results precede the next native run. The fixture
now answers only OMP's exact authenticated model-discovery GET, counted separately
from model invocations. Its seven local checks preserve refusal of other paths,
queries, bad credentials and Codex discovery requests.
Codex's default policy still refuses namespace creation. A named, confined policy
candidate is being prepared for harmless replay; no production policy has changed.

The [OMP repair run](https://github.com/matheusht/redteam-harness/actions/runs/43737579256)
at `f244b003` passed all 21 joined OMP checks: two native invocations, four model
POSTs, one separately counted discovery GET, no provider escapes or errors, retained
conversation and workspace state, owner-loss stop, revocation, recovery, verified
export and cleanup. Docker also passed. This is actual pinned native execution
against an owned deterministic provider, not external-provider or research acceptance.
Codex still failed before model requests. Its next disposable-host replay selects
fixed, digest-pinned seccomp and named AppArmor profiles for a harmless Bubblewrap
command only. It verifies the unchanged outer container controls and a denied mount
outside the child user namespace, then removes its owned container and profile.

The [confined-policy replay](https://github.com/matheusht/redteam-harness/actions/runs/43739457623)
at `5d9da3c5` loaded the candidate AppArmor profile in enforce mode and permitted
the user namespace. The outer mount still failed with `EPERM` and zero effective
capabilities. Raw Bubblewrap then failed mounting `/proc`; candidate container
and profile cleanup were verified. The pinned Codex implementation has its own
fresh-proc preflight and fallback while retaining PID isolation. The next check
therefore invokes that native helper, preserving its default behavior. This
component result does not establish successful Codex execution or enable the
candidate policy in production.

The [native-helper replay at `c8cd74d4`](https://github.com/matheusht/redteam-harness/actions/runs/43742239085)
completed Codex's read-only sandbox command under the confined candidate policy.
The outer mount remained denied with zero effective capabilities; container and
host-profile cleanup verified. The artifact explicitly leaves the silent proc
fallback branch unobserved. The full Codex workflow still used the default tool
policy and refused namespace creation. Signed tool-policy integration is next.

The [conformance run](https://github.com/matheusht/redteam-harness/actions/runs/43725604808)
at `eedb24c9` passed structural conformance (899 checks, no failures) but later
refused revision 4's checker pin. Revision 5 records the changed checker under the
existing successor procedure; a local tamper control still rejects drift and all
preexisting v4 bytes remain unchanged. A later full run at `2640d491` hit the
legacy review staging deadline before structural conformance. That same gate
passed on the earlier hosted run and locally; no timeout was widened. There is
a [full hosted conformance pass at `9415de22`](https://github.com/matheusht/redteam-harness/actions/runs/43731100402):
899 structural checks, zero failures, and v5 frozen inputs intact. The schema and
retrospective gates also passed under hosted Python 3.15.2. This verifies that
repository workflow at that revision; subsequent commits refine diagnostics, and a
final check must cover the finished repair. OMP's joined fixture passes at `f244b003`;
Codex and the broader delivery gates remain open.

The [full conformance run at `dd63fe81`](https://github.com/matheusht/redteam-harness/actions/runs/43738351015)
also passed. The canonical lifecycle step completed after 16m29s, within a 31m45s
workflow; it was ongoing work, not a stalled process. A separate intermittent
signed-review staging deadline remains under repair without raising the deadline.

The schema setup repair now reuses parsed schemas and the registry only for an
exact matching filename/byte snapshot. Every record and current schema bytes remain
checked. Twelve focused mutation/refusal checks and the full signed-review self-test
passed. Five alternating pairs of real synthetic signed-review writes completed
and independently verified on both versions; local median command time fell from
7.967846s to 3.714510s. The 10-second prewrite deadline is unchanged. See the
[saved comparison and repeat commands](../../evals/native-qualification/team-evidence/schema-cache-20261115/README.md).
These macOS timings are not a hosted Linux performance claim; the changed revision
still requires full hosted verification.

## Signed Codex integration and repeated-turn repair

The [hosted workflow at `e93a4fd9`](https://github.com/matheusht/redteam-harness/actions/runs/43751103990)
completed both Codex and OMP startup and joined scenarios. All three jobs passed,
including the Docker, owned loopback SSH and application-reset workflow. The signed optional tool policy
uses pinned seccomp bytes and a preinstalled named AppArmor profile; readback
confirmed the model container retained its default policy. The absent-profile
scenario refused startup and cleaned up. Docker's error names AppArmor but does
not repeat the profile name, so attribution combines that error with the exact
configured profile, observed host absence and nonrunning container state.

The first integrated replay at `1d2f9a66` completed one tool invocation, then timed
out on the second turn before another provider request. A controlled peer
reproduced a dispatch-lock cycle: the response waited for an executor callback,
while the response waiter held the callback's admission lock. Codex now rechecks
authority at the request write and releases the guard before awaiting its reply.
Executor operations retain their own admission checks; no timeout was widened.
The [failure-first regression](../../evals/native-qualification/team-evidence/codex-admission-20261115/README.md)
records the red and green results. A revocation between initial bookkeeping and
the guarded write can still leave a conservatively unknown invocation requiring
reconciliation, even if no request was sent.

Each hosted native result passed 21 checks: two native invocations and four controlled
provider POSTs, retained conversation and lab state, input/credential/process/network
separation, guardian stop after owner loss, revoked-call refusal, reopened receipt
recovery, idempotent cleanup, released reservation and all export checks. The tool,
model, prepared images and owned AppArmor profile were cleaned up. External provider
calls were zero and research acceptance was not run. OMP also made one separately
counted model-discovery GET. The [saved hosted results](../../evals/native-qualification/team-evidence/codex-admission-20261115/hosted/)
retain the exact source hashes and bounded observations.

The [conformance run at `c1fa3a77`](https://github.com/matheusht/redteam-harness/actions/runs/43748757758)
passed all 37 steps in 21m44s, including the schema-cache and canonical lifecycle
gates. PR #220 also retains the later [passing final-runtime conformance run](https://github.com/matheusht/redteam-harness/actions/runs/43751103945)
at `e93a4fd9`; this predates the provider-accounting completion pass. The focused
lock regression, UTF-8 transport and provider-free startup ownership checks passed.
The broader controlled adapter fixture exposed a cancellation assertion on both old
and new runtime code. The November 15 completion pass traced it to a missing
`HostOperation` import in the fixture. The corrected controlled Codex/OMP check passes;
no production cancellation change was needed.

## Remaining implementation and delivery

| Area | What remains |
| --- | --- |
| M0–M2 | Both pinned runtimes have joined source-workflow evidence. The controlled adapter fixture is corrected. Extend verification to live-model concurrent team behavior during operator testing. |
| M3 | Exercise actual acquisition, setup failure and repair, all access modes, reset/replay and cleanup through the joined workflow. Verify loss/reconnection against a separate authorized SSH host. |
| M4 | Qualify physical owned-lab state, independent replay and cleanup in that workflow. Unsupported artifact classes still stop; existing operator gates remain active until policy adoption. |
| M5 | Provider proxy attempts now have durable start/completion records with worker, dispatch and invocation attribution. Tokens/estimates and missing dimensions are reported separately. Real billing receipts and hard dollar/token caps are unsupported. Sustained restart/multiday operation remains operator verification. |
| M6 | Full hosted conformance passed at `c1fa3a77` without rewriting historical evidence. The [operator handoff](../agents/fresh-target-handoff.md) covers setup through export/cleanup. This completion pass skips CI as requested. Retire redundant callers only after parity. |
| Research acceptance | The operator owns the fresh-target test and fair native-agent comparison. It has not run. |

The review found no additional missing major subsystem. It did not prove every
intended behavior works. Optional capture output-directory manifests remain
unimplemented; the approved plan does not require that particular interface.
Existing transfer digests never prove that downloaded code executed.

The integration branch is published for review and has not been merged.
Source, scenario definitions and provenance remain in the branch; hosted results
are attached to the linked runs. Local verification logs and downloaded hosted
artifacts, including source hashes, are retained separately for the handoff.

The final integration review found six archived server logs omitted by the original
assembly commit. Their exact base bytes were restored, and all six comparisons
matched. Structural conformance then passed 900 checks with zero failures in the
pinned local environment. This repair preserves the existing records; it does not
replace them with a new execution.
