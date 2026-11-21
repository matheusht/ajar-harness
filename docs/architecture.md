# Ajar v3.3 Architecture

**Ajar** (built by **Ajar Labs**) is a zero-LLM deterministic verification engine (`ajar/`) paired with ASD-STE100 workflow skills (`skills/`) for `Platform`, `Code`, `Fixes`, `Security reviews`, and `Supply chain`.

Ajar never calls an LLM API inside its core state, gate, graph, planner, or reproduction modules. Agents supply hypotheses, minimal patches, and verification scripts; `ajar` enforces state transitions, suspended Open Doors, multi-hop middle-unicorn percolation, event-driven epistemic micro-hooks, stage-split swarm wire profiles, workspace isolation, locus-bound causal proof, 9-arm production patch verification, secret redaction, and SQL closeout gates.

---

## 1. Dual-Mode Execution, Campaign Phases, and Swarm Dispatch (`ADR-0017`..`ADR-0022`)

Both operating modes share the same SQLite WAL database (`run.db`), CLI commands, and closeout gates:

1. **Host Mode (Interactive Subscription Agents & Stage-Split Swarms):**
   - Driven by Claude Code, Codex CLI, Antigravity, OpenCode, or any MCP client via `ajar <subcommand>` or `ajar mcp`.
   - **Hunt vs. Remediate Campaign Phase Split (`ajar phase`):** Runs initialize in `campaign_phase = 'hunt'`, blocking 9-arm `ajar patch verify` and skipping `patch` task leases so swarm capacity stays focused on discovery and multi-stage chain synthesis until `ajar phase advance --to remediate`.
   - **Stage-Split `"Swarm Worker"` Dispatch & Portfolio Lanes (`ajar swarm`):** `ajar swarm packet --stage <investigate|bridge|falsify|reproduce|chain|portfolio>` emits compact (`<= 45`-line) `direct` worker packets containing stripped `(id, severity, locus)` tuples with zero parent chain-of-thought or weaponized prose (`portfolio` balances woken `chain` + `falsify`/`reproduce` + bounded `bridge` + greenfield `investigate`). If an upstream classifier blocks a subagent, `ajar swarm fallback <dispatch_id>` steps down `direct -> swarm_patch_first -> regression_tdd` (`swarm_dispatches` table) and splits multi-claim batches (`[4] -> [2, 2] -> [1, 1]`).
   - **Session Persistence:** `ajar hook claude-stop --if-active` and `ajar loop codex|omp` evaluate SQL gates `G1–G5` when an agent attempts to stop. If gates remain unmet, the hook blocks exit (`rc=2`) and returns the unmet blockers, guarded by a **3-stall circuit breaker** (`MAX_CONSECUTIVE_STALLS = 3`).
2. **Standalone Mode (`ajar run`):**
   - `ajar run <target> [--until exhaustive-high|first-verified-high|crown-jewel] [--phase hunt|remediate] [--cogs-cap <USD>] --workers <N> --discover-passes <K>` dispatches bounded explore, bridge, falsify, reproduce, chain, escalate, and patch workers against `run.db`.
   - **Keep-Biased `Best-of-N` Discovery -> Kill-Biased Funnel:** `--discover-passes K` seeds bi-directional exploration passes across `outside_in`, `inside_out`, `native_ffi`, and `peer_symmetry` before independent `falsify` and locus-bound `reproduce` kill false positives.
   - **Role-Tier Model Routing, Anti-Soliloquy Guard, & Refusal Fallback:** `select_model_for_task` routes deep architectural reasoning (`map`, `chain`, `bridge`, `patch`, `falsify`, `escalate`, and `zero_skill` `investigate`) to `AJAR_MODEL_REASON`, mechanical search/PoC tasks (`domain` `investigate`, `reproduce`, `instrument`) to `AJAR_MODEL_HUNT`, flags fabricated shell/gdb transcripts via `detect_soliloquy_transcript`, and retries safety-refused prompts once on `AJAR_MODEL_FALLBACK`.
   - **Dry-Surface Token Breaker & 80/20 Verify Reserve:** Spending `> 25%` of `cogs_cap_usd` on a single surface in `explore` phase with `0` anomalies, `0` primitives, and `0` claims throttles remaining open `investigate` tasks on that surface to `conditional_blocked`. Spending `>= 80%` of total budget transitions the run to `verify_only` (`falsify`, `reproduce`, `chain`, `escalate`).

---

## 2. Workspace Geometry, Post-State Snapshots, and Cross-VM Reopen (`D-04`, `ADR-0019`..`ADR-0022`)

Run state lives outside the target tree under `~/.ajar/runs/<run_id>/`, paired with local SSD build caches (`/tmp/ajar-build-cache/<run_id>/`) and compact shared ledger mirroring (`/shared/user/.gemini/ajar/runs/<run_id>/`):

```text
~/.ajar/runs/<run_id>/
├── run.db                           # SQLite WAL database (busy_timeout = 30000 ms; auto-migrated via _ensure_v33_schema)
├── brief.md                         # Lead Orchestrator campaign strategy brief
├── artifacts/                       # Run-scoped PoC/fixture scratch ($AJAR_ARTIFACTS_DIR)
├── workspace/                       # Default --envelope working directory (read-only target/)
└── repro/
    ├── repo.git/                    # Standalone repacked git clone of source target (zero alternates)
    ├── baseline_suite.json          # Cached clean-HEAD test suite baseline for Arm 5 diffing
    ├── snapshots/                   # Captured Arm-1 post-state tarballs (snp-*.tar.gz) for `ajar chain probe`
    ├── failures/                    # Scrubbed replayable JSON failure receipts (<claim_id>-<n>.json)
    ├── helpers/                     # Read-only (0444) StageContext, sitecustomize.py, ajar_helpers/
    ├── slot-<k>/                    # Shared 8-slot pool for 4-arm repro, `repro try`, chain ablation, and 9-arm patches (auto-heals stale `.git/index.lock`)
    └── slot-inst/                   # Isolated scratch worktree for `chain probe` and `claim instrument`
```

- **Hybrid Storage & Cross-VM `ajar reopen`:** Heavy `CARGO_TARGET_DIR`, `GOCACHE`, and `CCACHE_DIR` trees stay on local SSD `/tmp/ajar-build-cache/<run_id>` while `_clean_slot_preserving_objects` retains compiled `.o`/`.a` files across both 4-arm and 9-arm resets via monotonic `mtime` bumps. `ajar reopen <run_id>` hydrates `~/.ajar/runs/<run_id>` from `/shared/user/.gemini/ajar/runs/<run_id>`, upgrades `v3.2.x` tables in-place, reconstructs missing `target_path` checkouts offline from `repro/repo.git`, and resets zero-attempt `blocked` claims to `survived_falsify`.
- **Toolchain Scrubbing & Container Loopback Guard:** `scrubbed_subprocess_env` strips host credentials while preserving `SDKROOT` (and cached macOS `xcrun`), `DEVELOPER_DIR`, `PKG_CONFIG_PATH`, `.cargo/bin` + rustup toolchain `bin` (`CARGO_NET_OFFLINE=true`), `$AJAR_RUN_DIR`, and `$AJAR_ARTIFACTS_DIR`. `_run_shell_in_slot` sets `AJAR_BLOCK_EXTERNAL_NET=1` and loads `repro/helpers/sitecustomize.py` to block non-loopback `AF_INET`/`AF_INET6` sockets.

---

## 3. SQLite WAL State Model, Reactive Open Doors, & Multi-Hop Percolation (`ADR-0018`..`ADR-0024`)

`ajar/store/`, `ajar/db.py`, `ajar/chain_planner.py`, `ajar/epistemic_hooks.py`, and `ajar/reactions.py` coordinate **Work**, **Suspended Open Doors**, **Percolation**, **Epistemic Hooks**, **Long-Horizon Memory**, **Truth**, and **Economics**:

### Work, Portfolio Anti-Starvation, & PR Differential Axis
- `surfaces` (`requires_tags_json`) & `surface_drivers`: Mapped entrypoints, required capability tags, trust boundaries, and executable harnesses.
- `tasks` & `swarm_dispatches`: Prioritized work items (`map`, `investigate`, `bridge`, `falsify`, `reproduce`, `instrument`, `chain`, `patch`, `escalate`) with `direction`, statuses `open -> leased -> done | dry | conditional_blocked`, `checkpoint_json`, and `diff_state`. `lease_next_task` prioritizes woken `chain` tasks (`salience >= 96`), interleaves greenfield `investigate` ahead of `bridge` whenever `leased_bridges >= 2`, and skips `patch` tasks while `campaign_phase == 'hunt'`.
- `coverage_spans` & `steers`: SHA-bound source line spans (`ajar coverage record`) and attributable operator rules (`scope_authority` vs `research_steering`).

### Suspended Subgoals ("Open Doors") & Multi-Hop Middle-Unicorn Percolation (`ajar/chain_planner.py`)
- `crown_jewels`: Concrete terminal sinks (`jewel_id`, `locus`, `impact_class`, `max_steps`, `forbid_cli_config_override`).
- `parked_doors` & `door_fts`: Suspended deep sinks or partial chains (`ajar door park`) holding `wanted_tags_json`, `wanted_symbols_json`, `blocker_locus`, and `snapshot_id`. Spawns `<= 2` bounded `bridge` tasks (`max_bridge_attempts = 2`) and wakes reactively (`parked | bridging | exhausted_locked -> ready`) via tri-modal matching (tags + code symbols/guard proximity/1-hop `repomap_edges` + FTS5 BM25) whenever any worker records a matching primitive, anomaly, claim, or finding.
- **Multi-Hop Percolation & Trust Gadgets:** `primitives` separates invariant-breaking capabilities (`role = 'capability'`) from non-buggy code that trusts a broken invariant (`role = 'trust_gadget'`, `ajar primitive dry`). `detect_percolated_multi_hop_paths` computes $2..10$-hop forward/backward DAG reachability, enqueuing `salience = 98` `chain` tasks when a middle link connects an entry prefix to a sink suffix and surfacing 1-link `unicorn_gaps` in `ajar chain frontier`.

### Event-Driven Epistemic Hooks & Prefix-Stable `< 4 KB` Context (`ajar/epistemic_hooks.py`, `ajar/reactions.py`)
- **Bounded `H1`–`H8` Micro-Hooks:** Triggered deterministically by SQLite state transitions (`H1_GUARD_SYMMETRY`, `H4_TYPED_STATE_BRIDGE`, `H5_POST_CONFIRM_ESCALATION` including `stepping_stone` `High -> Critical` escalation, `H6_RELEASE_UB_DIFF`) or AST/source signals (`H2`, `H3`, `H7`, `H8`), capped at `<= 2` active hooks (`<= 90` tokens) with mandatory `Kill Rule` lines.
- **Prefix-Stable `< 4 KB` Context (`render_task_context`):** Keeps the `Certified Run Prefix` (`Goal`, `Active Workspace Steers`, sorted `Certified Bindings`) 100% byte-identical across workers while placing `Open Doors`, `Cross-Subsystem Capability Bridges`, and `Active Epistemic Hooks` inside `Task Delta`.

### Truth & Remediation Axis
- `claims`: Enforces structural prose (`validate_structural_claim_prose`) and separates `preflight_error` / `build_or_env_error` (`0` strikes) from `target_negative` (`failed_repro_count` incremented only on real target negatives).
- `findings` & `repro_snapshots`: Created by `ajar claim reproduce` with `realism_tier` (`crown_jewel | high_impact | stepping_stone`), persisted `build_cmd`, optional `snp-*` post-state snapshots (`--save-post-state`), and single-command calibration (`ajar finding calibrate`).
- `chains`: Composes `fnd-*`, `clm-*`, `prim-*`, and `anom-*` directly in `ajar chain propose` (auto-inheriting `micropatch_diff`, rejecting gadget-only chains and caller self-execution flags, and enforcing `AJAR_ABLATE_STEPS=""` on Arm 2).
- `patch_verifications`: Created by `ajar patch verify` in `remediate` phase after all **9 hardened production arms** pass (`remediation_state = 'verified_local'`).

---

## 4. Verification Stages: Reproduction, Zero-Boilerplate Chains, & 9-Arm `Fixes` (`ADR-0019`..`ADR-0024`)

1. **Stage A — Strike-Free Smoke Probes & Locus-Bound Reproduction (`ajar repro try`, `ajar claim reproduce`):**
   - `ajar repro try` runs strike-free build/PoC checks inside the shared 8-slot pool (`slot-<k>`), eliminating single-slot contention during parallel swarm hunts.
   - `ajar claim reproduce` enforces `evaluate_precondition_realism`, `validate_entrypoint_fidelity`, and `validate_no_static_source_cheat`, runs `--build-cmd` + Arms 1–4 (`clean+PoC`, `clean+control`, `micropatch+PoC`, `micropatch+control`), persists scrubbed replayable failure artifacts (`repro/failures/<claim_id>-<n>.json`) on non-passing runs, captures `--save-post-state` snapshots after Arm 1, and runs optional Arms `5A`/`5B` (`--release-cmd`).
2. **Stage B — Post-State Probing & Multi-Artifact Chain Ablation (`ajar chain probe`, `ajar chain propose`):**
   - `ajar chain probe --from-snapshot <snp_id>` hydrates a Stage-1 filesystem tarball into `slot-inst` to test Stage-2 consumers immediately.
   - `ajar chain propose --steps <fnd|clm|prim|anom,...>` auto-inherits stored micropatches (with optional `StageContext` helpers), runs full chain + benign control (`AJAR_ABLATE_STEPS=""`) + per-step marginal ablation, and marks resolved `parked_doors` / `crown_jewels`.
3. **Stage C — Hardened 9-Arm Production Patch Gate (`ajar phase advance --to remediate` + `ajar patch verify`):**
   - Preserves `.o` objects across resets (`--suite-timeout 1800`), runs Arms 1–4, Arm 5 (cached `baseline_suite.json` diff), Arm 6 (`>= 3` variants with `>= 1` firing on clean `HEAD`), Arm 7 (`--caller-audit`), Arm 8 (`--sibling-audit`), and Arm 9 (`git apply -R` revert re-failure proof), setting `remediation_state = 'verified_local'`.

---

## 5. Deterministic SQL Closeout Gates (`ajar/gates.py`)

- **`G1` (Surface, Priority Task, & Crown-Jewel Stopping Gate):** Under `exhaustive-high`, requires `>= 1` mapped surface, `0` open/leased `critical`/`high` tasks, and `>= 1` completed task per `critical`/`high` surface. Under `crown-jewel`, multi-step `stepping_stone` Highs never short-circuit discovery; the gate passes either when a `crown_jewel` finding/chain lands (with zero open `critical` verification tasks) or when all mapped surfaces and bounded `bridge` hunts exhaust cleanly.
- **`G2` (Zero Unresolved Claims):** Zero claims remain in `proposed`, `survived_falsify`, `needs_instrumentation`, or `config_gated` with an open/leased override probe.
- **`G3` (Causal Proof, Challenger Separation, & Release UB Gate):** Every `findings` row has passing 4-arm JSON receipts, `proposer_worker_id != falsifier_worker_id`, and zero `critical`/`high` findings classified as `debug_assert_only`.
- **`G4` (First-Principles Quota, Anti-Premature-`dry`, & Strict `env_blocker` Gate):** Enforces `zero_skill` quota, verified `dry` guard loci, blocks premature `dry` closure when an active (`status != 'dry'`) unchained guarded primitive lacks completed guard-break verification, and rejects policy/safety-withheld `blocked` claims.
- **`G5` (Orphaned Anomaly, Ready Open Door, & Stage-5 Converge Completeness):** Zero `unexplained` anomalies or unresolved `ready` Open Doors remain, and when `>= 2` active composable signals exist, at least one Stage-5 `chain` task has completed.

---

## 6. Internal Package Layering, Zero-Cycle DAG, Guardrails, & DST (`ADR-0023`..`ADR-0024`)

To prevent CLI/MCP drift, silent state-machine corruption, import cycles, and prose-only conventions, `ajar/` follows a strict acyclic DAG enforced mechanically in CI:

```text
ajar/domain/ & ajar/redact.py & ajar/repro_helpers.py   (pure zero-IO StrEnums, models, self-healing transitions, leaves)
     ▲
ajar/store/                                             (tx.py, migrations.py, util.py: immediate_tx, SCHEMA_SQL, open_run_db)
     ▲
ajar/epistemic_hooks.py -> ajar/chain_planner.py -> ajar/db.py -> ajar/reactions.py
     ▲
ajar/services/                                          (workflow.py unified transactional mutations; proof.py DEC-0132 & P0-3)
     ▲
ajar/cli/ & ajar/mcp.py                                 (thin modular CLI package & STDIO-MCP adapter; 0 raw SQL writes)
```

- **Atomic Transactional Services & Self-Healing Errors (`ajar/services/workflow.py`, `ajar/domain/`, `ajar/mcp.py`):** Every workflow mutation acquires `immediate_tx(conn)` (`BEGIN IMMEDIATE` / nested `SAVEPOINT`, never held across subprocesses), checks `assert_run_mutable`, and enforces `ALLOWED_*_TRANSITIONS` + `derive_claim_axes`. `InvalidTransitionError` includes `allowed_targets` and `fix_hint`, MCP `tools/call` returns structured JSON error payloads, `ajar swarm packet` embeds scrubbed claim/task records directly (no raw SQL query instructions), `ajar/hooks.py` evaluates a semantic progress tuple ignoring telemetry noise, and `ajar doctor --run <id> [--prune-slots]` audits SQLite integrity, stale leases, and lock-safe slot cleanup.
- **Mechanical Guardrails (`tools/arch_lint.py` + CI):** Enforces 10 rules (`NO_RAW_SQL_IN_MCP`, `CLI_RAW_SQL_RATCHET` locked at `0`, `LAYER_DAG_BOUNDARY`, `ZERO_LLM_ENGINE`, `NO_HARDCODED_DEVBOX_PATH`, `NO_AMBIENT_ENV_MUTATION`, `NO_UNFILTERED_TAR_EXTRACT`, `NO_COMMIT_NOOP`, `MULTI_WRITE_REQUIRES_IMMEDIATE_TX`, and Tarjan SCC `NO_CIRCULAR_IMPORTS`), emitting self-healing `fix_hint` messages. CI runs `ruff` (`E,F,I,W,B`), `tools/arch_lint.py`, universal `mypy --strict ajar tools/arch_lint.py`, CLI-vs-Docs/Skills conformance checks, and full `pytest -q`.
- **Deterministic Simulation Testing & Verification Driver (`tests/dst/test_state_machine_sim.py`, `scripts/verify-repo.sh`):** Seeded multi-worker DST (`AJAR_DST_SEED=<n>` for exact replay) asserts 10 global invariants plus dedicated checks for the 2-strike instrumentation pivot, primitive-to-door wakeup and multi-hop percolation, `diff_sync` `build_cmd` carry-forward, and 2-connection WAL contention under `immediate_tx`. Contributors run `scripts/verify-repo.sh --fast` (`~10s` inner loop) during iteration and `scripts/verify-repo.sh --full` before opening a PR.
- **Startup Proof Helpers (`ajar/services/proof.py`):** `ajar economics export` exports read-only, strictly advisory `DEC-0132` COGS/LoC calibration telemetry (`ajar-economics-calibration/1`), and `ajar ledger commit-preimage` produces redacted `P0-3` SHA-256 commit-before-submit records with atomic symlink-refusing `0o600` preimage files and stdout isolation.

