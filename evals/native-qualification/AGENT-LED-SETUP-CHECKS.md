# Agent-led setup: failure checks and public scenario

**State:** #208 has a candidate separate setup mode, signed v2 linked-epoch continuation, and synthetic authority/isolation/owner-loss checks. The historical baseline below measured the pre-implementation boundary and is not #202 acceptance. A live provider/model owner-loss run remains unverified. The full #202 host build and later shared research allowance remain open. See the [operator flow](../../docs/agents/native-setup.md).

## Decision and source basis

Use a separate, bounded preparation state before the existing native `prepare` sealer. Its only successful output is a checked setup package that `prepare` can consume. The simpler alternative of calling `prepare` with placeholder runtime and build inputs fails: `prepare` already requires those inputs (`tools/native_research.py:634-693`), seals them into the research plan (`:902-939`), and `start` approves that plan after sealing (`:1098-1168`). It also creates a fresh metered run (`:3103-3240`); a second run would silently reset setup allowance unless a host-owned engagement ledger reconciles both stages. `prepare` checks the caller's scope hash but does not verify its signature or permitted effects (`:698-701`). The native bootstrap permits an inline scope signature (`skills/source-engagement-bootstrap/SKILL.md`); the legacy `operator_signature.py` verifies event challenges, not this pre-plan native scope. The existing connection, byte, and time limits do not settle monetary cost (`docs/wiki/native-research-status.md`).

The host must verify a human-signed scope and a **separate setup approval** before the first model turn or target build. Use a host-trusted signer input, not a signer identity supplied only by the agent or by the scope being checked. The approval covers the exact engagement, original source manifest, scope and goal digests, base agent image, model route, relay and trust material, setup effect class, network class, expiry, and finite allowance. The setup agent reaches only its metered model relay; the host builder has network `none`. The first supported build effect is an owned disposable container with no Docker socket, host credentials, unrelated mounts, or observer write path. Anything outside that class is a new authority decision. An approval that needs a hard monetary ceiling remains blocked until cost metering can enforce it. The later human plan approval remains a distinct, counted authority action.

The #208 setup slice now verifies a detached operator scope signature, a complete signed setup section with source/goal pins and authority fields, and a separately signed setup approval with a host-supplied trusted fingerprint. Its setup-only native run reserves fixed connection, byte, time and tmpfs limits. It does not execute a target build or carry its usage into a later research plan; #202 still needs that handoff. A requested monetary cap is rejected before Docker dispatch because provider billing is unavailable. The native stop owner revokes producers after foreground owner loss. A v2 grant can link a fresh physical epoch with residual connections/bytes and the original absolute deadline after exact stop, cleanup, provider and checkpoint checks. The native conversation is not restored. This recovery path has synthetic CLI evidence only; do not claim live owner-loss qualification or #208 acceptance.

## Failure cases to prove before implementation

| Case | Required host observation and result |
| --- | --- |
| Missing, invalid, changed, or expired signed scope or setup approval | Reject before a model turn, build, or Docker resource creation. Compare exact bytes and signer against the host trust anchor. An approval must not expand scope. |
| Changed target | Compare every original source file with the frozen manifest immediately before each effect and at package sealing. A changed, added, removed, or escaping symlink blocks; keep setup edits in a separate tree. |
| Forbidden network or effect | Inspect the actual container network and mounts, deny unapproved host actions, and retain a blocked authority request. The offline builder has network `none`. |
| Secret exposure | Reject credentials in proposed environment, commands, dependency material, and public output; never mount host keys or the control socket. Keep raw traces private and redact any public projection. |
| Missing dependency or unsupported architecture | Return the precise package/tool/architecture requirement as `blocked_setup`; no research result or usable setup package. |
| Time, memory, disk, process, connection, byte, or cost ceiling | Stop the affected action, preserve measured consumption and remaining allowance, and block further dispatch. Monetary spend unavailable from the provider must stay unknown, not zero. |
| Agent interruption or host crash during build | Persist frozen source, proposal, action ID, input hashes, pending state, and spent allowance before dispatch. On restart, adopt only a matching immutable terminal receipt. An uncertain build is `unknown_effect` and cannot be retried automatically or charged twice. |
| Incomplete cleanup | Read back exact owned container/network IDs after stop. A missing or ambiguous readback keeps setup blocked and preserves a cleanup obligation. |

## Required host handoff

1. Freeze the authorized original source and validate the signed scope and setup approval. Record the approval and initial allowance in a host-only engagement record. **Complete when no model or build can start without this record.**
2. Give the setup agent a source copy and goal in an isolated workspace, without hidden answers or an operator build hint. It writes a runtime recipe, complete offline dependency set, build argv, version and dependency probes, and `THREAT_MODEL.md`. The threat model is a working claim, not authority. **Complete when a proposal can be frozen without agent access to host control or observer writes.**
3. Validate the proposal against the effect envelope. Journal `prepared` and `dispatched` with exact frozen input hashes before the host builder runs it. Build offline in an owned disposable container; pin the image/runtime, source, dependency and output manifests, exit status, trace, usage and cleanup readback. **Complete only with a checked package or an exact blocked result.**
4. On resume, compare the original inputs and pending action with the journal and remaining allowance. Adopt a verified `captured` receipt once. Hold `unknown_effect` for readback or a separately authorized reset. **Complete when interruption cannot duplicate an effect or reset allowance.**
5. Feed the checked package and remaining allowance into the existing `prepare` sealer. Keep its later research plan approval separate and count both human decisions. **Complete when the research plan points to the setup receipt and never treats setup output as original-target proof.**

## Linked setup epoch failure checks (written before implementation)

The first setup plan may opt into a separately signed v2 grant. Its immutable
original connection and byte ceilings and absolute UTC deadline govern every
later physical epoch. The v1 approval remains a single-run grant.

| Case | Required public-path check |
| --- | --- |
| v1 approval, altered v2 signature, changed original plan/scope/source/goal/image/model/effect, or expired deadline | Refuse a linked epoch before a Docker call. The prior scope and grant remain pinned to the host-trusted signer. |
| Owner still active, `REVOKED` absent or changed, producer IDs differ, or exact Docker absence is unavailable | Refuse successor preparation; preserve the old run and its cleanup obligation. |
| Provider ledger missing, invalid, active tunnel, over cap, or incompatible with the stopped producer manifest | Refuse successor preparation. Unknown provider requests and monetary spend remain unknown. |
| A setup dispatch is uncertain, last turn has no host checkpoint, or checkpoint bytes change | Refuse successor preparation and never rerun that turn automatically. |
| Successor requested twice, an unlinked root claims the v2 grant, or a link receipt changes | Refuse a second branch or start. Preparation does not reset cumulative usage. |
| Residual connections, bytes, or absolute time below a usable epoch minimum | Refuse preparation before resource creation; never increase any original ceiling. |
| A checked owner-loss successor exists | Its run root has a fresh native store/session, the same original source and grant, a read-only copy of the bounded host checkpoint, residual connection/byte limits, and a runtime that ends by the original absolute deadline. |

The public synthetic owner-loss scenario uses a harmless multi-file source,
synthetic signed operator authority, and a fabricated terminal provider ledger
and stopped resource record. It calls `setup-next-epoch` through
`tools/native_research.py` with a Docker shim that proves exact IDs absent.
The scenario verifies precondition refusals and the prepared successor's pins,
residual limits, checkpoint and fresh-store state. Fabricated stop/accounting
receipts are explicit substitutes for a live owner-loss run; they do not prove
provider billing, model reconstruction, or production cleanup.

## Public synthetic scenario

Run the current baseline from a clean checkout:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_agent_led_setup_baseline.py --output /tmp/agent-led-setup-baseline.json
```

Requires Python 3, OpenSSL CLI, and the pinned local Linux amd64 relay file. The script supplies a Docker shim that records any unexpected call; no Docker daemon is contacted. It creates a fresh harmless three-file Python source tree in a private temporary directory, calls the public `native_research.py prepare` and `status` commands, checks exact source hashes and allowance state, then calls `start` without approval and checks that no resources were created. It records that `prepare` accepts an unsigned fixture scope because the setup authority gate does not yet exist. The supplied runtime probe is never executed. Expected exit is 0 with `baseline_passed: true` and `issue_202_acceptance: blocked_unimplemented`; that is a successful **baseline measurement**, not a setup success. The JSON file is the repeatable receipt. No target, model, provider, container, or network starts.

The #208 public synthetic check is:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_native_setup_e2e.py --output /tmp/native-setup-e2e.json
```

It creates a harmless three-file fixture, synthetic operator key and signatures, then calls the public `setup-source-manifest`, `prepare`, `status`, `start`, `setup-turn`, and `setup-resume` entrypoints with a Docker shim. It checks incomplete or unsigned scope, source identity and size, missing approval, monetary cap, expanded effect class, changed frozen source/scope, two dispatch records whose UUID order reverses their durable turn sequence, and refusal of later turns after a frozen output marker. A separate already-local BusyBox container checks read-only source, bounded tmpfs, network `none`, and exact cleanup absence. It saves hashes and observed results in the JSON receipt. It does not execute a model turn, provider request, actual setup proposal freeze, interrupted recovery, or full native-run cleanup; those remain unverified. A live-provider and target run is a separate qualification gate.
