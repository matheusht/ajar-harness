# OSLit implementation and evidence

The operator authorized the complete [M0–M6 plan](oslit-engineering-plan-2026-11-14.md)
on 14 November 2026: implement autonomously, reuse native tools, enforce boundaries,
verify real workflows, and leave the fresh-target research test to the operator.
This record separates implementation from observed integration and research results.

## Delivery state

| Unit | State | Required evidence |
| --- | --- | --- |
| M0 contracts and failure cases | Complete design checkpoint | ADR 0014, concrete v2 contract, native API findings and failure-first scenarios below |
| M1 one state owner | Not started | Signed authority, one journal, public workflow, preserved v1 readers |
| M2 runtimes and team | Not started | Codex/OMP control and tools, authenticated workers, queue and revocation |
| M3 environments | Not started | Source/binary/application/combined setup; local and SSH resource enforcement |
| M4 research evidence and recovery | Not started | Independent measurement review, review obligations, replacement and closeout |
| M5 accounting and long operation | Not started | Shared accounting, restart, no implicit deadline and sustained harmless soak |
| M6 delivery | Not started | Install/inspect/examples/guide/export/methodology/CI and operator handoff |
| Fresh-target research acceptance | Operator-owned; not run | Independent positive result and comparison under the agreed conditions |

## Starting point and ownership

The implementation starts from `89bcede2c1e62573767017251e8734f211fa3573`, the head
of [draft PR 209](https://github.com/matheusht/redteam-harness/pull/209). Existing
planning edits belong to this assignment and are preserved. The implementation
branch is `codex/oslit-team-contract`; dependent work will retain this ancestry.
The coordinator owns integration, checks and publication. Writers use separate
branches/worktrees. Runtime, contract and environment M0 investigations are
read-only and do not change the shared source tree.

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
  Linux/SSH host is currently available. SSH integration evidence therefore
  remains unavailable; code and local checks can proceed independently.
- The development volume has approximately 4.6 GiB free. No new VM or large image
  was installed. Existing runtimes and user data remain protected.

## Verification record

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

Failure scenarios are specified before implementation. New checks exercise the
public CLI or the actual runtime/environment boundary and save commands, inputs,
versions, expected outcomes, observed results and cleanup. Simulated worker events
are labeled and cannot establish live runtime isolation, provider behavior or
research success. Existing historical artifacts are not rewritten or regraded.

The final report must identify implemented behavior, local checks, real native
and provider observations, remote observations, hosted CI, unfinished milestones,
and the operator's research acceptance separately. Missing infrastructure is a
delivery limit, not a passing scenario.
