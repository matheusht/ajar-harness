# One-pool fresh review after the harmless smoke

20 October 2026. **Prewritten interface only; no integration or model run here.**
T02 owns the managed launcher; T05 owns run lifetime/stop. This adds no service,
pool, runtime code, hidden-case access or review verdict. Source pins identify the
inspected revision, not accepted live behavior. Failure checks are in CHECKS.md.

## Borrow the existing run

The review caller needs these existing host values, not a new allowance API:

| Host-owned value | Required meaning |
| --- | --- |
| Existing NativeRun instance and run-state directory | Started once by T02; native_run.snapshot supplies manifest hash, nonce, exact producer IDs and original monotonic deadline. native_run.active is a preflight check, not the final-send barrier. |
| Already sealed reviewer container ID/binding | Separate HOME/XDG/native store and scratch; same pinned image/effective config/plugin/model, internal route and relay as the researcher. It exists stopped before manifest sealing and NativeRun.start; no late container creation or new NativeRun.start. |
| Existing CONNECT state directory and private route | Same protected tunnel.sqlite3, relay and preconfigured local capability. Retain the pool row's original config and created timestamp, count(tunnels), bytes and created+duration deadline; never reset them for a role. No fabricated pool UUID is required. Keep route/capability values out of packets and receipts. |
| Observer-owned packet directory, mounted read-only | Create its fixed directory/mount before producer sealing; populate it only from frozen harmless-smoke observations after the researcher turn quiesces. Do not replace the bind root. Before any reviewer session or prompt, freeze/check every file hash and thereafter leave those bytes unchanged. The idle reviewer has no native task before publication. |
| Independent app capture and usage snapshots | Existing host application checks over protected original/candidate copies; all native session/message pages before/after each role, plus independently available provider records and in-flight status. Observer/control state stays outside every producer mount. |

The current CONNECT hard dimensions are connections, charged_tunnel_bytes, workers
and time. Charged/admitted encrypted bytes include a chunk reserved before stop
whose final send was then denied; preserve that conservative charge. These totals
do not prove actual delivery: use independent receiver/effect evidence for that.
HTTP requests, tokens and USD are measured or unavailable. A tunnel count is not an
inference count. Native cost is corroboration; missing keyless charge attribution is
unavailable, not zero. The reviewer may be denied at the same pool's bound; that can
test sharing, but it leaves #159 review unfinished.

## Frozen harmless packet

Use ordinary uniquely named files under the existing read-only /handoff mount.
No researcher HOME/database, hidden archive, fixed target, advisory, answer matrix,
test oracle, host control directory, capability or authentication material enters it.

| File | Contents, frozen after the actual harmless researcher turn |
| --- | --- |
| CLAIMS.md | Exact internal claim/version, actual source/config/state conditions, supported partials, proposed extension/disposition and uncertainty. Bind it to the real RESEARCH.md; label any operator restatement as assistance. Do not invent a claim if the turn produced none. |
| RESEARCH.md | The actual harmless research note, unchanged. |
| ORIGINAL-index.php, ORIGINAL-message.php, ORIGINAL-check.php | Byte-identical baseline originals, explicitly mapped to their normal project names. |
| index.php, message.php, check.php | Frozen actual candidate project after the researcher turn. Check which files changed; intentional edits are candidate workflow evidence, never original-target defect proof. |
| RAW-NATIVE-TOOLS.json | Complete claim-material tool inputs/outputs/status/order and source versions, including failures and contrary observations. Preserve missing/truncated ranges explicitly. Exclude provider HTTP bodies/auth, unrelated chat and hidden material. |
| RAW-APP-CHECKS.json | Independent baseline/candidate observations: exact bounded command, phase/state, source hashes, exit/stdout/stderr and actual output/effect. Keep controls and failures, not just selected successes. |
| UNFINISHED.json | Every unreviewed lead's basis, specific uncertain condition, next check and status. Proposed researcher closure remains a proposal. |
| REQUEST.json and PROMPT.txt | Exact file-to-SHA256 map, source/claim/version identities and neutral prompt. Preserve T03's distinction between input identity, prepared history and actual review. Source-map notes explain copying ORIGINAL-* into a separate clean scratch with normal filenames for baseline replay. |

Flat unique names fit the existing staging convention. The current handoff helper
trusts only the old frozen note-export manifest: it cannot accept this new PHP
packet unchanged. T02/coordinator must freeze and independently select its actual
manifest/digest before using an adapted staging call; do not bypass the old pin or
present note-export records as PHP evidence. No PHP packet was fabricated here.

For a changed claim, include immutable PREVIOUS-REQUEST.json and PREVIOUS-REVIEW.json
only after their exact pair is independently accepted for this successor. The
current ACTUAL_PREDECESSORS set is empty. Caller-selected/self-consistent JSON,
old offline transfer receipts and requires_actual_prior_review metadata cannot
substitute. Additional actual changed-claim contexts need their own presealed
fresh store/producer; this minimum single-review call does not qualify that phase.

## Call sequence owned by the existing T02 launcher

1. **Before starting the pool:** create relay, researcher, fresh reviewer and resume
   producers stopped; seal their exact IDs/bindings/mounts once. Reviewer storage
   is separate; researcher and resume share only their intended persistent state.
   Use NativeRun.start once. The offline rehearsal uses its explicitly owned TLS
   responder, test CA and dummy=true; future official-provider work needs separate
   acceptance. A mock request/tool result is not a real model judgment or charge.
2. **Finish the harmless researcher turn:** wait for the actual native invocation
   to finish; retain incomplete/in-flight status on any uncertainty and stop new
   work rather than retry for a pass. Capture all researcher session/message pages,
   app/control observations, actual note/source and current shared-ledger usage.
   Freeze the packet. Keep the pool active and the first producer idle or stopped,
   with its exact sealed ID still present for global verification.
3. **Before review:** compare original pool config/created/deadlines and monotonic
   counters with prior snapshots, plus run manifest/nonce/IDs. Check the observer
   packet hashes and actual reviewer mounts/config. No late manifest edit, pool
   reopen, new deadline or per-review budget. A closed/uncertain run retains the
   packet as unfinished and never dispatches a review.
4. **Create the fresh native session:** in the already sealed reviewer, use
   `opencode api --standalone session.list --param limit=100`, traversing cursors;
   require an empty separate store. Then use `session.create --data` with a neutral
   title, retain the returned data.id, and `session.message.list --param
   sessionID=<id> --param limit=100`, requiring empty data. Use the same isolated
   workdir/config conventions as the existing native runner. Host mount/hash reads
   are preflight assistance; do not preload host-issued session.shell results into
   the actual review context and count them as reviewer-selected checks.
5. **One actual reviewer invocation, only after acceptance:** the existing native
   call shape is `opencode run --standalone --agent build --model
   opencode/deepseek-v4.1-flash-free --format json --session <fresh-id> <prompt>`.
   Run inside the existing reviewer producer with its already configured route.
   The neutral frozen prompt asks it to inspect every claim-material file and hash,
   select/check a material causal link on clean original/candidate copies, preserve
   valid bases and contrary evidence, assess proposed dismissal, retain unfinished
   conditions on stop, and report limits/help/actual usage. No predetermined verdict.
6. **Final-send authority remains T05/CONNECT:** do not hold dispatch_guard around
   the whole CLI or stream. The already integrated CONNECT final byte writes use
   the run guard; queued writes recheck after charging, under the dispatch lock.
   Host active() checks alone do not close the race. Already sent work may settle;
   preserve conservative counts and uncertainty rather than refunding/retrying.
7. **Capture the actual review:** retain the exact native trace and all paginated
   reviewer/child/auxiliary sessions/messages and usage. Verify actual file reads
   and completed reviewer-selected causal/control work, then independently capture
   the bounded app effect outside worker write access. Do not blindly execute an
   arbitrary model shell command on the host. Bind final claims/limits to the exact
   input and effect; an empty result, mock tool call or role label cannot pass #159.
8. **Resume and global stop:** if still authorized/active, verify no first-stage
   OpenCode process remains and preserve a stopped-store copy. Require its qualified
   SQLite PRAGMA quick_check to pass before opening the original session from the
   presealed resume producer; preserve copy/failing SQL and stop on failure. Keep
   one writer per native store; the reviewer has its own store. Retain prior spend.
   Any changed source/claim invalidates affected review and dependents.
   Call request_stop before any separate provider revocation, then NativeRun.close
   and require verified run REVOKED or explicit UNSAFE. After quiescence reconcile
   native/provider usage and in-flight work; only then remove exact owned resources.
   No unpause/restart/new pool to rescue an exhausted run.

Lifecycle correction confirmed by the coordinator: the earlier T02 managed wording
said remove the first container before resume, but Producers.freeze re-inspects
every sealed ID. Keep the first ID present, idle or stopped, use the presealed
resume producer, and remove both only after global verified stop. Literal early
removal needs a separately qualified retirement interface that does not currently
exist. This document changes neither owner's implementation/checks.

This defines only a possible future call. It neither grants provider dispatch nor
qualifies actual #159/#162, hidden-case discovery, authentication, filing or adoption.
