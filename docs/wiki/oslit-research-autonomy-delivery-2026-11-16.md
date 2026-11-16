# Research autonomy delivery — 16 November 2026

The autonomy implementation is complete in the candidate branch. Final native
verification is in progress at `5df9010bb1a756e232b2011258965fb711212a24`;
PR publication is authorized and pending. The operator closed the preceding
engineering plan, then approved the autonomy plan and explicitly requested full
E2E verification, dependency repair, rebuilt runtime images and implementation
fixes. Research acceptance remains a separate operator-owned step.

The candidate adds research autonomy within initial signed authority, native helpers,
recoverable shared research context and an active versioned knowledge library.
Historical engagements keep their original authority and frozen guidance. The
[verification record](../../evals/native-qualification/team-evidence/research-autonomy-20261116/README.md)
retains repeatable scenarios and distinguishes actual runtime execution from
simulated judgments, provider responses and environments.

## Current workflow evidence

| Execution | Observed outcome |
| --- | --- |
| Local full conformance | [900 checks, zero failures](../../evals/native-qualification/team-evidence/research-autonomy-20261116/conformance-result.json) on `5df9010b`, using the pinned dependencies. This is local verification. |
| Current hosted workflow | [Run 43915587129](https://github.com/matheusht/redteam-harness/actions/runs/43915587129), at `5df9010b`, passed its Docker job and both direct native suites. Public workflow qualification remains open for the reasons below. |
| Codex direct native workflow | All 42 checks passed at `5df9010b`, including helper activity, selected reference/version handling, usage, recovery, export and cleanup, with scripted provider responses. |
| OMP direct native workflow | All 42 checks passed at `5df9010b`, with normal bootstrap and the corrected signed fixture capacity. The same bounded helper/reference/usage/recovery/export/cleanup mechanics passed. |
| Public CLI → Runner → lead/helper → fresh reviewer → reviewed dry closure → export/cleanup | Codex reached accepted review, closed state and verified cleanup, but an unclassified partial provider upload failed the strict error check. OMP remains blocked by fixture continuation/lane handling. Neither public workflow is qualified by this run. A later run must demonstrate the repaired acceptance checks; the current failure is preserved. |
| Live OMP provider | [One actual source-read turn](../../evals/native-qualification/team-evidence/research-autonomy-20261116/LIVE-OMP-SOURCE-READ.md) completed using OMP 18.20.0, Mistral `mistral-small-2603` and an owned Docker tool lab, with verified cleanup. It did not exercise the full public Runner/team workflow. |
| Live Codex provider | External authentication succeeded. The [repaired executor registration](../../evals/native-qualification/team-evidence/research-autonomy-20261116/codex-external-auth-order/README.md) remained healthy through thread creation, which then failed at an unavailable sandbox namespace in the Mac Docker tool lab. No model turn ran; cleanup was verified. |

The Linux native fixtures use actual pinned runtimes and protected containers with
scripted provider responses. Reviewed dry closure is bounded to an owned harmless
fixture. These checks establish workflow mechanics. The operator's fresh-target
investigation, fair native-agent comparison and useful multiday research have not
been run here.

## All implementation areas

| Area | Implemented capability | Verification and remaining limits |
| --- | --- | --- |
| M0 — contracts | Signed inputs/profiles, identities, access modes, policy selection and optional research limits; historical signatures retain their meaning. | The signed-contract suite passed 84 cases, including public Codex/OMP schema declarations and credential-value refusals. Joined results apply only to their recorded revision. |
| M1 — state and execution | One controller/journal, reservations, replay, Runner, public facade and context reconstruction from shared records. | Local recovery and joined native recovery cover their saved conditions. Sustained operation remains unverified. |
| M2 — runtimes and teams | Pinned Codex/OMP sessions, protected tools, retained specialists, parent-owned helpers, shared usage and fresh independent reviewers. | Native results above distinguish scripted mechanics from live model behavior. Helpers cannot independently review their parent's work. |
| M3 — environments | Source/binary/application/combined access; permitted acquisition, setup/repair, local/SSH Docker, accounts, owned reset and disposable lab-state cleanup. | Actual Docker, loopback SSH and application-reset checks; six owned local TLS acquisition checks. Broader joined access combinations and loss/reconnection to a separate remote SSH host remain verification gaps. |
| M4 — evidence and review | Protected observations, control/replay provenance, independent review, patch checks, reviewed closure and bounded lab-artifact ownership. New scopes remove the generic escalation order and universal scientific checklists. | Local evidence/review scenarios and the joined dry-closure fixture. Broader physical lab-state combinations and model-directed scientific adequacy need their own evidence. |
| M5 — continuation and usage | Renewable leases, optional total invocation/elapsed-parent-time caps, restart/reconstruction, provider-attempt journal, tokens/estimates, helper accounting, operator stop and uncertain-outcome recovery. | Saved recovery/accounting scenarios exercise mechanics. Multiday operation remains unverified. Real billing receipts and hard dollar/token caps are unsupported. |
| M6 — delivery | Installer, preflight, public run/resume/status/stop/export, examples, frozen reusable instructions, guides, CI and preserved historical callers. | Dependencies installed, runtime images rebuilt and current local conformance passed. Both current direct native suites passed; public workflow qualification and PR publication are pending. Merge/adoption remain separate. |

## Research-autonomy changes

[Decision 0016](../decisions/0016-research-autonomy.md) selects the new versioned
policy. Strategy challenges remain visible without excluding otherwise permitted
resources or imposing a fixed replacement countdown. Independent reviewers assess
the actual control and reproduction; code enforces permissions, identity, provenance
and integrity. Total invocation and duration caps apply only when selected by the
operator. Machine capacity, renewable leases and stop/recovery controls remain.

Ordinary notes, source links, board search and updates preserve corrected assumptions,
partial effects and unfinished work across lost contexts. Native helpers inherit the
parent's authenticated authority, and their usage belongs to its accounting. Separate
fresh workers remain required for independent review.

The [knowledge library](../agents/knowledge-library.md) provides immutable selected
versions, search/read, authorized public fetch and workspace materialization. Retention
failure is explicit while otherwise permitted content remains usable. Experimental
techniques are available immediately; recommendation requires independent changed-case
transfer and a meaningful counterexample. Withdrawal preserves prior bytes and records.
The [host workflow](../../evals/native-qualification/team-evidence/research-autonomy-20261116/knowledge-host-result.json)
passed 14 checks using real signed controllers/journals with simulated fetch and
environments. Native reference reads do not establish native execution of that whole
technique-evaluation workflow.

## Repairs found during verification

This pass added the supported Mistral credential binding, restored lossless binary
reads, corrected strict current export projections while preserving the observed
historical shape, and admitted value-free public JSON-schema declarations without
admitting credential values. Failure scenarios preceded product repairs. Fixture
corrections separately repaired signed setup, event waiting, complete review-packet
reads and continuation routing.

The [Codex authentication repair](../../evals/native-qualification/team-evidence/research-autonomy-20261116/codex-external-auth-order/README.md)
keeps effective-configuration validation before login and registers the executor
after authentication, which had closed the earlier connection. The exact changed
production source retained a healthy bridge through thread creation; the separate
Mac Docker namespace prerequisite remains unresolved.

The [bridge repair](../../evals/native-qualification/team-evidence/research-autonomy-20261116/proxy-backpressure/README.md)
preserves bytes when a consumer pauses. Before the fix, an actual local IPC scenario
received only 4096 of 204800 bytes. Afterwards it received every byte with the expected
digest; revocation still interrupted a blocked stream promptly. All 10 existing
proxy/TLS/policy cases passed. Queue/frame bounds and signed authority were unchanged.

OMP caches its native addon and SQLite state per session. Actual ARM measurements
showed why 128 and 256 MiB workspaces were insufficient for the parent/helper workload;
512 MiB completed the ARM comparison. The later actual AMD run exhausted 512 MiB
before the second helper. The current owned AMD fixture therefore signs 1 GiB of
model workspace and 1.5 GiB of memory; CPU 2 and 128-process limits remain. The pinned
AMD package size informed that next capacity choice. The current direct OMP suite
passed all 42 checks with normal bootstrap and these signed limits. Codex's signed
capacity is unchanged. This adjusts test inputs, not product containment or
historical contracts.

A later full TLS discriminator transferred all 652,488 fragmented bytes through the
actual proxy/relay to an owned TLS receiver after a consumer pause. Explicit
revocation during a separate upload produced partial EOF and an unknown request
receipt. The [result](../../evals/native-qualification/team-evidence/research-autonomy-20261116/proxy-backpressure/network-upload.json)
shows why cancellation needs separate evidence. It does not retroactively explain
the current hosted partial upload. A new fixture must tie cancellation to a verified
authority-ending event inside that exact request-read interval; active-authority
truncation and malformed complete requests remain failures.

## Evidence boundary

Use the [saved scenarios](../../evals/native-qualification/team-evidence/research-autonomy-20261116/SCENARIOS.md),
source hashes and repeat commands in the verification record. Historical failures
remain retained. Full public mechanics, a live source-read smoke, physical environment
coverage, sustained operation and research benefit are different claims; this page
reports only the execution evidence supporting each.
