# Proposed ticket breakdown

Review companion to the [specification](spec.md). All six tickets are drafts awaiting approval; none is published as `ready-for-agent`. No implementation has started.

1. **[Repair active engineering guidance](issues/01-repair-active-guidance.md)**
   - **Blocked by:** none.
   - **Delivers:** working current setup references and status navigation, with mirrored instructions, history and frozen pins preserved.
2. **[Reject unsupported Q02 comparison inputs](issues/02-q02-admission.md)**
   - **Blocked by:** none.
   - **Delivers:** a public comparison command that rejects malformed input, keeps missing evidence inconclusive and applies its existing limited rule only to admitted evidence.
3. **[Account for every assigned offline comparison case](issues/03-offline-study-account.md)**
   - **Blocked by:** none.
   - **Delivers:** a deterministic report over a frozen roster and attributable observations, including failed/empty cases, complete human effort and unknown cost.
4. **[Explain evidence state through a read-only reconstruction summary](issues/04-read-only-reconstruction.md)**
   - **Blocked by:** none.
   - **Delivers:** one inspection that explains source and claim revisions, reviews, current reports, context provenance and outside outcomes without changing source records.
5. **[Prepare the benign recovery comparison packet](issues/05-recovery-comparison-packet.md)**
   - **Blocked by:** ticket 3, because its synthetic examples must validate through the shared study-account boundary.
   - **Delivers:** document versions, correction/loss cases, expected accounts and a pinned comparison protocol. No runtime or provider adapter is built.
6. **[Prepare the task-local message-board comparison packet](issues/06-message-board-comparison-packet.md)**
   - **Blocked by:** ticket 3, for complete and comparable workload accounting.
   - **Delivers:** three document packets, serial/direct/board arrangements, bounded notices and an isolated answer key. No board service or model run is included.

Tickets 1–4 can proceed independently. Tickets 5 and 6 can proceed independently after ticket 3. Q02 is not a prerequisite for the general comparison account: its frozen prompt-ablation rule has a different purpose. The reconstruction implementation does not need a study report to expose facts already present.

The proposed test boundaries are existing documentation conformance, the public Q02 command, an offline study-report command and a read-only inspector. Both experiment packets reuse the study-report boundary. There is no prefactoring or framework ticket.

On approval, publish the spec and each ticket with native parent/blocking relationships. Preserve this review version and map to the assigned tracker identifiers. Do not alter or close an unrelated parent or lift prior operational holds.
