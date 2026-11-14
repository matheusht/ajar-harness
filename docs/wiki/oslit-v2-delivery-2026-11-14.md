# Candidate v2 delivery — 14 November 2026

The Codex/OMP team route has substantial implementation and bounded engineering
checks. **The complete M0–M6 assignment is unfinished.** It is not a qualified or
adopted research workflow. The operator owns the future fresh-target test and
comparison with a capable native agent.

This page summarizes the candidate descended from `183199cc` and the linked
follow-up evidence. The [public CLI delivery unit](../../evals/native-qualification/team-evidence/m6-public-cli-20261114/README.md),
integrated at `c56d562f`, connects inspect/run/resume/stop to the composed preflight
and real runner; its deliberately unavailable native fixture does not establish a
complete native research run. The [implementation record](../research/oslit-implementation-2026-11-14.md)
tracks integration; each saved receipt identifies the source it exercised. A
receipt from an earlier unit does not certify later changes. The
[October source-route assessment](native-research-status.md) remains a separate
historical observation.

## Implemented behavior and evidence

| Area | Candidate implementation | What the evidence establishes |
| --- | --- | --- |
| Authority and one state owner | [Signed v2 inputs](../../tools/engagement_contract.py), [journal/controller](../../tools/engagement_controller.py), public `native_engagement.py` facade and preserved old-route readers | [Contract](../../evals/native-qualification/smoke/check_engagement_contract_e2e.py) and [team workflows](../../evals/native-qualification/smoke/check_engagement_team_e2e.py) exercise signed disposable inputs, durable events, authenticated requests, reservations and replay. Simulated workers do not establish native containment. |
| Codex and OMP | Native tools, sessions, host operations, isolated model credential binding, owned startup/recovery receipts and separate provider/tool routes | [Actual native checks](../../evals/native-qualification/team-evidence/m2-native-boundary-20261114/README.md) used installed Codex 0.166.0 and OMP 18.20.0 against owned fake provider responses. These are native-process observations, not live model or provider qualification. |
| Environments and accounts | Source/binary/application/combined descriptors, local or SSH Docker transport, lease ownership, exact resource readback, target account injection and separate cookie state | [Environment checks](../../evals/native-qualification/team-evidence/m3-environment-20261114/README.md), [renewed execution](../../evals/native-qualification/team-evidence/m3-renewed-execution-20261114/README.md) and [account checks](../../evals/native-qualification/team-evidence/m3-target-accounts-20261114/README.md) distinguish actual local sockets/processes from simulated Docker/SSH responses. Logical account selection does not prove which user a real target recognizes. |
| Coordination and evidence | Versioned shared updates/instruments, independent review packets, strategy obligations, lead replacement, protected experiments and reviewed closure | [Evidence workflows](../../evals/native-qualification/smoke/check_engagement_evidence_e2e.py), [coordination workflows](../../evals/native-qualification/smoke/check_engagement_coordination_e2e.py) and [boundary composition](../../evals/native-qualification/team-evidence/m5-native-boundary-20261114/README.md) establish their local mechanics. Native/environment peers are simulated where explicitly stated. Protected source capture does not establish clean replay of a remote application's state. |
| Usage and continued work | Shared invocation/worker-second reservations; late and duplicate settlement; optional overall deadline; renewable workers | [Actual native accounting](../../evals/native-qualification/team-evidence/native-usage-accounting-20261114/README.md) preserves per-invocation reported tokens, retries and interrupted partial usage against fake provider responses. Provider request totals and billed spend remain unavailable. Short renewal checks and clock scenarios are not multiday operation. |
| Operator delivery | [Pinned installation](../agents/native-tool-installation.md), [input templates](../../examples/native-engagement-v2/README.md), [guide](../agents/engagement.md), preflight, export, portable methodology and CI selection | [Installation evidence](../../evals/native-qualification/team-evidence/m6-native-installation-20261114/README.md) and [guidance workflow](../../evals/native-qualification/smoke/check_engagement_guidance_e2e.py) cover their stated local boundaries. CI wiring is not a hosted CI result or a complete install-to-cleanup run. |

The portable methodology and OSLit worker protocol are separate files. New
engagements freeze both at initialization; resume verifies those bytes and export
includes both files and their hashes. Give the exported methodology to a native
baseline for a fair comparison. Historical v2 records without frozen guidance
remain readable and stoppable; active research cannot acquire new guidance by
silently rewriting that history.

An active native worker keeps its conversation context. Later tasks and recovered
workers reconstruct context from published records and frozen inputs. Exact native
conversation continuity across those boundaries is not established.

## Remaining engineering and qualification gaps

| Milestone | Remaining completion boundary |
| --- | --- |
| M0 — contracts | Design/contracts and failure scenarios have local review; their assumptions still need the integrated execution evidence required by the plan. |
| M1 — one state owner | Final public workflow integration must preserve sole ownership, revocation and exact cleanup across the combined runtime/environment path. |
| M2 — runtimes/team | Actual native tools have local evidence, but the full joined protected workflow and Linux model-host boundary remain unqualified. Linux model-host execution is currently unsupported. |
| M3 — environments | Actual Docker containment, actual SSH host/disconnect/cleanup, complete setup repair and remote application reset/replay remain unverified. Local fake transport checks cannot close these items. |
| M4 — research/evidence | Local review/claim controls need the joined workflow's execution proof. A signed impact/escalation ceiling alone does not implement fresh artifact approval, an artifact cleanup ledger or prior-rung review. Existing repository gates remain active. |
| M5 — long operation/usage | No actual multiday soak or sustained host restart result; provider request totals, billed spend and monetary caps remain unavailable. Report missing usage dimensions explicitly. |
| M6 — delivery | Final integrated verification, hosted CI and an operator-install-to-cleanup release-candidate handoff remain open. Broader caller retirement waits for parity evidence. |

The protected model owner currently uses macOS `sandbox-exec` and Darwin process
birth identity. A Linux tool container is a different boundary. Native tools
require the owned Docker environment; the candidate provides no uncontained host
tool fallback. The local macOS listener/network check is not a proof of Docker
network isolation.

The development Docker endpoint did not provide usable live verification, and the
operator reported no disposable Linux/SSH host. Existing services and data were
preserved. Missing infrastructure is an unavailable verification result, not a
passing environment scenario or permission to reduce the agreed delivery scope.

## Repeatable portable checks

The [conformance workflow](../../.github/workflows/conformance.yml) retains existing
structural and historical checks and adds seven provider-free v2 workflows:
contract, team, evidence, runner, coordination, frozen guidance and target
accounts. They need Python 3.11+, `ssh-keygen`, Unix file locks/sockets and owned
loopback listeners. The account workflow uses actual owned HTTP receivers; native
worker and environment behavior is simulated in the controller workflows.
No external provider, research target, Docker daemon or SSH host is required.

Run the commands in that CI step with `RUNNER_TEMP` set to a caller-owned temporary
directory. Expected: every command exits zero and writes its JSON receipt under
`oslit-v2-checks/`. CI uploads those receipts under the checked Git revision even
when a scenario fails. Local execution of the same commands is local evidence;
only a completed hosted run can establish hosted CI status.

Read [the operator guide](../agents/engagement.md) for inspect/run/status/direction,
stop/recovery and export. Status distinguishes authority, cleanup, resource holds,
claim disposition and usage completeness. An internal bundle does not grant
publication, filing or deployment authority.
