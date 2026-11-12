# Agent-led setup: failure checks and public scenario

**State:** pre-implementation contract for [#202](https://github.com/matheusht/redteam-harness/issues/202). The current public `native_research.py prepare` is provider-free sealing, not agent-led setup. The runnable baseline below measures that boundary; its passing result is not #202 acceptance.

## Decision and source basis

Use a separate, bounded preparation state before the existing native `prepare` sealer. Its only successful output is a checked setup package that `prepare` can consume. The simpler alternative of calling `prepare` with placeholder runtime and build inputs fails: `prepare` already requires those inputs (`tools/native_research.py:634-693`), seals them into the research plan (`:902-939`), and `start` approves that plan after sealing (`:1098-1168`). It also creates a fresh metered run (`:3103-3240`); a second run would silently reset setup allowance unless a host-owned engagement ledger reconciles both stages. `prepare` checks the caller's scope hash but does not verify its signature or permitted effects (`:698-701`). The native bootstrap permits an inline scope signature (`skills/source-engagement-bootstrap/SKILL.md`); the legacy `operator_signature.py` verifies event challenges, not this pre-plan native scope. The existing connection, byte, and time limits do not settle monetary cost (`docs/wiki/native-research-status.md`).

The host must verify a human-signed scope and a **separate setup approval** before the first model turn or target build. Use a host-trusted signer input, not a signer identity supplied only by the agent or by the scope being checked. The approval covers the exact engagement, original source manifest, scope and goal digests, base agent image, model route, relay and trust material, setup effect class, network class, expiry, and finite allowance. The setup agent reaches only its metered model relay; the host builder has network `none`. The first supported build effect is an owned disposable container with no Docker socket, host credentials, unrelated mounts, or observer write path. Anything outside that class is a new authority decision. An approval that needs a hard monetary ceiling remains blocked until cost metering can enforce it. The later human plan approval remains a distinct, counted authority action.

**Implementation blocker at this base:** there is no native signed-scope proof with machine-checkable setup effects, no pre-plan model relay with a host-owned pending-action journal, and no engagement allowance shared with the later sealed run. A copied research approval or a second independent native run would leave those boundaries unverified. Build those host controls together before exposing a setup dispatch command.

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

## Public synthetic scenario

Run the current baseline from a clean checkout:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_agent_led_setup_baseline.py --output /tmp/agent-led-setup-baseline.json
```

Requires Python 3, OpenSSL CLI, and the pinned local Linux amd64 relay file. The script supplies a Docker shim that records any unexpected call; no Docker daemon is contacted. It creates a fresh harmless three-file Python source tree in a private temporary directory, calls the public `native_research.py prepare` and `status` commands, checks exact source hashes and allowance state, then calls `start` without approval and checks that no resources were created. It records that `prepare` accepts an unsigned fixture scope because the setup authority gate does not yet exist. The supplied runtime probe is never executed. Expected exit is 0 with `baseline_passed: true` and `issue_202_acceptance: blocked_unimplemented`; that is a successful **baseline measurement**, not a setup success. The JSON file is the repeatable receipt. No target, model, provider, container, or network starts.

After implementation, use the same fixture through the public setup entry with a test-only signed scope and setup approval, an unhinted agent proposal (or a labeled synthetic proposal for local checks), and a host-controlled offline builder. Save the exact fixture and approval bytes, proposal, command, input/output hashes, trace, allowance, assistance, cleanup, and blocked variants above. A second operator must repeat the package from those saved inputs. A live-provider and target run remains a separate qualification gate.
