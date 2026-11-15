# Candidate v2 delivery — 14 November 2026

The Codex/OMP team route has substantial implementation and bounded engineering
checks. **The complete M0–M6 assignment is unfinished.** It is not a qualified or
adopted research workflow. The operator owns the future fresh-target test and
comparison with a capable native agent.

This page summarizes the candidate through `9a26c93d` and the linked
follow-up evidence. The [public CLI delivery unit](../../evals/native-qualification/team-evidence/m6-public-cli-20261114/README.md),
integrated at `c56d562f`, connects inspect/run/resume/stop to the composed preflight
and real runner; its deliberately unavailable native fixture does not establish a
complete native research run. The [implementation record](../research/oslit-implementation-2026-11-14.md)
tracks integration; each saved receipt identifies the source it exercised. A
receipt from an earlier unit does not certify later changes. The
[October source-route assessment](native-research-status.md) remains a separate
historical observation.

November 15 source reconciliation: the [local assembly assessment](../research/oslit-implementation-assembly-2026-11-15.md)
records the joined Codex/OMP source workflows with actual Linux runtimes and controlled
provider replies, acquisition, owned application reset and the bounded lab-artifact ledger.
The [fresh-target handoff](../agents/fresh-target-handoff.md) is the current operator entry.
The candidate is unmerged; research acceptance remains with the operator.

## Implemented behavior and evidence

| Area | Candidate implementation | What the evidence establishes |
| --- | --- | --- |
| Authority and one state owner | [Signed v2 inputs](../../tools/engagement_contract.py), [journal/controller](../../tools/engagement_controller.py), public `native_engagement.py` facade and preserved old-route readers | [Contract](../../evals/native-qualification/smoke/check_engagement_contract_e2e.py) and [team workflows](../../evals/native-qualification/smoke/check_engagement_team_e2e.py) exercise signed disposable inputs, durable events, authenticated requests, reservations and replay. Simulated workers do not establish native containment. |
| Codex and OMP | Native tools, sessions, host operations, isolated model credential binding, owned startup/recovery receipts and separate provider/tool routes | [Actual native checks](../../evals/native-qualification/team-evidence/m2-native-boundary-20261114/README.md) used installed Codex 0.166.0 and OMP 18.20.0 against owned fake provider responses. These are native-process observations, not live model or provider qualification. |
| Environments and accounts | Source/binary/application/combined descriptors, local or SSH Docker transport, lease ownership, exact resource readback, target account injection and separate cookie state | [Environment checks](../../evals/native-qualification/team-evidence/m3-environment-20261114/README.md), [renewed execution](../../evals/native-qualification/team-evidence/m3-renewed-execution-20261114/README.md), [account checks](../../evals/native-qualification/team-evidence/m3-target-accounts-20261114/README.md) and [native-boundary account integration](../../evals/native-qualification/team-evidence/m5-boundary-integration-20261114/README.md) distinguish actual local sockets/processes from simulated native/container peers and Docker/SSH responses. Private host references bind logical accounts to request observations; they do not prove which user a real target recognizes. |
| Coordination and evidence | Versioned shared updates/instruments, independent review packets, strategy obligations, lead replacement, protected experiments, current review for declared escalation and reviewed closure | [Evidence workflows](../../evals/native-qualification/smoke/check_engagement_evidence_e2e.py), [coordination workflows](../../evals/native-qualification/smoke/check_engagement_coordination_e2e.py), [declared escalation](../../evals/native-qualification/team-evidence/declared-escalation-20261114/README.md), [application capture](../../evals/native-qualification/team-evidence/m5-application-capture-20261114/README.md) and [source capture effects](../../evals/native-qualification/team-evidence/m5-capture-effects-20261114/README.md) establish local composition and admission mechanics. Native/container peers and reviewer judgments are simulated where stated; local probes and owned HTTP receivers supply the stated execution observations. |
| Usage and continued work | Shared invocation/worker-second reservations; late and duplicate settlement; optional overall deadline; renewable workers | [Actual native accounting](../../evals/native-qualification/team-evidence/native-usage-accounting-20261114/README.md) preserves per-invocation reported tokens, retries and interrupted partial usage against fake provider responses. The proxy now journals provider request attempts, completed responses and unknown outcomes, including retries and startup requests. Runtime tokens and estimates remain separate from unavailable provider billing receipts. Short renewal checks and clock scenarios are not multiday operation. |
| Operator delivery | [Pinned installation](../agents/native-tool-installation.md), [input templates](../../examples/native-engagement-v2/README.md), [guide](../agents/engagement.md), preflight, export, portable methodology and CI selection | [Installation evidence](../../evals/native-qualification/team-evidence/m6-native-installation-20261114/README.md) and [guidance workflow](../../evals/native-qualification/smoke/check_engagement_guidance_e2e.py) cover their stated local boundaries. CI wiring is not a hosted CI result or a complete install-to-cleanup run. |

The portable methodology and OSLit worker protocol are separate files. New
engagements freeze both at initialization; resume verifies those bytes and export
includes both files and their hashes. Give the exported methodology to a native
baseline for a fair comparison. Historical v2 records without frozen guidance
remain readable and stoppable; active research cannot acquire new guidance by
silently rewriting that history.

Protected capture can select a nonempty subset of the worker's resources.
Source/binary-only capture may name a signed local `effect_id`; application requests
select their own effect through `X-OSLit-Effect`. Initial setup still requires
exactly one account-free `read` effect at `source_only` or `self` covering the
selected resources and environment. A capture containing application access records
`clean_start:false` and `remote_application_reset_unverified` unless the capture
uses the later implemented signed owned-application reset. An uncontrolled remote
application cannot provide
the clean independent remote replay needed for claim confirmation or the next
escalation rung. A source-only subset of combined access can have a separate clean
local input without making a remote-reset claim.

New `stored` and `cross_user` intents require a current accepted review of the
independently confirmed predecessor and the exact next signed effect. Reopened
claims, superseded instruments and replacement review requests invalidate that
transition's admission. These internal checks preserve the repository's separate
operator review and impact-artifact gates. Generic `artifact_create` remains
unsupported. The harmless source fixture exercises adjacent declared rungs with
simulated reviewer judgments; it is not a demonstrated security escalation.

The [Q20 retention unit](../../evals/native-qualification/team-evidence/m2-retained-specialists-20261114/README.md)
keeps an eligible specialist's live native session for the next ready task with
the same resources and runtime authority. Reuse requires a completed invocation,
idle native readback and no pending or unknown protected effects/captures. The
session, workspace, ownership, lease and reservation continue; reuse asserts no
cleanup or clean replay. Reviewers stay fresh. Incompatible next work, failed
readback and controller recovery use cleanup and reconstruction from published
records and frozen inputs. Actual Codex/OMP checks observed prior conversation
and tool files across two invocations using owned fake provider responses. The
controller transition was checked separately with simulated native/environment
peers; the later joined source workflow verifies native continuity and cleanup with controlled provider replies; broader team behavior remains operator verification.

## Implementation and remaining verification

| Milestone | Current boundary |
| --- | --- |
| M0 — contracts | Implemented signed contracts, access modes, identities, limits and failure scenarios. |
| M1 — one state owner | Implemented controller/journal, reservations, replay and recovery; joined source workflow has actual runtime/container evidence. |
| M2 — runtimes/team | Both pinned runtimes passed joined Linux source workflows with controlled provider replies. The controlled cancellation fixture's missing import is corrected. Live-model team behavior remains operator verification. |
| M3 — environments | Source, binary, application and combined descriptors, acquisition, setup repair, Docker/SSH and owned application reset are implemented. The 15 November completion adds bounded disposable Docker state volumes and application artifact tracking. Separate remote-host loss, physical volume qualification and broader joined access combinations remain verification work. External persistent state requires a target-specific reset owner. |
| M4 — research/evidence | Evidence/control/replay, review/replacement, closure and bounded owned-lab artifact tracking are implemented. Physical lab-state qualification, live independent review and research acceptance remain unverified. Existing operator gates remain active. |
| M5 — long operation/usage | Shared limits, reservations, request-attempt journal, native token/estimate totals, completeness reporting, restart and no-deadline continuation are implemented. Real billing receipts and hard dollar/token limits are unsupported; sustained operation is unverified. |
| M6 — delivery | Installer, preflight, templates, export and the fresh-target handoff are available. Hosted evidence is retained for its checked revision; no new CI or fresh-target run is required by this implementation pass. The operator must configure a responding Docker/SSH lab, provider and target-specific signed inputs. |


The protected model owner supports the existing macOS `sandbox-exec` route and
an optional signed Linux Docker model host. The Linux implementation composes a
second owned container, separate from the target/tool lab, and binds its receipt
to the host, boot, container, guardian process and cgroup. Configuration and the
optional OMP model catalog are frozen; credentials cross a private input pipe
after image/helper verification. The contained checks use simulated Docker and
namespace observations with actual bootstrap/protocol subprocesses. Native tools
still require the owned environment; there is no uncontained host tool fallback.

The development Docker endpoint did not provide usable live verification, and the
operator reported no disposable Linux/SSH host. Existing services and data were
preserved. Missing infrastructure is an unavailable verification result, not a
passing environment scenario or permission to reduce the agreed delivery scope.

A later disposable GitHub-hosted Ubuntu run supplied actual Docker lifecycle
evidence, reproduced watcher loss and verified its container-local fix. It did not use
the operator's development daemon or a separate SSH host. Keep this bounded
execution proof, including the later loopback SSH run, separate from simulated
transport checks and from the newly implemented Linux model-host boundary,
which still needs actual native/container execution evidence.

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
