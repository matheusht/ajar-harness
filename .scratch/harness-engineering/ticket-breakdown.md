# Approved ticket breakdown

Companion to the [specification](spec.md). The operator [approved all six tickets and the test boundaries on 2026-09-05](https://github.com/matheusht/redteam-harness/issues/105#issuecomment-5553859692). Publication identifiers are recorded in the [handoff](../../docs/research/harness-engineering-2026-09-05/handoff.md). No implementation has started.

1. **[Repair active engineering guidance](issues/01-repair-active-guidance.md)**
   - **Blocked by:** none.
   - **Delivers:** working current setup references and status navigation, with mirrored instructions, history and frozen pins preserved.
2. **[Reject unsupported Q02 comparison inputs](issues/02-q02-admission.md)**
   - **Blocked by:** none.
   - **Delivers:** a public comparison command that rejects malformed input, keeps missing evidence inconclusive and applies its existing limited rule only to admitted evidence.
3. **[Account for every assigned offline comparison case](issues/03-offline-study-account.md)**
   - **Blocked by:** none.
   - **Delivers:** a deterministic report over a frozen roster and normalized observations, including failed/empty cases, accounted human effort and metric-specific completeness limits.
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

The approved test boundaries are existing documentation conformance, the public Q02 command, an offline study-report command and a read-only inspector. Both experiment packets reuse the study-report boundary. There is no prefactoring or framework ticket.

The reviewed version is preserved at commit `d150f8d04fd902b48f6a5914880637d39e29a2d1`. Publication preserves the approved scope, using native parent/blocking relationships. Do not close the specification or lift prior operational holds merely because planning is complete.
