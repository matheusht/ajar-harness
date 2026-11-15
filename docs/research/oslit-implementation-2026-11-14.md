# OSLit implementation and evidence

The operator authorized the complete [M0–M6 plan](oslit-engineering-plan-2026-11-14.md)
on 14 November 2026: implement autonomously, reuse native tools, enforce boundaries,
verify real workflows, and leave the fresh-target research test to the operator.
This record separates implementation from observed integration and research results.

## Delivery state

Read the [current M0–M6 status](../wiki/oslit-v2-delivery-2026-11-14.md#implementation-and-remaining-verification)
and [operator handoff](../agents/fresh-target-handoff.md) for implemented behavior,
setup and remaining verification. Both native runtimes have joined Linux source
workflow evidence with controlled provider replies. Provider attempts are now
journaled; real billing receipts remain unavailable. The operator owns the later
fresh-target and full-day tests. No new hosted CI is requested for this pass.

The entries below preserve earlier checkpoints; their original counts and
limitations do not describe today's implementation. In particular, the early M1
`run`/`resume` placeholder was subsequently connected to the real runner, and the
Linux startup gap was superseded by the November 15 integrated results.

## Starting point and ownership

The implementation starts from `89bcede2c1e62573767017251e8734f211fa3573`, the head
of [draft PR 209](https://github.com/matheusht/redteam-harness/pull/209). Existing
planning edits belong to this assignment and are preserved. The implementation
branch is `codex/oslit-team-contract`; dependent work will retain this ancestry.
The coordinator owns integration, checks and publication. Writers use separate
branches/worktrees. The initial runtime, contract and environment M0 investigations were read-only.
Subsequent implementation used bounded writers and independently reviewed units.

The current [engineering workflow PR playbook](https://github.com/matheusht/engineering-workflow/blob/main/skills/pstack/poteto-mode/playbooks/opening-a-pr.md)
requires verified checkpoint commits, independent review of the complete patch,
ready PR publication and exact remote readback. Opening a PR does not grant merge
authority. The installed upstream playbook differs; the user-selected adapted
workflow governs this assignment. No shared worktree reset is permitted.

## Decisions and evidence

- Retain the public entrypoint and the v1 route. New v2 engagements use one
  append-only journal; they do not invoke the old driver/continuation pair as a
  second team scheduler. This follows the two prior architecture candidates and
  their cross-review, updated for the operator's Codex/OMP correction.
- Worker identity comes from an isolated host-owned channel. A submitted role,
  copied assignment ID or native peer message does not grant authority. Runtime
  and environment observations remain separate from controller assertions.
- The same authority and allowance survive replacement and restart. Overall
  expiry is optional; worker leases remain short and renewable. Token/cost caps
  are unsupported until complete observation and enforcement are demonstrated.
- Real Docker probes timed out on the development Mac. No daemon restart or
  existing-resource cleanup was attempted. The user confirmed no disposable
  Linux/SSH host was available at M0. The later hosted loopback SSH check below
  supplies bounded transport evidence; a separate remote host remains unavailable.
- The development volume has approximately 4.6 GiB free. No new VM or large image
  was installed. Existing runtimes and user data remain protected.

## Hosted environment verification

The later [actual Docker workflow](../../evals/native-qualification/team-evidence/real-docker-20261114/README.md)
uses a disposable GitHub-hosted Ubuntu runner. It provides real Docker execution
without changing the unavailable development daemon or requiring an operator SSH
host. The lifecycle run at `41a0be16` passed 21 checks, including immutable input,
unprivileged execution, network isolation, artifact readback, child revocation and
cleanup. This does not establish the joined native/controller workflow.

A failure-first watcher-loss scenario at `fd8674b1` then reproduced a lifetime
defect: killing the host watcher left its container running beyond the lease.
The fixture cleaned up all owned resources. Container-local enforcement then
passed this unchanged case at `3d0df8a2`: 25 lifecycle checks passed, the container
was observed stopped 0.1657 seconds after watcher loss, and all cleanup readbacks
were clean. A separate actual guardian scenario passed 30 checks for PID 1,
worker separation, child reaping, private control and expiry. Its
[manifest](../../evals/native-qualification/team-evidence/real-docker-20261114/guardian-manifest.json)
preserves exact source hashes and hosted receipts.

The later actual loopback SSH run at `1ec66d6d` passed 26 checks on the same
disposable host, including a killed SSH client, stopped container and exact
resource/listener cleanup. Its
[manifest](../../evals/native-qualification/team-evidence/real-docker-20261114/ssh-manifest.json)
retains the startup failure and corrected fixture account policy. This verifies
OpenSSH transport composition; it does not replace a separate remote host or
network-partition test.
The [saved manifest](../../evals/native-qualification/team-evidence/real-docker-20261114/hosted-manifest.json)
records exact source hashes and run links.

The Linux model-host implementation at `cceac74c` privately composes a separate
owned container with signed limits, exact process/cgroup receipts, private
credential delivery, frozen configuration and an optional OMP model catalog.
Independent replay passed all 14
[contained scenario families](../../evals/native-qualification/team-evidence/m2-linux-model-host-20261114/README.md).
Those scenarios simulate Docker and namespace facts; actual Linux native startup,
network containment and recovery remain for the hosted native workflow.

## Historical verification checkpoints

These entries describe their original checked revisions. Later source, local native
checks and integration evidence are linked from the delivery state above.

M0 delivers [ADR 0014](../decisions/0014-native-engagement-team.md),
the [v2 contract](oslit-v2-contract-2026-11-14.md),
[runtime grounding](oslit-v2-runtime-grounding-2026-11-14.md),
[environment grounding](oslit-v2-environment-grounding-2026-11-14.md), and
[failure-first scenarios](../../evals/native-qualification/TEAM-ENGAGEMENT-SCENARIOS.md).
Independent document review found and corrected a stale assignment note and a
missing E05 session/update scenario. The follow-up review found no remaining
concrete issue. This is design review, not runtime qualification.

Codex 0.166.0 and OMP 18.20.0 passed control-only session creation/readback/idle
interrupt probes with networking denied by the macOS sandbox. Saved
[results and hashes](../../evals/native-qualification/team-evidence/m0-20261114/manifest.json)
were independently checked against their observations. No model prompt was sent.
Native tool isolation, active revocation, provider execution and session-content
recovery remain unverified. OMP's installed SDK source is older than its binary;
the implementation must pin the matching SDK before using native tool factories.

M0 structural conformance passed **900 checks, zero failures** using
`/tmp/pr209-conformance-venv/bin/python tools/check-conformance.py`. The log is
`/tmp/oslit-implementation/m0-conformance.log`. `git diff --check` and the root
instruction mirror passed. Code cleanup does not apply to this documentation
checkpoint; no production code changed.

M1 input validation passed 61 local failure-first cases. The journal/facade passed
six composite team scenarios with simulated workers, and the preserved v1 driver
passed its 18 existing cases. Independent fixed-snapshot review then found eight
controller defects in ownership, directory separation, crash publication, receipt
identity/recovery, status bounds and retries. A separate eight-scenario E2E check
failed on that snapshot before fixes and passed afterward. Its crash case exits an
owned subprocess immediately after the event-directory fsync and reopens the
journal through the public CLI. Follow-up review added a ninth scenario: a late
receipt must preserve previously observed usage before releasing its reservation.
It failed before the fix and passed afterward. These results establish local controller behavior,
not live runtime containment or provider execution. At that M1 checkpoint, run/resume was explicitly blocked pending
runtime/environment integration; it is not the current facade state.

Failure scenarios are specified before implementation. New checks exercise the
public CLI or the actual runtime/environment boundary and save commands, inputs,
versions, expected outcomes, observed results and cleanup. Simulated worker events
are labeled and cannot establish live runtime isolation, provider behavior or
research success. Existing historical artifacts are not rewritten or regraded.

The final report must identify implemented behavior, local checks, real native
and provider observations, remote observations, hosted CI, unfinished milestones,
and the operator's research acceptance separately. Missing infrastructure is a
delivery limit, not a passing scenario.
