# M0 environment and delivery grounding

Observed 2026-11-14 in `/Users/matheusvsky/.codex/worktrees/setup-checked-adoption/llm-redteam-harness`, source head `89bcede2c1e62573767017251e8734f211fa3573`. Read-only source investigation. No provider, research-target, container creation, SSH connection, image install, service restart, or cleanup action ran. Temporary workflow sources are under `/tmp/oslit-implementation/workflow`.

## Conclusion

Reuse the existing exact-ID Docker ownership, prestart inspection, immutable input binding, independent stop-owner pattern, and post-stop resource readback. Keep old callers unchanged. Add one environment adapter with local Docker and SSH transport; it returns protected observations to the new journal and does not own another research state machine. The current fixed OpenCode gateway and one-shot 24-hour owner are not general network or renewable-lease implementations. No generic SSH lab runner was found.

The smallest complete scope is still substantial: enforce worker identity/resources at actual tool/network execution, make setup failures repairable, bind source/binary/application identities, and read back both local and remote cleanup. A queue lease without access revocation does not satisfy shared-target isolation.

## Observed host prerequisites

| Check | Observed result |
| --- | --- |
| Host | Darwin 25.5.0 arm64 |
| Python | 3.14.6 |
| Docker client | `/usr/local/bin/docker`, 29.3.1, build c2be9cc |
| Docker context | `desktop-linux` |
| Docker server | `docker version` and `docker info` each timed out at 5 seconds. An earlier unbounded read was cancelled; it returned Client details and Server null. No container/image inventory could be obtained. |
| SSH | `/usr/bin/ssh`, OpenSSH_10.2p1 / LibreSSL 3.3.6; ssh-keygen exists |
| SSH references | `~/.ssh/config`, `~/.ssh/known_hosts`, `~/.ssh/id_ed25519` exist; values not read. These references do not identify an authorized remote lab. |
| Forge | `gh` installed; `origin` absent; connected GitHub file reads work. Public web reads returned 404 for the private workflow repo. |

Coordinator later reported shared Docker backend/VM, no alternative VM tooling, and 4.6 GiB free disk. Do not restart shared Docker, remove data, or install VM/images to force progress. Coordinator requested an authorized disposable SSH host asynchronously. Until supplied and verified, remote integration evidence remains unavailable.

Inventory command pattern: `subprocess.run(argv, capture_output=True, text=True, timeout=5)` around Docker read commands. Never use an unbounded Docker probe in preflight. `inspect` should distinguish a present client from an available server without target/model contact.

## Reuse map and actual limits

| Existing source | Reusable behavior | Limit to preserve or remove only in v2 |
| --- | --- | --- |
| `tools/native_setup_builder.py:701` `docker_call` | Bounded subprocess output/time; restricted environment; daemon-ID check before operations | Setup-shaped arguments; extract only when a real second caller needs the shared function |
| `tools/native_setup_builder.py:745` `event_call` | Record action intent before Docker, unknown effect on timeout, acknowledge exact output hashes, detect credential-like output before retaining it | Its mutable build journal is old-route state; v2 should emit its own journal event once, not maintain a second authoritative build state |
| `tools/native_setup_builder.py:772` / `:815` | Inspect exact container; require nonce/name/ID before removal; inspect and list again for absence | Do not weaken mismatched identity or unavailable readback into cleanup success |
| `tools/native_setup_builder.py:858` `setup_build` | Original source read-only; recipe/catalog/image/output hashes; network none; constrained disposable build; protected checked receipt | Offline catalog required; failure is terminal for that attempt. v2 must preserve attempt and return setup diagnosis to lead for revised attempt, without prewritten operator build command |
| `tools/native_research.py:2415` `_network` and `:2445` `_create` | Named/nonce-labelled internal network; inspect network and exact created-container constraints; read-only root, dropped caps, no privilege escalation, bounded CPU/memory/PIDs, no Docker socket | Fixed resource roles and fixed limits. A general adapter must take admitted limits/capabilities and verify them, not import target-specific capture branches |
| `tools/native_research.py:2830` `_preseal_setup`, `:2860` `_preseal` | Worker internal network and only keyless relay dual-homed; source copy separation | OpenCode settings, exact role roster and target branches are historical. Do not use unchanged preseal as v2 orchestration |
| `experiments/native-network-preflight/tcp_relay.go` | Small keyless relay to one host listener | It forwards bytes, not authority. Its probe and default route are OpenCode-specific; protocol/destination checks remain a gateway responsibility |
| `experiments/native-network-preflight/v2_connect.py` | Owned sockets, connection/byte/duration bounds, native stop checks | Fixed CONNECT authority, opaque TLS; cannot establish model/request/token/spend accounting or general acquisition policy |
| `tools/native_provider_gateway.py:1` | Host-only credential injection; no request/response logging; validate provider request before forwarding | Fixed OpenCode endpoint and model. Not a general web proxy or Codex/OMP provider adapter |
| `experiments/native-network-preflight/v2-effect-windows/native_run.py:109` | Prestart control-path mount exclusion, exact producer manifest, independent stop-owner handshake | One-shot monotonic deadline, hard 86400 cap, terminal revocation cannot restart. Preserve v1; new worker lease semantics require separate versioned path |
| `experiments/native-network-preflight/v2-effect-windows/_native_stop_owner.py` and `producer_stop.py` | Independent parent-loss/timeout watcher; exact manifest/nonce/ID bindings; freeze/kill and recheck entire producer set before REVOKED | Producer collection is sealed and bounded; useful pattern, not a dynamic team controller |
| `tools/native_closeout.py:286` / `:319` | Verify daemon identity; list resources by ID and name; bind owner stop, snapshot, revocation and cleanup receipts | Coupled to old plan and continuation. Reuse observations, not old claim meaning or another global continuation owner |
| `tools/docker_session_runtime.py:441` / `:599` / `:964` | Strict local Docker socket, exact ownership, read-only mounts, independent watchdog and cleanup | Existing generic session is fixed linux/arm64 and local unix socket; not SSH capable. Do not pretend setting DOCKER_HOST creates qualified remote ownership |
| `tools/operator_signature.py:83` | Exact-byte SSH signature verification, scope signer pin, bounded verifier | Keep authority v2 validation separate from SSH transport; an SSH login key is not engagement authority |

Historical network checks already specify direct external/host TCP and DNS bypass challenges with positive controls (`experiments/native-network-preflight/V2-TUNNEL-CHECKS.md:16`). Their existence is not a pass on this host/revision. Verify internal-network isolation against host gateway, metadata/private ranges, DNS, IPv6, direct sockets and changed proxy environment before admitting a network capability. Docker `--internal` plus proxy variables alone is not the proof.

## Concrete minimal environment interface

Use one environment module with a transport selected from the immutable initial input. Reuse subprocess/SSH/Docker rather than add a provisioning service. Proposed operations: `inspect`, `prepare`, `execute`, `readback`, `renew`, `revoke`, `cleanup`. Controller decides admission and writes intent; environment validates the admitted worker generation/resource lease again at execution and returns `settled`, `unknown`, or `unavailable`. Never turn a subprocess exit alone into observed target effect.

Protected resource identity should contain engagement ID, environment ID/generation, transport, pinned host key/account for SSH, Docker daemon ID, random ownership nonce, exact container/network IDs, image digest/platform, worker/assignment generation, allowed mounts, network policy digest, resource limit digest, and lease generation/expiry. Log references and digests rather than secrets or complete container Env. Every created artifact has a cleanup obligation.

1. **Source:** freeze input revision/files and modes; mount original read-only; grant an owned disposable workspace. Agent chooses setup commands/tools under admitted acquisition. Record failed build observations and the revised recipe as separate attempts. Successful normal-function check pins the resulting image/files; no security conclusion follows.
2. **Binary:** require regular-file digest, platform/architecture and permitted privilege capabilities. Mount binary read-only; record loader/libraries and startup privileges. No fabricated source manifest or build recipe. Missing architecture/emulation/debug permission is an explicit blocker.
3. **Application:** bind signed endpoint/account references and environment identity. Prefer owned clone or distinct instance/account. If target is non-copyable, grant one write-capable worker for the affected resource at a time; proxy/service routes and shell/browser access must use that active lease. Unknown effect holds dependent tasks while separate instances can continue. No generic readback can infer arbitrary application reset success.
4. **Combined:** use all supplied descriptors but preserve their distinct identities and explicit source/build/deployment correspondence. Never substitute local-clone observations for remote-deployment evidence.
5. **SSH:** explicit authorized host/account and pinned host key, `BatchMode=yes`, `StrictHostKeyChecking=yes`, dedicated known-hosts file, finite connect/command timeout, no agent forwarding, no password prompt. Run only in newly owned run directory; call the same Linux environment owner there. Pin host boot identity and daemon identity; never sweep processes or reuse unknown containers. Do not send credentials in argv, records or model-visible files.

## Lease and network enforcement

Use short renewable worker leases, distinct from optional engagement expiry. Host-controlled renewals require current scope, worker generation, reservation and write-lease ownership. A remote owner/watchdog must expire locally when SSH/controller disconnects; reconnect verifies exact resources before any new dispatch. Boot/session identity prevents a persisted monotonic timestamp from silently gaining new meaning after reboot. Stop/revoke closes sockets and freezes/stops the exact worker/tool descendants before ownership transfers. Lease expiry is not cleanup proof.

General network admission needs separate provider, acquisition and target routes. Grant explicit signed protocols/destinations/address classes; resolve and validate every new destination, pin the actual connection address, reject disallowed redirects/new CONNECTs, and deny direct worker egress independently of proxy environment. Retain raw-observation incompleteness explicitly. Provider secrets and controller/admin channel remain outside arbitrary shell tools. If native runtime and arbitrary shell share the provider capability, a direct model call may bypass nominal spawn/role controls; M2 must settle attribution and gateway reservation semantics before calling that boundary enforced. Broad internet acquisition cannot silently grant arbitrary provider or target effects.

For a non-copyable target, revoke and read back old write access before granting the next worker. A task flag or cooperative lock file is insufficient because shell/browser can keep an open connection. Route access through a host-owned gateway or isolate the worker network; close active channels on lease loss. Agent code must not hold Docker/SSH administration credentials or mount the lease-control files.

## Failure-first public-workflow scenarios

Specify these before implementation and retain the commands, input manifests, hashes, versions, statuses, sanitized observations and cleanup readback. Use harmless controlled services; no planted vulnerability or fresh target research.

| ID | Concrete scenario | Required evidence |
| --- | --- | --- |
| E02-a | Source setup fails due to missing dependency; lead obtains permitted dependency and revises setup; original source then checked again | Failed and repaired attempts retained, exact acquisition/version/hash, original unchanged, real normal-function observation, no operator build hint |
| E02-b | Denied host, redirect to denied address, DNS rebinding/alternate address, direct IPv4/IPv6 socket, host gateway/metadata/DNS bypass and changed proxy variables | Independent receiver observes no prohibited connection; admitted destination positive works; missing protocol checks explicitly unavailable |
| E02-c | Change recipe, source, image or dependency bytes after setup receipt; output contains credential-like marker | Refusal before dispatch/publication, no secret stored, preserved original receipt |
| E03-a | Same benign echo program supplied as binary only, as running application only, and combined descriptors | Each starts without a source requirement; identity/platform/role recorded; wrong architecture or account gets precise blocker |
| E03-b | Two workers write the same application/account; old worker keeps socket/browser session; lease expires and work reassigns | Actual old writes denied before effect; one writer observed; independent instance continues; stale worker cannot revive by message |
| E07-a | SSH connection drops while remote harmless job is running; controller restarts before and after lease expiry | Remote watchdog expires without controller, reconnect adopts exact receipt once, job/resources read back, no blind repeated command |
| E07-b | Host key/boot identity/daemon ID/container nonce differs; cleanup command fails | Refuse unrelated resource operation, preserve unresolved cleanup, no successful closeout |
| E07-c | Stop during partial remote creation and while child subprocess remains | All owned IDs recorded before effect; exact descendants revoked; absence verified on remote host; unknown remains held if unreachable |
| E16-a | Clean install -> inspect -> run -> status -> direction -> resume -> stop -> export using documented source/binary/app/combined inputs | Public commands work, readonly commands never dispatch, version/credential references checked without values, export resolves every evidence digest |
| E16-b | Run same harmless workflow through Codex and OMP; worker status/claim/submit, messaging/waiting, fresh reviewer and service-manager restart | Actual native feature/control observations, native vs simulated labels, persisted cursor and ownership, no provider claim from CLI help alone |

Prerequisites: responding Docker daemon and digest-pinned suitable runtime images; authorized disposable Linux SSH host/account/host-key for remote cases; signed harmless engineering scope; controller trust inputs; actual Codex/OMP credentials through approved adapter; independent receivers for network observations. Current Docker/SSH/live-provider cases are unavailable, not passes. A controlled local SSH container may verify SSH transport later but does not establish external-host reliability.

## Delivery and caller inventory

Implementation reaches public `tools/native_engagement.py`, new controller/contract/runtime/environment modules, shared builder/execute/closeout primitives only when extracted, native network/owner integrity pins and their callers, versioned input schema, worker command wrapper/host channel, safe input examples, `docs/agents/engagement.md`, root/bootstrap/Pi route pointers, reusable methodology bundle, install/version manifest, systemd resume example, sanitized export spec, E02/E03/E07/E16 scenario runner and CI prerequisites. Preserve old drivers/records and v1 checks; do not rewrite historical qualification artifacts.

M6 inspect must report client present/server unavailable separately, architecture support, missing referenced credentials without reading values into logs, provider capability and unsupported hard-limit dimensions. Install manifest should pin repository/runtime/schema/images and list Python/SSH/Docker requirements; Go/relay only for adapters using it. Service manager restarts `resume` against same root/authority/allowance, not `run` with a new grant. No custom daemon.

## Current engineering workflow requirements

Read current private repository main through connected GitHub reader. Observed main head `9de2f7ca357197486886cc7c931c634be3657194`; fetched file blob hashes saved separately in workflow source manifest. Public web fetch returned 404; connector succeeded. Relevant downloaded sources: README, activation, host contract, guide introduction/build/long-work, PR publication, active pstack router, teteu entry, code-cleanup, opening-a-pr and autopilot-full.

The live active `opening-a-pr.md` is materially different from installed upstream pstack:

- Record base/head/status and all existing staged/unstaged/untracked/user work. Separate writer branches/worktrees; never reset a shared worktree to resolve conflict or between agents.
- Verify and commit each coherent unit before next. Each commit is reviewable; no mandatory one-PR-per-commit or arbitrary PR split.
- Before every PR-facing code commit, apply `candidate/code-cleanup`; preserve legitimate validation/comments; rerun affected checks after edits. Docs-only skips code cleanup explicitly.
- Use actual patch and ordered commits, current fixed-patch independent review including WIP. Rewritten/changed patch needs fresh affected evidence.
- Prose follows `matt/pr`, pstack technical-writing and unslop; adapted no-comments is judgment review, not comment deletion.
- Finish implementation/checks/review before a ready PR. Draft only when user explicitly asks. Short Conventional Commit title and why/what/scope/blast-radius/actual-verification body.
- Create ready using connected tool or authenticated CLI, then read back URL/number/base/exact remote head/draft/checks and visibility. Save normalized fields and run publication consistency check. A local record does not prove forge truth.
- Preserve checkpoint ancestry if a connector publishes Git objects differently; record local-to-remote mapping rather than flattening.
- PR creation does not itself grant merge authority or unattended watching. Full-autopilot tested merges still require current task authority, fresh independent review, remote protection/check state and exact-head post-merge check. Held dependent-stack route stops unmerged.
- Keep decision trail and recoverable next action. Preserve operator-reserved fresh-target research test.

The local `origin` binary is absent; use connected GitHub or authenticated `gh` for applicable forge operations. Workflow validators were not executed because this pass fetched the required reading subset, not a complete installation. Parent should load exact leaf skills before applying their methods; downloading a source does not claim it ran.

## What remains unverified

No live environment, native runtime/provider, SSH, network-bypass, cleanup or multi-day acceptance was executed. No code was changed. Main risks are enforced caller attribution around arbitrary native tools, direct network/model bypass, remote lease survival and exact cleanup under lost connectivity; these need real controlled evidence before support claims.
