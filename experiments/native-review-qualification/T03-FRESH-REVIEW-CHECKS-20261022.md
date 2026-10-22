# Fresh native review: failure checks written before implementation

22 October 2026. The decision is to reuse the native runner's presealed
container, `native_api`, `invoke_native`, and original NativeRun/CONNECT allowance.
The simpler alternative is to feed its existing fixed PHP packet to the reviewer;
that cannot review an arbitrary exact claim or a changed evidence revision. This
review-side helper prepares observer-selected bytes, starts one genuinely empty
OpenCode reviewer session through the runner callbacks, and binds the observed
turn to those bytes. It owns no container, route, pool, target or filing action.

The observer writes `SELECTION.json` outside every producer mount. It contains
`claim_id`, `claim_version`, the prepared `source_manifest_sha256`, a `files`
name-to-SHA256 map, six nonempty `roles` lists (`claim`, `conditions`, `source`,
`raw`, `contrary`, `unfinished`), and `source_paths` mapping each flat packet
source name to its original relative source path. The entire source role map
must match `run_root/plan.json`'s original source inventory. The selected
directory contains exactly those files, including failures and contrary raw
results. The observer must verify completeness against its protected capture;
the helper cannot recover evidence the observer omitted.

Call `fresh_review.prepare_packet(observer_root, selection_path,
selection_sha256, run_root / 'handoff' / reviewer_role,
public_bytes=fresh_review.validate_public_bytes)` after the researcher stops.
Use `reviewer_role='reviewer-1'` for the first claim and `reviewer-2` for a
changed claim; both slots must have been sealed before the shared run starts.
Then call `fresh_review.invoke_fresh_review(run_root, packet_dir, pin,
reviewer_role, native_api=..., invoke_native=..., allowance_snapshot=...,
run_active=..., public_bytes=..., independent_check=...)`. The callbacks are
the runner's `tools/native_research.py` functions. `independent_check` is a
host-owned callable that receives completed native tool records and the exact
request, then independently observes the selected clean reviewer target effect
and control. It must return `status=observed`, `observer_origin=host_protected`,
`native_action_reached_clean_target=true`, `source_stable_after=true`, the
selected `tool_line`/`command_sha256`, `review_target_id`,
`review_target_source_sha256`, packet `source_revision`/`evidence_revision`,
and nonempty `effect`/`control` objects. When absent,
the review stays `unfinished`. The helper never accepts a caller-authored JSON
dict as that observation.

The prewritten provider-free setup check is
`python3 experiments/native-review-qualification/check_fresh_review_setup.py`.
Its synthetic material is unrelated to any hidden research case. Stubbed native
callbacks prove call order and fail-closed behavior only. A later real E2E must
save the complete native trace, independent effect/control and shared-pool ledger.

| Failure | Check and required behavior |
| --- | --- |
| Researcher selects or silently drops material | The independent observer selects one exact manifest digest and a directory containing only its claim, conditions, original source, raw results, contrary results and unfinished work. Missing/extra/symlinked or changed bytes fail before publication. The caller, not this helper, must attest observer ownership and completeness against its raw capture. |
| Changed claim/evidence inherits an old verdict | `input_id` binds claim/version, all role names and every file hash. Changed bytes or version change the ID; no previous review is carried forward. |
| Packet path or bind root changes after sealing | Require the already created empty mount root; preserve its device/inode and exact read-only file inventory. Recheck before session creation, before the prompt and after return. |
| Old context or second pool is used | Require empty native reviewer store, create one session and verify empty messages. Take original run/pool identity and counters before and after through the runner callbacks; reject reset, changed deadline/config/IDs, cap exhaustion or inactive run before dispatch. |
| Prepared prompt is mistaken for review | Only `invoke_native` in the fresh session executes the frozen prompt. Record session ID, native turn summary, session usage and pool counters. Failed/incomplete turns stay unfinished. |
| Reviewer merely agrees, reads no evidence, or emits a signed label | Parse its actual native JSONL tool/text events. A review candidate needs packet reads, a completed reviewer-selected executable tool check, a host-owned matching effect and control, and an explicit outcome tied to the exact input ID. Missing evidence stays unfinished. |
| Strong lead is dismissed by relabeling | Prompt requires basis, uncertain trust condition and next check for each proposed dismissal. A rejected/irrelevant lead without an independently examined basis remains unfinished; a partial supported base and missing transition must be retained. |
| Stop or budget arrives before/during review | Stop new dispatch through existing NativeRun/CONNECT. Preserve the packet and turn/usage evidence as unfinished; never assert safety or retry under a new allowance. |
| A model outcome is treated as filing/escalation authority | Return an internal review candidate only. Existing operator, oracle, filing and external-action gates stay separate. |

The real acceptance check is a fresh native model session and independently
captured material effect/control under one accepted allowance, followed by a
changed-input follow-up. The local setup check is only implementation preparation; it
cannot close #159 or establish detection reliability.
