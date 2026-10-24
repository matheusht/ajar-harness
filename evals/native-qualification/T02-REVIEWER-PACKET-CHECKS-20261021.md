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
| Researcher failed, still running, has no actual note, or lacks raw claim-material tool events (I06–I07) | No packet/review session. Preserve unfinished state and observed failure. Take the candidate snapshot only after the native turn returns and the first container stops; publish it only after source and app checks pass. |
| A researcher-spawned background shell survives the OpenCode `idle_top` check and changes PHP during host replay or packet copy | Capture native usage, stop the first container, verify Docker reports it stopped, then take a host-owned candidate snapshot. Replay and publish from that snapshot; a failed stop leaves the reviewer unstarted. |
| Baseline or candidate bytes change after their app-check hashes were recorded, or during the independent PHP replay | Hash each replay input before and after the PHP commands; reject any mismatch. At packet freeze, compare the actual original and candidate bytes against the separate baseline and candidate `app_checks.source_sha256` maps before writing a packet file. A controlled mutation must leave the packet empty and reviewer unstarted. |
| Tool record is malformed, truncated, too large or contains a secret, host path, unknown source, or unrelated chat (I04, I06, I15) | Refuse packet publication. Keep the private run receipt; never transfer questionable bytes. Include every bounded tool part, including failed/contrary parts, with order and attribution. |
| Candidate substituted for original, output classification substituted for raw app effect, or unsupported claim invented (I06–I08, I12) | Packet binds byte-identical original/candidate PHP, unchanged actual RESEARCH.md, exact baseline/candidate commands and outputs, and clearly labels any operator-authored claim/unfinished fields. No synthetic prior review. |
| Packet file changes after hash freeze, hidden/extra file appears, or prompt/request lacks a digest (I05, I08, I13) | Verify exact inventory, hashes and fixed directory identity before reviewer session and again after run. Review remains unfinished on any drift. |
| The read-only `/handoff` directory remains mode 0555 after reviewer exit, so `shutil.rmtree(work)` raises `PermissionError` and leaves temporary work behind (I14) | Keep `/handoff` read-only throughout review. Only after verified container cleanup, restore owner write permission on the owned bind root, remove temporary work, and retain an independently checked private receipt copy outside that work tree. Exercise this cleanup with an owned frozen packet and check that only the temporary root disappears. |
| Pool/NativeRun is replaced, deadline extended, cap exhausted, or stop arrives after preflight (I01–I02, I09–I10) | Compare original run nonce/manifest/IDs/deadline and original CONNECT config/creation/deadline with monotonic counters; use the existing pool. A closed or capped pool leaves review unfinished. T05 final-send guard remains authoritative. |
| Reviewer store already has a session, does not read packet or run a material control, or the owned responder emits plausible prose/tool calls (I04, I11–I12) | Require empty store before session.create, empty messages before prompt, capture actual reviewer tools and independent app effect. Mark mock-only execution unqualified for #159 even if the offline route works. |
| Resume or cleanup destroys first sealed ID or review evidence (I13–I16) | Keep first ID until global verified stop, recheck packet/source, retain shared ledger and usage snapshots, then perform existing stop/cleanup checks. |

Acceptance for this change: the owned synthetic offline workflow produces a
repeatable redacted receipt showing packet creation, fixed read-only mount,
hash drift and changed-input rejection before publication, and live pre-output
denial. Source checks and the current manifest pass. This is preparation, not
#158/#159 native qualification.
