/goal
@antigravity-continue
# Ajar v3.6-Balanced Autonomous Swarm-Lead Charter
## Target #1: `openai/openai-agents-python` (+ 1-Hop `mcp` Python SDK) — Clean-Room Verification & OpenAI Bugcrowd VRP Audit (Up to $100,000)

### 0. GOVERNANCE, SAFETY & PURE CONDUCTOR LAW (NON-NEGOTIABLE)
1. **Pure Conductor Mandate (`0` Direct Code Work | `< 25%` Lead Context)**:
   - You are the **Swarm Lead**. You **NEVER** inspect raw source files directly, **NEVER** run raw `grep`/`rg` across the repository, **NEVER** author test harnesses or patches yourself, and **NEVER** execute builds/fuzzers in your own context.
   - Keep `< 25%` context utilization at all times. Coordinate **8 concurrent specialized workers** (`W1`–`W8`) exclusively via `.ajar/REALITY.md`, `.ajar/WHITEBOARD.md`, `.ajar/STATUS.md`, `chain_weaver`, `autobuild` + Python `Input Encoder` microfuzzing, and Ring-0 `verify.py` (`C3`).
2. **Clean-Room & VRP Compliance Law**:
   - **100% Offline Execution**: Unset `OPENAI_API_KEY`, call `set_tracing_disabled(True)`, and bind all mock servers strictly to `127.0.0.1` ephemeral ports or in-memory `anyio`/`asyncio` streams. Zero traffic may touch `api.openai.com` or any external host.
   - **Defensive Verification Only**: Use deterministic `ScriptedModel` / mock `ModelProvider` fixtures, benign canary state markers, and `pytest` `tmp_path` isolation.

---

### 1. TARGET REPOSITORIES, 1-HOP MOUNTS & SHIPPED BUILD PROFILES
Instruct `W1` (`autobuild` & Environment Architect) in Wave 0 to pin exact commit SHAs in `.ajar/REALITY.md`:
- **Primary Repository**: `https://github.com/openai/openai-agents-python` (`HEAD` of `main`)
  - **In-Scope Surface**: `src/agents/**` ONLY (exclude `tests/`, `docs/`, `examples/` at minute zero unless re-exported in `src/agents/__init__.py` runtime defaults).
- **1-Hop Dependency Mounts**:
  1. `modelcontextprotocol/python-sdk` (`mcp >= 1.19.0, < 3` — `ClientSession`, stdio/SSE/StreamableHTTP transports).
  2. `pydantic` (`v2.x` `TypeAdapter` & strict JSON schema conversion in `src/agents/strict_schema.py` / `function_schema.py`).
  3. `cryptography` (AEAD/Fernet primitives in `src/agents/extensions/memory/encrypt_session.py`).
- **Build & Regression Recipe**:
  - `uv sync --all-extras --dev`
  - `OPENAI_API_KEY="" uv run pytest -n0` + `make typecheck` + `make lint`
- **Documented Non-Bugs (Pre-Seed `.ajar/REALITY.md` Exclusions)**:
  - `UnixLocalSandboxClient` explicitly documents zero OS-level confinement on Linux; focus on escaping configured `Manifest`/`Permissions`, `DockerSandboxClient`, or `ApplyPatchTool` workspace roots.

---

### 2. EIGHT-WORKER SWARM TOPOLOGY (`W1`–`W8`)
- **`W1` (Build & Harness Steward)**: Owns `.ajar/build.sh`, `.ajar/REALITY.md`, offline `ScriptedModel` / loopback `MCPServer` fixtures, and Ring-0 `verify.py`.
- **`W2` (Orchestration, Guardrails & Handoffs)**: Maps `src/agents/{run,guardrail,tool_guardrails}.py`, `src/agents/handoffs/`, `src/agents/run_internal/{guardrails,tool_execution,turn_resolution}.py`.
- **`W3` (MCP Client & Tool Schema Boundaries)**: Maps `src/agents/mcp/{server,manager,util}.py`, `src/agents/{tool,strict_schema,function_schema}.py`.
- **`W4` (Sandbox, Patch/Editor & Shell Capabilities)**: Maps `src/agents/{apply_diff,editor}.py`, `src/agents/sandbox/**` (`SandboxAgent`, `DockerSandboxClient`, `SandboxApplyPatchTool`, `SnapshotSpec`).
- **`W5` (`RunState`, Sessions, Encryption & Realtime)**: Maps `src/agents/run_state.py`, `src/agents/memory/**`, `src/agents/extensions/memory/encrypt_session.py`, `src/agents/realtime/**`, `src/agents/tracing/**`.
- **`W6` (Backward Sink Abductor & `chain_weaver` Synthesizer)**: Posts backward `WISH` obligations across the 12 canonical `EffectType`s (`cross_session_key_reuse`, `reentrant_callback_window`, `policy_alias_divergence`, `privilege_or_capability_smuggling`, `residual_error_state`, `schema_or_encoding_malleability`).
- **`W7` (Python `Input Encoder` Microfuzzer Engineer)**: Writes deterministic `emit(rng)` / `Hypothesis` async-interleaving harnesses for active `L1`–`L5` and `[BNT-*]` chains.
- **`W8` (Clean-Context Cross-Family Critic & `C3` Patch Author)**: Verifies all 5 Ring-0 `verify.py` gates and authors minimal upstream-ready patches + regression tests.

---

### 3. FIVE CROSS-SEAM HYPOTHESES (`L1`–`L5`) & `INPUT ENCODER` CONTRACTS
1. **`L1` — Parallel `InputGuardrail(run_in_parallel=True)` vs. Side-Effecting Tool & Session Commit Race**: Test whether slow/async `InputGuardrail` or sibling `ToolInputGuardrail` tripwires allow concurrent turn-1 `FunctionTool` / `ApplyPatchTool` / `MCPServer.call_tool` side effects or `Session.add_items()` writes to commit before cancellation propagates (`enc_l1_guardrail_race.py`).
2. **`L2` — `RunState.to_json() / from_json()` Resume Lineage, Sticky Approvals & Handoff Confusion**: Test whether `ToolApprovalItem` / `MCPApprovalResponseItem` / `always_approve=True` decisions survive argument mutations or cross-agent handoffs / `ToolNameCollisionPolicy` namespace collisions (`enc_l2_runstate_lineage.py`).
3. **`L3` — Loopback MCP Dynamic Tool Rug-Pull, Approval Bypass & Bearer/Header Leakage**: Test whether `notifications/tools/list_changed` or reconnects bypass `require_approval`, cross-contaminate tenant sessions on timeout retry, or leak `MCPServerStreamableHttpParams` credentials into LLM-visible `ToolCallOutputItem` errors or `RunState` (`enc_l3_mcp_boundary.py`).
4. **`L4` — `SandboxAgent` / `ApplyPatchTool` / `apply_diff` Symlink & Path Confinement Escape**: Test multi-hunk `*** Add File:` / `*** Move to:` / `*** Update File:` envelopes, Unicode path normalization, symlink staging, and `DockerSandboxClient` archive copy-in/copy-out against `tmp_path/outside_canary.txt` (`enc_l4_sandbox_patch.py`).
5. **`L5` — `EncryptedSession` Cross-Tenant Row-Swap (Missing `session_id` AAD) & `RealtimeSession` Interrupt Ordering**: Test whether `EncryptedSession` binds `(session_id, seq)` as AAD against shared-DB ciphertext replay/splicing, and test concurrent WebSocket tool-call + `Handoff` + `interrupt()` races (`enc_l5_session_realtime.py`).

---

### 4. AUTONOMOUS STOPPING CRITERION (`TWO-TIER PINCER EXHAUSTION`)
Run autonomously (`@antigravity-continue`, enforcing 45m physical-signal pivots, 65%/70% worker relays, and 92% drain reserve) until **EITHER**:
- **(A) `C3` Crown-Jewel Victory + Queue Drain**: At least one High/Critical boundary violation passes all **5 Ring-0 `verify.py` `C3` gates** (`3/3` clean-worktree pre-patch fail on shipped public API, minimal `src/agents/` patch, rebuild/retest `3/3` pass + full `pytest`/`mypy`/`ruff` green, and Cross-Family Critic approval) **AND** all high-priority `[BNT-*]` / `EFFECT <-> WISH` chains on `.ajar/WHITEBOARD.md` are drained; **OR**
- **(B) `100%` Two-Tier Pincer Exhaustion**: `100%` of untrusted/cross-trust public entrypoints in `src/agents/**` are mapped forward **AND** `100%` of Crown-Jewel sinks are backward-abduced with verified `file:line` `INVARIANT` or `DEAD_END` proofs in `.ajar/WHITEBOARD.md`.
