# T02 direct native research route: checks frozen before implementation

Decision: use the existing OpenCode V2 image, sealed Docker producers, one
`NativeRun`/CONNECT pool, and standard `opencode api` / `opencode run`. The
target input is a caller-selected source tree and brief. The simpler alternative,
changing `opencode_v2_managed_owned.py`, keeps its fixed PHP fixture, generated
answer, and dummy provider coupled to every launch; it cannot be the direct
research route. `tools/docker_session_runtime.py` is also unsuitable as the
launcher because it deliberately makes `/workspace` read-only.

Interface: `tools/native_research.py prepare` freezes source/brief and explicit
model, image, relay, and scope digests in a private run root. It does not verify
the scope's human signature or create approval. `start` owns the
foreground native run and its already sealed relay, researcher, two fresh
reviewers, resume, and separate original/review target containers. Research
and each reviewer sit on distinct internal networks; only the relay is shared.
The eight-producer cap permits one initial review and one changed-claim fresh
review. Later reviews remain unfinished until a new bounded run is prepared.
`research` creates the first empty native session and sends the frozen brief;
`resume` sends one private prompt to the exact existing session while
that owner is alive. `stop` closes dispatch, waits for exact producer freeze,
and cleans only owned IDs. The reviewer has a separate native store and a
read-only `/handoff` and `/workspace/original` mount; it receives no researcher
history by default. The public `review` route invokes a fresh reviewer, but its
assessment stays `unfinished` until a target-owned independent checker observes
material effect and control. The current runner reports
`protected_capture=unavailable` for native target requests and effects.

| Failure | Required check and outcome |
| --- | --- |
| Missing scope, mutable/ambiguous source or brief, symlink, overlapping output, hidden answer accidentally selected | Reject invalid source paths and hash each regular input. The caller owns source selection, hidden-answer exclusion, signed scope, and engagement authority; the runner does not establish these semantics. |
| Unpinned or changed OpenCode image, architecture, executable version, model, relay, CA, or stop controls | Reject before model dispatch; inspect exact image ID and environment, compare source/binary digests, then run `opencode --version` and inspect loaded agents/config/tools in the active internal container before any model turn. No fallback model or global user config. This is not a `--network none` version check. |
| Operator or provider credential reaches a researcher mount, environment, image config, native config, or report | Reject credential-like environment/config fields; never pass host home, Docker socket, keys, or observer output. The supported route is the keyless OpenCode free model only; no host key is needed or copied. |
| Authenticated target returns or requires a password/cookie visible to the agent | The runner rejects credential-like prompt text but cannot sanitize OpenCode's persistent native database after the agent sees tool output. Authenticated Kanboard work needs a qualified host-owned credential-injection and protected observer path before live #158 qualification. The protected trace's hashes do not redact the native store. |
| Live launch without a fresh operator approval bound to scope/model/image/route and finite cap | Refuse before creating resources. Require a private human-authored JSON assertion with exact plan/scope pins, `approved_by`, UTC `approved_at`, and UTC `expires_at` no later than 24 hours after approval. This is not a cryptographic signature or an independent scope-signature check. Preparation and status are provider-free. No live invocation is authorized by this change. |
| Researcher reaches host, observer, external network, or another producer outside the fixed CONNECT relay | Preseal one internal network and a dual-homed relay; researcher/reviewer/resume attach only internally with isolated DNS. Inspect actual networks/mounts/env before dispatch. Full enabled-route proof remains a separate qualification check. |
| Resume changes source, model, session, pool, deadline, or allowance | Compare the original run ID, sealed IDs, native state, container bindings and pool identity; use the same native session and shared writable research workspace. No second `NativeRun`. |
| Native `opencode run` dies, times out, returns no matching session ACK, or is interrupted after dispatch | Write a durable before-dispatch identity first. Report `unknown_effect`, block implicit retry, and require independent host/application inspection. Never infer no effect from a missing ACK. |
| Owner dies, stop races dispatch, a producer is still running, or Docker cannot prove absence | NativeRun stop owner closes admission and freezes exact IDs. The public `recover-start` command handles only created-stopped resources before activation or terminal verified-stop state after owner loss. Keep control files/resources on unsafe or unverifiable cleanup; do not label the run stopped or remove evidence. |
| Researcher changes project or native store after the host snapshots it | Save a protected event-order trace with content hashes and native session usage, without raw prompt, response, credential, or application secret. A stopped native SQLite and candidate-source snapshot are not yet implemented; no stable post-run application claim follows from the trace. |
| Transcript or source diff claims a protected application effect without independent original-target capture | Leave effect `unverified`; the target-specific observer supplies request, actor, protected effect and denied controls outside researcher write access. No native transcript promotes this claim. |
| CONNECT tunnel/byte/time cap is mistaken for a provider request or charge cap | Report enforced dimensions only. Keyless HTTPS inference count and charge are opaque inside TLS; #158 remains open until an independent whole-run allowance is provided and checked. |

Provider-free checks for this implementation: `prepare` on a disposable harmless
source, `status`, exact input/source pin readback, rejection of missing approval,
changed source/control pins, Python syntax, and changed-files review. No
application/provider call, native first turn, native resume, fresh reviewer, or
target-side independent capture has been run by this change. The first live
execution must prove those paths and record its own bounded artifacts.
