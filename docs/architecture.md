# Ajar v3.4 Architecture

**Ajar** (built by **Ajar Labs**) is a zero-LLM deterministic verification engine (`ajar/`) paired with ASD-STE100 workflow skills (`skills/`) for `Platform`, `Code`, `Fixes`, `Security reviews`, and `Supply chain`.

Ajar never calls an LLM API inside its core state, gate, graph, catalog, planner, or reproduction modules. Agents supply hypotheses, minimal patches, and verification scripts; `ajar` enforces state transitions, multi-agent EV lead voting, per-root plateau breakers, suspended Open Doors, backward sink-to-source call slicing, multi-hop middle-unicorn percolation, event-driven epistemic micro-hooks, stage-split swarm wire profiles, workspace isolation, fail-closed locus-bound causal proof, 9-arm production patch verification, secret redaction, atomic bundle sealing, and SQL closeout gates.

---

## 1. Dual-Mode Execution, Campaign Phases, and Swarm Dispatch (`ADR-0017`..`ADR-0025`)

Both operating modes share the same SQLite WAL database (`run.db`), CLI commands, and closeout gates:

1. **Host Mode (Interactive Subscription Agents & Stage-Split Swarms):**
   - Driven by Claude Code, Codex CLI, Antigravity, OpenCode, or any MCP client via `ajar <subcommand>` or `ajar mcp`.
   - **Hunt vs. Remediate Campaign Phase Split (`ajar phase`):** Runs initialize in `campaign_phase = 'hunt'`, blocking 9-arm `ajar patch verify` and skipping `patch` task leases until `ajar phase advance --to remediate` (which enforces `G5` chain convergence and zero open `critical` hunt/chain/verify tasks unless `--force --notes <reason>` records an explicit operator override).
   - **Multi-Agent Expected-Value Lead Voting & Per-Root Plateau Breaker (`ajar lead`, `ajar map --unvisited`):** Swarm scouts vote on surfaces, Open Doors, slices, chains, or subsystems (`ajar lead vote`, `ajar lead rank`), boosting consensus high-EV tasks while `compute_root_plateau_throttles` (`ajar lead throttles`) applies `-35` salience to post-reproduction non-chain churn on already-reproduced files and `ajar map --unvisited` surfaces unaudited call slices.
   - **Stage-Split `"Swarm Worker"` Dispatch & Portfolio Lanes (`ajar swarm`):** `ajar swarm packet --stage <investigate|bridge|falsify|reproduce|chain|portfolio>` emits compact (`<= 45`-line) `direct` worker packets ordering `portfolio` claims by severity. If an upstream classifier blocks a subagent, `ajar swarm fallback <dispatch_id>` steps down `direct -> swarm_patch_first -> regression_tdd` (using boundary-invariant conformance framing on non-reproduction stages).
   - **Session Persistence & Honest Early Closeout (`ajar hook`, `ajar close`):** `ajar hook claude-stop --if-active` and `ajar loop codex|omp` evaluate SQL gates `G1–G5` when an agent attempts to stop (`MAX_CONSECUTIVE_STALLS = 3`). Operators stopping a run before `G1–G5` complete run `ajar close --reason <stopped_by_operator|window_reached|superseded> --notes "<why>"` instead of claiming `all_gates_passed`.
2. **Standalone Mode (`ajar run`):**
   - `ajar run <target> [--until exhaustive-high|first-verified-high|crown-jewel] [--phase hunt|remediate] [--cogs-cap <USD>] --workers <N> --discover-passes <K>` dispatches bounded explore, bridge, falsify, reproduce, chain, escalate, and patch workers against `run.db`.
   - **Keep-Biased `Best-of-N` Discovery -> Kill-Biased Funnel:** `--discover-passes K` seeds bi-directional exploration passes across `outside_in`, `inside_out`, `native_ffi`, and `peer_symmetry` before independent `falsify` and locus-bound `reproduce` kill false positives.
   - **Role-Tier Model Routing, Anti-Soliloquy Guard, & Refusal Fallback:** `select_model_for_task` routes deep architectural reasoning (`map`, `chain`, `bridge`, `patch`, `falsify`, `escalate`, and `zero_skill` `investigate`) to `AJAR_MODEL_REASON`, mechanical search/PoC tasks (`domain` `investigate`, `reproduce`, `instrument`) to `AJAR_MODEL_HUNT`, flags fabricated shell/gdb transcripts via `detect_soliloquy_transcript`, and retries safety-refused prompts once on `AJAR_MODEL_FALLBACK`.
   - **Dry-Surface Token Breaker & 80/20 Verify Reserve:** Spending `> 25%` of `cogs_cap_usd` on a single surface in `explore` phase with `0` anomalies, `0` primitives, and `0` claims throttles remaining open `investigate` tasks on that surface to `conditional_blocked`. Spending `>= 80%` of total budget transitions the run to `verify_only` (`falsify`, `reproduce`, `chain`, `escalate`).

---

## 2. Workspace Geometry, Post-State Snapshots, and Cross-VM Reopen (`D-04`, `ADR-0019`..`ADR-0025`)

Run state lives outside the target tree under `~/.ajar/runs/<run_id>/`, paired with local SSD build caches (`/tmp/ajar-build-cache/<run_id>/`) and compact shared ledger mirroring (`/shared/user/.gemini/ajar/runs/<run_id>/`):

```text
~/.ajar/runs/<run_id>/
├── run.db                           # SQLite WAL database (busy_timeout = 30000 ms; auto-migrated via _ensure_v34_schema)
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
    └── slot-inst/                   # Isolated scratch worktree for `claim instrument`
```

- **Hybrid Storage, Harness Code-Hash Binding, & Cross-VM `ajar reopen`:** Heavy `CARGO_TARGET_DIR`, `GOCACHE`, and `CCACHE_DIR` trees stay on local SSD `/tmp/ajar-build-cache/<run_id>` while `_clean_slot_preserving_objects` retains compiled `.o`/`.a` files across both 4-arm and 9-arm resets via monotonic `mtime` bumps. `ajar init` binds `runs.harness_sha256` across `ajar/**/*.py` so `ajar doctor --run` and `ajar report` flag `harness_modified_mid_run` if engine files are edited mid-campaign. `ajar reopen <run_id>` hydrates `~/.ajar/runs/<run_id>` from `/shared/user/.gemini/ajar/runs/<run_id>`, upgrades `v3.1..v3.3` tables in-place, reconstructs missing `target_path` checkouts offline from `repro/repo.git`, and resets zero-attempt `blocked` claims to `survived_falsify`.
- **Toolchain Scrubbing & Container Loopback Guard:** `scrubbed_subprocess_env` strips host credentials while preserving `SDKROOT` (and cached macOS `xcrun`), `DEVELOPER_DIR`, `PKG_CONFIG_PATH`, `.cargo/bin` + rustup toolchain `bin` (`CARGO_NET_OFFLINE=true`), `$AJAR_RUN_DIR`, and `$AJAR_ARTIFACTS_DIR`. `_run_shell_in_slot` sets `AJAR_BLOCK_EXTERNAL_NET=1` and loads `repro/helpers/sitecustomize.py` to block non-loopback `AF_INET`/`AF_INET6` sockets.

---

## 3. SQLite WAL State Model, Unified Catalog, Open Doors, & Percolation (`ADR-0018`..`ADR-0025`)

`ajar/store/`, `ajar/catalog.py`, `ajar/db.py`, `ajar/chain_planner.py`, `ajar/epistemic_hooks.py`, and `ajar/reactions.py` coordinate **Work**, **Lead Voting**, **Unified Catalog**, **Suspended Open Doors**, **Percolation**, **Epistemic Hooks**, **Truth**, and **Economics**:

### Work, EV Salience, Portfolio Anti-Starvation, & PR Differential Axis
- `surfaces` (`requires_tags_json`), `surface_drivers`, & `lead_votes`: Mapped entrypoints, required capability tags, trust boundaries, executable harnesses, and multi-worker Expected-Value votes (`ajar lead {vote,rank,throttles}`).
- `tasks` & `swarm_dispatches`: Prioritized work items (`map`, `investigate`, `bridge`, `falsify`, `reproduce`, `instrument`, `chain`, `patch`, `escalate`) with `KIND_SALIENCE_FLOORS`, consensus EV boosts, per-root plateau throttling, `checkpoint_json`, and `diff_state`. `lease_next_task` prioritizes woken `chain` tasks (`salience >= 96`), interleaves greenfield `investigate` ahead of `bridge` whenever `leased_bridges >= 2`, and skips `patch` tasks while `campaign_phase == 'hunt'`.
- `coverage_spans` & `steers`: SHA-bound source line spans (`ajar coverage record`, feeding `ajar map --unvisited`) and attributable operator rules (`scope_authority` vs `research_steering`).

### Unified Issue & Gadget Catalog, Open Doors, & Multi-Hop Percolation (`ajar/catalog.py`, `ajar/chain_planner.py`)
- `ajar catalog search` & `ajar catalog backslice`: Normalizes findings, capabilities, `trust_gadget` transitions, candidate claims, unexplained anomalies, and Open Doors into one queryable catalog, synthesizing 1-hop `composable_pairs` and walking `repomap_edges` backward (`callee <- caller`) from any Crown Jewel, Open Door, locus, or symbol while surfacing `unvisited_caller_files`.
- `crown_jewels`, `parked_doors`, & `door_fts`: Suspended deep sinks or partial chains (`ajar door park`) spawning `<= 2` bounded `bridge` tasks and waking reactively (`-> ready`) via tri-modal matching.
- **Multi-Hop Percolation & Trust Gadgets:** `detect_percolated_multi_hop_paths` keeps `surfaces` active alongside `crown_jewels`, enqueuing `salience = 98` `chain` tasks when a middle link connects an entry prefix to a sink suffix and ranking 1-link `crown_jewel` `unicorn_gaps` first in `ajar chain frontier`.

### Event-Driven Epistemic Hooks & Prefix-Stable `< 4 KB` Context (`ajar/epistemic_hooks.py`, `ajar/reactions.py`)
- **Bounded `H1`–`H8` Micro-Hooks:** Triggered deterministically by SQLite state transitions (`H1_GUARD_SYMMETRY`, `H4_TYPED_STATE_BRIDGE`, `H5_POST_CONFIRM_ESCALATION` including `stepping_stone` `High -> Critical` escalation, `H6_RELEASE_UB_DIFF`) or AST/source signals (`H2`, `H3`, `H7`, `H8`), capped at `<= 2` active hooks (`<= 90` tokens) with mandatory `Kill Rule` lines.
- **Prefix-Stable `< 4 KB` Context (`render_task_context`):** Keeps the `Certified Run Prefix` (`Goal`, `Active Workspace Steers`, sorted `Certified Bindings`) 100% byte-identical across workers while placing `Open Doors`, `Cross-Subsystem Capability Bridges`, and `Active Epistemic Hooks` inside `Task Delta`.

### Truth & Remediation Axis
- `claims`: Enforces structural prose (`validate_structural_claim_prose`), supports `--same-root-of` and `ajar claim duplicate`, and separates `preflight_error`, `build_or_env_error`, and `micropatch_error` (`0` strikes, `poc_proven`) from `target_negative`.
- `findings`, `finding_corrections`, & `repro_snapshots`: Created by `ajar claim reproduce` with `realism_tier`, persisted `build_cmd`, fail-closed `--save-post-state` snapshots, single-command calibration (`ajar finding calibrate`), and timestamp-ordered projection (`apply_latest_finding_corrections`).
- `chains`: Composes `fnd-*`, `clm-*`, `prim-*`, and `anom-*` directly in `ajar chain propose` with modular `--backup-step` stage swaps, fail-closed step ablation, and `ajar chain calibrate`.
- `patch_verifications`: Created by `ajar patch verify` in `remediate` phase after all **9 hardened production arms** pass (`remediation_state = 'verified_local'`).

---

## 4. Verification Stages: Reproduction, Zero-Boilerplate Chains, & 9-Arm `Fixes` (`ADR-0019`..`ADR-0025`)

1. **Stage A — Strike-Free Smoke Probes & Fail-Closed 4-Arm Reproduction (`ajar repro try`, `ajar claim reproduce`):**
   - `ajar repro try` runs strike-free build/PoC checks inside the shared 8-slot pool (`slot-<k>`).
   - `ajar claim reproduce` enforces `evaluate_precondition_realism`, `validate_entrypoint_fidelity`, and `validate_no_static_source_cheat`, runs `--build-cmd` + Arms 1–4 (`clean+PoC`, `clean+control`, fail-closed `micropatch+PoC`, `micropatch+control`), classifies Arm-3/Arm-4 breakage after passing Arm 1 + Arm 2 as zero-strike `micropatch_error` (`poc_proven=True`), verifies `--save-post-state` exists on disk, and runs optional Arms `5A`/`5B` (`--release-cmd`).
2. **Stage B — Post-State Probing & Modular Multi-Artifact Chain Ablation (`ajar chain probe`, `ajar chain propose`):**
   - `ajar chain probe --from-snapshot <snp_id> [--build-cmd ...]` hydrates a Stage-1 filesystem tarball into `slot-<k>` to test Stage-2 consumers immediately.
   - `ajar chain propose --steps <...> [--backup-step <primary>:<backup>]` auto-inherits stored micropatches, swaps backup steps if primary steps fail, runs benign control (`AJAR_ABLATE_STEPS=""`) + fail-closed per-step marginal ablation, and marks resolved `parked_doors` / `crown_jewels`.
3. **Stage C — Hardened 9-Arm Production Patch Gate (`ajar phase advance --to remediate` + `ajar patch verify`):**
   - Preserves `.o` objects across resets (`--suite-timeout 1800`), runs Arms 1–4, Arm 5 (cached `baseline_suite.json` diff), Arm 6 (`>= 3` variants with `>= 1` firing on clean `HEAD`), Arm 7 (`--caller-audit`), Arm 8 (`--sibling-audit`), and Arm 9 (`git apply -R` revert re-failure proof), setting `remediation_state = 'verified_local'`.

---

## 5. Deterministic SQL Closeout Gates (`ajar/gates.py`)

- **`G1` (Surface, Priority Task, & Crown-Jewel Stopping Gate):** Under `exhaustive-high`, requires `>= 1` mapped surface, `0` open/leased `critical`/`high` tasks, and `>= 1` completed task per `critical`/`high` surface. Under `crown-jewel`, multi-step `stepping_stone` Highs never short-circuit discovery; the gate passes either when a `crown_jewel` finding/chain lands (with zero open `critical` verification tasks) or when all mapped surfaces and bounded `bridge` hunts exhaust cleanly.
- **`G2` (Zero Unresolved Claims):** Zero claims remain in `proposed`, `survived_falsify`, `needs_instrumentation`, or `config_gated` with an open/leased override probe.
- **`G3` (Causal Proof, Challenger Separation, & Release UB Gate):** Every `findings` row has passing 4-arm JSON receipts, `proposer_worker_id != falsifier_worker_id`, and zero `critical`/`high` findings classified as `debug_assert_only`.
- **`G4` (First-Principles Quota, Anti-Premature-`dry`, & Strict `env_blocker` Gate):** Enforces `zero_skill` quota, verified `dry` guard loci, blocks premature `dry` closure when an active (`status != 'dry'`) unchained guarded primitive lacks completed guard-break verification, and rejects policy/safety-withheld `blocked` claims.
- **`G5` (Orphaned Anomaly, Ready Open Door, Nonterminal High Chain, & Stage-5 Converge Completeness):** Zero `unexplained` anomalies, zero unwaived `ready` Open Doors, and zero nonterminal high-salience (`>= 95`) `chain` tasks remain, and when `>= 2` active composable signals exist, at least one Stage-5 `chain` task has completed.

---

## 6. Internal Package Layering, Zero-Cycle DAG, Guardrails, & DST (`ADR-0023`..`ADR-0025`)

To prevent CLI/MCP drift, silent state-machine corruption, import cycles, and prose-only conventions, `ajar/` follows a strict acyclic DAG enforced mechanically in CI:

```text
ajar/domain/ & ajar/redact.py & ajar/repro_helpers.py   (pure zero-IO StrEnums, models, self-healing transitions, leaves)
     ▲
ajar/store/ & ajar/catalog.py                           (tx.py, migrations.py, util.py, read-only catalog & backward slicer)
     ▲
ajar/epistemic_hooks.py -> ajar/chain_planner.py -> ajar/db.py -> ajar/reactions.py
     ▲
ajar/services/                                          (workflow.py unified mutations; proof.py DEC-0132, P0-3, & bundle seal)
     ▲
ajar/cli/ & ajar/mcp.py                                 (thin modular CLI package & STDIO-MCP adapter; 0 raw SQL writes)
```

- **Atomic Transactional Services & Self-Healing Errors (`ajar/services/workflow.py`, `ajar/domain/`, `ajar/mcp.py`):** Every workflow mutation acquires `immediate_tx(conn)` (`BEGIN IMMEDIATE` / nested `SAVEPOINT`, never held across subprocesses), checks `assert_run_mutable`, and enforces `ALLOWED_*_TRANSITIONS` + `derive_claim_axes`. `InvalidTransitionError` includes `allowed_targets` and `fix_hint`, MCP `tools/call` returns structured JSON error payloads, `ajar swarm packet` embeds scrubbed claim/task records directly (no raw SQL query instructions), `ajar/hooks.py` evaluates a semantic progress tuple ignoring telemetry noise, and `ajar doctor --run <id> [--prune-slots]` audits SQLite integrity, `harness_modified_mid_run`, stale leases, and lock-safe slot cleanup.
- **Mechanical Guardrails (`tools/arch_lint.py` + CI):** Enforces 10 rules (`NO_RAW_SQL_IN_MCP`, `CLI_RAW_SQL_RATCHET` locked at `0`, `LAYER_DAG_BOUNDARY`, `ZERO_LLM_ENGINE`, `NO_HARDCODED_DEVBOX_PATH`, `NO_AMBIENT_ENV_MUTATION`, `NO_UNFILTERED_TAR_EXTRACT`, `NO_COMMIT_NOOP`, `MULTI_WRITE_REQUIRES_IMMEDIATE_TX`, and Tarjan SCC `NO_CIRCULAR_IMPORTS`), emitting self-healing `fix_hint` messages. CI runs `ruff` (`E,F,I,W,B`), `tools/arch_lint.py`, universal `mypy --strict ajar tools/arch_lint.py`, CLI-vs-Docs/Skills conformance checks, and full `pytest -q`.
- **Deterministic Simulation Testing & Verification Driver (`tests/dst/test_state_machine_sim.py`, `scripts/verify-repo.sh`):** Seeded multi-worker DST (`AJAR_DST_SEED=<n>` for exact replay) asserts 10 global invariants plus dedicated checks for the 2-strike instrumentation pivot, primitive-to-door wakeup and multi-hop percolation, `diff_sync` `build_cmd` carry-forward, and 2-connection WAL contention under `immediate_tx`. Contributors run `scripts/verify-repo.sh --fast` (`~15s` inner loop) during iteration and `scripts/verify-repo.sh --full` before opening a PR.
- **Proof & Deliverable Sealing Helpers (`ajar/services/proof.py`):** `ajar economics export` exports read-only, strictly advisory `DEC-0132` COGS/LoC calibration telemetry (`ajar-economics-calibration/1`), `ajar ledger commit-preimage` produces redacted `P0-3` SHA-256 commit-before-submit records, and `ajar bundle {seal,verify}` enforces `os.lstat` symlink rejection, two-snapshot writer stability, archive secret/local-path scanning, and atomic `BUNDLE-MANIFEST.json` + `SEAL.sha256` digests.


