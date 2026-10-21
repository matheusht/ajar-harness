# Prewritten shared-review interface checks

20 October 2026. These checks precede a future T02 integration change. **All runtime
scenarios below are NOT RUN here.** Only source/interface/pin readback is performed.
No implementation, new fixture, provider request, hidden case, Claude or CI.

| ID | Offline failure injection / observation | Required result before later live acceptance |
| --- | --- | --- |
| I01 | Give reviewer a new CONNECT state directory, new capability/config, changed created timestamp or later deadline | Reject the handoff. Same original pool row/config/creation/deadline and NativeRun nonce/manifest/IDs must survive researcher, reviewer and resume. Do not reset counters. |
| I02 | Consume an owned-response tunnel before review, then have a genuinely fresh reviewer attempt the permitted route through the existing pool; separately place the pool at cap | Prior counters remain; accepted/denied actual reviewer route appears in the same ledger and owned responder. A bypass denial is not this test. Cap denial leaves review unfinished, not qualified. |
| I03 | Add/recreate a reviewer after producer sealing, or remove the first producer before global stop | Refuse late identity/binding; missing sealed ID prevents a stopped-success claim. Follow the coordinator-confirmed correction: first ID remains present, idle or stopped, with presealed resume. Never silently rewrite a manifest. |
| I04 | Share researcher HOME/XDG/native store or writable project with reviewer; add old chat, hidden archive or answer material | Reject actual mounts/context sources. Separate initially empty store/session and only exact observer-selected read-only claim material. Do not inspect/open hidden material to prove exclusion; verify allowed roots and their inventories. |
| I05 | Stage packet while reviewer task is already active, replace the bound host directory, or alter a file after freezing | Reject transfer or changed hash. Fixed mount exists before sealing; host publishes complete bytes while reviewer has no native task, verifies inventory before session/prompt, then preserves them. Worker write attempts on a disposable packet copy fail. |
| I06 | Omit a failed/contrary native tool result, substitute a success summary, or present host-issued shell output as reviewer choice | Retain all claim-material raw records/uncertain ranges and assistance attribution. Native metadata/file transfer alone never counts as model examination or causal review. |
| I07 | Use only original files or only edited files, or offer candidate success as original-source behavior | Freeze baseline and actual candidate separately, map normal PHP names, retain exact state/phase/source IDs and independent baseline/control effect. Valid intended edits remain workflow evidence, not an original defect. |
| I08 | Call current note-export prepare_packet with an unselected PHP manifest; supply a fake/self-consistent prior review for v2 | Reject the existing trusted-pin mismatch and unaccepted predecessor. Select a genuine new PHP packet separately. Changed-claim actual preparation requires independently selected immutable prior REQUEST/review pair; its positive branch is currently unavailable. |
| I09 | Stop or expire the run after preflight but before a queued reviewer byte send; also stop after a send already occurred | Final CONNECT guard rejects the unsent write with charged counts retained. Already sent work may settle; preserve independent effects/in-flight usage. No whole-CLI dispatch lock or recall claim. |
| I10 | Reviewer fails/times out midstream; an auxiliary/retry/delegate path is enabled | Stop new work and preserve uncertainty/all session pages. Every enabled route shares the same pool or is effectively disabled. Keyless native cost cannot become an independently observed $0 charge by default. |
| I11 | Owned responder emits a plausible review or tool result | Label mock route/tool mechanics only. #159 review needs an actual reviewer-selected material causal check and independent effect/control; offline responder output cannot pass it. |
| I12 | Reviewer rejects one claim and drops a distinct supported base/lead, or a stop arrives before review | Final internal output updates affected dependents and preserves valid historical bases plus every unreviewed basis/condition/next check. Candidate decisions remain operator-authored in the offline rehearsal; actual reviewer behavior is unqualified. |
| I13 | Resume mutates the source/claim after the frozen review | Preserve actual review/input history; invalidate affected current conclusions. A new changed-claim review needs a presealed fresh context and independently accepted predecessor, not a per-context allowance reset. |
| I14 | Only provider REVOKED exists, stop verification fails, or cleanup loses usage/evidence | Provider marker is admission only. Require exact producer freeze before run REVOKED, otherwise UNSAFE. Preserve traces/SQLite backup and usage after quiescence; remove only nonce-owned IDs and verify absence without unpause/restart. |
| I15 | Serialize a proxy URL/capability, auth header, provider body/private key, home path or hidden hint | Refuse retention, redact before save and preserve private raw evidence under 0700/0600. Packet/receipt includes no secret value. Offline CA public certificate is distinct from its host-only private key. |
| I16 | Resume opens the shared researcher native store while the first process still writes, or stopped-store integrity read fails | Keep reviewer storage separate and enforce one writer on researcher/resume storage. Verify first native process absence and qualified quick_check on a preserved stopped-store copy before resume. Preserve the copy/failing SQL and leave the run unavailable on error. |

Future runnable receipt per case must identify: frozen input/prompt/source hashes,
exact model/image/config/tools, producer/session IDs, actual native commands/results,
shared-ledger before/after/quiescent snapshots, effects/controls, assistance, enforced
versus measured dimensions, stop ordering and exact cleanup. Negative/unknown paths
remain explicit. A passing static pin check does not execute these scenarios.

Static acceptance for these documents only: every referenced source exists and its
hash matches SOURCE-PINS.json; that file distinguishes historical command examples
from current source and frozen receipts; no existing source/evidence is modified;
INTERFACE.md agrees with the inspected NativeRun/CONNECT signatures and current
handoff limitations. Active owner edits require new pin readback before integration.
