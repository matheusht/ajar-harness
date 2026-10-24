# Native handoff preflight: failure checks before implementation

20 October 2026. Own only this new directory; do not modify T02/T05/#85 source,
existing packets/receipts, global config or an active runtime. Reuse existing
claim/evidence files. No hidden case, provider/model inference, hosted CI, new
application fixture or engagement. This is one necessary offline native-context
preflight; it cannot accept #159/#162 or authorize #160.

Current T02 aggregate-app receipt is unavailable. The only allowed OpenCode calls
are local metadata/session creation and a direct native session.shell file-read/
read-only-mount check. NetworkMode=none and no credential/proxy/host-control mount
must make inference impossible. Direct session.shell does not test model tool
selection/permission preparation or a fresh LLM's actual input examination.

| Failure | Check and required outcome |
| --- | --- |
| Existing data or another owner's edits are overwritten | New output only, ephemeral owned workspace and packet copy. Existing sources/packets are hashed, never modified. Exact owned ID/nonce cleanup only. |
| Wrong image/config/plugin used | Require cached official V2 image ID from HANDOFF.json, pull=never, exact observed config and local plugin hashes. No silent fallback/derived image or package install. |
| Research history is inherited | Empty isolated HOME/XDG/native store; actual session.list must initially be empty. Create one local session, require one exact new ID and zero messages before checks. This proves initial store state, not full future model-context independence. |
| Observer oracle/old chats enter reviewer mount | Mount only an ephemeral copy of packets/v1 at /handoff read-only, new private workspace, read-only config/plugin. No repo/root/home/host socket, expected-outcome matrix, previous session store or hidden input mount. Inspect actual mounts, network, user, caps and security options. |
| File reads are only printed claims | Through actual local session.shell, hash all seven frozen packet files. Inspect completed output fields in native message records, not the user command text. Match host-computed hashes. This is direct native API execution without a model. |
| Mount protection is assumed | Attempt append to the disposable packet copy through native session.shell; require a read-only error marker and unchanged host-side copy/original hashes. Never attempt mutation of original evidence. |
| Fixture runtime is assumed usable | Check command -v python3 in the exact image. If missing, record material replay unavailable; do not rewrite the app, install a runtime, create a service or substitute a host-only replay for reviewer execution. Do not run the application while the aggregate gate is closed. |
| Input/version binding is partial | Freeze v1, v2, printed-success and strong-lead reviewer-visible file/source hashes in HANDOFF.json. Hash-only verification cannot claim a reviewer examined them. v2 later needs the actual v1 review hash as a separate immutable attachment. No pre-authored outcome may enter the reviewer inputs. |
| Raw paths/secrets enter durable evidence | Exact command/stdout/stderr records stay in a new private 0700 directory with 0600 file. Repository copy replaces the owned temporary root/home prefix with <RUN>/<HOME>. No environment/auth dump; config is owned synthetic pinned content. |
| Cleanup or failure disappears | Always stop/remove only the ownership-verified created container, inspect its absence and verify owned temporary state removal. Preserve failed/unavailable receipt and input hashes. No rerun to hide a failure. |
| Offline context becomes a native reviewer claim | Session identity, file reads and mount state are offline observations only. Actual fresh inference inputs/outputs, causal replay, shared allowance, changed-claim review, stopping and false-proof decisions remain NOT RUN. |

Expected local context result: exact offline native session identity and read-only
handoff inputs, clean source/cleanup and a separate available/unavailable interpreter
result. A missing interpreter is a material handoff blocker, not a successful review.
The independent original-source effect/control checks are the existing saved nine-call
CLI and T06 captures; this run must not relabel them as model/reviewer execution.

Capture amendment after first offline attempt: session.shell can return exit zero
with empty stdout. Treat that as no response body and inspect completed native message
outputs for execution evidence. An empty body alone neither fails execution nor proves
it. The first attempt is retained with its exact pre-fix runner/checks/handoff source.
