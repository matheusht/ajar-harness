# T02 reviewer packet checks (written before implementation)

21 October 2026. This is the bounded harmless PHP integration of
`experiments/native-review-qualification/T03-T02-SHARED-REVIEW-INTERFACE-20261020/CHECKS.md`
(I01–I16) and `PORTABLE-RESEARCH-ACCEPTANCE.md`. The live route remains denied.

The source change reaches the T02 managed runner, its current source manifest,
the owned offline source workflow and the packet receipt. It must leave the
historical transfer manifest, the T05 controls, cloud qualification lane,
fixture sources and real provider/target routes alone.

| Failure injected or observed | Required check |
| --- | --- |
| Reviewer created after seal, receives researcher store/project, writable packet, or a replaced bind root (I03–I05) | Fixed empty packet root exists before producer creation; reviewer is already sealed with only that root at `/handoff` read-only and separate HOME/XDG/store. Reject changed binding or root identity. |
| Researcher failed, still running, has no actual note, or lacks raw claim-material tool events (I06–I07) | No packet/review session. Preserve unfinished state and observed failure. The candidate is copied only after the native turn returns and source/app checks pass. |
| Tool record is malformed, truncated, too large or contains a secret, host path, unknown source, or unrelated chat (I04, I06, I15) | Refuse packet publication. Keep the private run receipt; never transfer questionable bytes. Include every bounded tool part, including failed/contrary parts, with order and attribution. |
| Candidate substituted for original, output classification substituted for raw app effect, or unsupported claim invented (I06–I08, I12) | Packet binds byte-identical original/candidate PHP, unchanged actual RESEARCH.md, exact baseline/candidate commands and outputs, and clearly labels any operator-authored claim/unfinished fields. No synthetic prior review. |
| Packet file changes after hash freeze, hidden/extra file appears, or prompt/request lacks a digest (I05, I08, I13) | Verify exact inventory, hashes and fixed directory identity before reviewer session and again after run. Review remains unfinished on any drift. |
| Successful cleanup removes the temporary bind root (I14) | Retain an independently checked, private receipt copy with the same file hashes outside every producer mount. |
| Pool/NativeRun is replaced, deadline extended, cap exhausted, or stop arrives after preflight (I01–I02, I09–I10) | Compare original run nonce/manifest/IDs/deadline and original CONNECT config/creation/deadline with monotonic counters; use the existing pool. A closed or capped pool leaves review unfinished. T05 final-send guard remains authoritative. |
| Reviewer store already has a session, does not read packet or run a material control, or the owned responder emits plausible prose/tool calls (I04, I11–I12) | Require empty store before session.create, empty messages before prompt, capture actual reviewer tools and independent app effect. Mark mock-only execution unqualified for #159 even if the offline route works. |
| Resume or cleanup destroys first sealed ID or review evidence (I13–I16) | Keep first ID until global verified stop, recheck packet/source, retain shared ledger and usage snapshots, then perform existing stop/cleanup checks. |

Acceptance for this change: the owned synthetic offline workflow produces a
repeatable redacted receipt showing packet creation, fixed read-only mount,
hash drift rejection and live pre-output denial. Source checks and current
manifest pass. This is preparation, not #158/#159 native qualification.
