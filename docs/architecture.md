# Ajar v3.2 Architecture

**Ajar** (built by **Ajar Labs**) is a zero-LLM deterministic verification engine (`ajar/`) paired with ASD-STE100 workflow skills (`skills/`) for `Platform`, `Code`, `Fixes`, `Security reviews`, and `Supply chain`.

Ajar never calls an LLM API inside its core state, gate, graph, or reproduction modules. Agents supply hypotheses, minimal patches, and exploit scripts; `ajar` enforces state transitions, event-driven epistemic micro-hooks, workspace isolation, locus-bound causal proof, 9-arm production patch verification, secret redaction, and SQL closeout gates.

---

## 1. Dual-Mode Execution, Discovery Funnel, and Model Routing (`ADR-0017`..`ADR-0019`)

Both operating modes share the same SQLite WAL database (`run.db`), CLI commands, and closeout gates:

1. **Host Mode (Interactive Subscription Agents):**
   - Driven by Claude Code, Codex CLI, Antigravity, OpenCode, or any MCP client via `ajar <subcommand>` or `ajar mcp`.
   - **Session Persistence:** `ajar hook claude-stop --if-active` and `ajar loop codex|omp` evaluate SQL gates `G1–G5` when an agent attempts to stop. If gates remain unmet, the hook blocks exit (`rc=2`) and returns the unmet blockers, guarded by a **3-stall circuit breaker** (`MAX_CONSECUTIVE_STALLS = 3`).
2. **Standalone Mode (`ajar run`):**
   - `ajar run <target> [--cogs-cap <USD>] --workers <N> --discover-passes <K>` dispatches bounded explore, falsify, reproduce, chain, escalate, and patch workers against `run.db`.
   - **Keep-Biased `Best-of-N` Discovery -> Kill-Biased Funnel:** `--discover-passes K` seeds bi-directional exploration passes across `outside_in`, `inside_out`, `native_ffi`, and `peer_symmetry` before independent `falsify` and locus-bound `reproduce` kill false positives.
   - **Role-Tier Model Routing, Anti-Soliloquy Guard, & Refusal Fallback:** `select_model_for_task` routes deep architectural reasoning (`map`, `chain`, `patch`, `falsify`, `escalate`, and `zero_skill` `investigate`) to `AJAR_MODEL_REASON`, mechanical search/PoC tasks (`domain` `investigate`, `reproduce`, `instrument`) to `AJAR_MODEL_HUNT`, flags fabricated shell/gdb transcripts via `detect_soliloquy_transcript`, and retries safety-refused prompts once on `AJAR_MODEL_FALLBACK`.
   - **Dry-Surface Token Breaker & 80/20 Verify Reserve:** Spending `> 25%` of `cogs_cap_usd` on a single surface in `explore` phase with `0` anomalies, `0` primitives, and `0` claims throttles remaining open `investigate` tasks on that surface to `conditional_blocked`. Spending `>= 80%` of total budget transitions the run to `verify_only` (`falsify`, `reproduce`, `chain`, `escalate`).

---

## 2. Workspace Geometry, Helpers Runtime, and Sandboxing (`D-04`, `ADR-0019`)

All run state lives outside the target tree under `~/.ajar/runs/<run_id>/`:

```text
~/.ajar/runs/<run_id>/
├── run.db                           # SQLite WAL database (busy_timeout = 30000 ms)
├── workspace/                       # Default --envelope working directory (read-only target/)
└── repro/
    ├── repo.git/                    # Bare-shared git clone of source target
    ├── baseline_suite.json          # Cached clean-HEAD test suite baseline for Arm 5 diffing
    ├── helpers/                     # Read-only (0444) StageContext, sitecustomize.py, ajar_helpers/
    ├── slot-<k>/                    # Isolated 4-arm, chain-ablation, and 9-arm patch worktrees
    ├── slot-inst/                   # Isolated scratch worktree for `ajar claim instrument`
    └── cache-<k>/                   # Per-slot build caches (CARGO_TARGET_DIR, GOCACHE, pycache)
```

When `unshare -rn` is unavailable in unprivileged containers, `_run_shell_in_slot` sets `AJAR_BLOCK_EXTERNAL_NET=1`, scrubs proxy variables, and loads `repro/helpers/sitecustomize.py` to block non-loopback `AF_INET`/`AF_INET6` sockets while permitting `127.0.0.1` / `::1` test servers.

---

## 3. SQLite WAL State Model & Event-Driven Epistemic Hooks (`ADR-0018`, `ADR-0019`)

`ajar/db.py` and `ajar/epistemic_hooks.py` coordinate **Work**, **Epistemic Hooks**, **Long-Horizon Memory**, **Truth**, **Platform Graph**, and **Economics**:

### Work & PR Differential Axis
- `surfaces` (`requires_tags_json`) & `surface_drivers`: Mapped entrypoints, required capability tags, trust boundaries, and executable harnesses.
- `tasks`: Prioritized work items (`map`, `investigate`, `falsify`, `reproduce`, `instrument`, `chain`, `patch`, `escalate`) with `direction`, statuses `open -> leased -> done | dry | conditional_blocked`, `checkpoint_json` (`ajar task checkpoint`), and `diff_state` (`kept | closed | invalidated_guard | new` via `ajar init --diff <base..head> --parent-run <id>`).
- `coverage_spans`: SHA-bound source line spans audited per task (`ajar coverage record`).
- `steers`: Attributable operator threat-model and scope rules (`scope_authority` vs `research_steering`).

### Event-Driven Epistemic Hooks & Capability Bridges (`ajar/epistemic_hooks.py`)
- **Zero-Overhead Default:** Plain code with no triggered state or AST signal injects `0` hook tokens.
- **Bounded `H1`–`H8` Micro-Hooks (`epistemic_hooks`):** Triggered deterministically by SQLite state transitions (`H1_GUARD_SYMMETRY`, `H4_TYPED_STATE_BRIDGE`, `H5_POST_CONFIRM_ESCALATION`, `H6_RELEASE_UB_DIFF`) or lightweight AST/source signals (`H2_DIRTY_UNWIND`, `H3_INTRINSIC_AND_PEER_SINK`, `H7_TRUST_METADATA_AND_FSM_ORDER`, `H8_PROJECTION_UNDER_CONSTRAINT`). Capped at `<= 2` active hooks (`<= 90` tokens) in `Task Delta`, each paired with a mandatory 1-line `Kill Rule` and `max_leases` auto-expiry.
- **Cross-Subsystem Capability Bridge:** Matches `primitives.provides_tags_json` against `primitives.requires_tags_json` and `surfaces.requires_tags_json` across subsystems to surface upstream providers and enqueue Stage-5 `chain` tasks.

### Long-Horizon Memory & Prefix-Stable Context Axis
- `anomalies`, `primitives`, `primitive_helpers`, and `certified_bindings` (`[UNTRUSTED_TARGET_DOC]` FTS5 provenance tags distinguish target docs from code).
- **Prefix-Stable `< 4 KB` Context (`render_task_context`):** Keeps the `Certified Run Prefix` (`Goal`, `Active Workspace Steers`, sorted `Certified Bindings`) 100% byte-identical across workers while placing `Trajectory Checkpoint`, `Cross-Subsystem Capability Bridges`, and `Active Epistemic Hooks` inside the `Task Delta` tail.

### Truth & Remediation Axis
- `claims`: Progress through `proposed -> survived_falsify | falsified | config_gated -> reproduced | needs_instrumentation | rejected_repro | duplicate_root_cause | blocked`, plus `ajar claim rescope` and `ajar claim instrument`.
- `findings`: Created exclusively by `ajar claim reproduce` after all reproduction arms and causal locus alignment pass (`ub_divergence_class` recorded when `--release-cmd` runs).
- `chains`: Verified inside `repro/slot-<k>` with automated $N$-step causal ablation (`ablation_matrix_json`).
- `patch_verifications`: Created by `ajar patch verify` after all **9 hardened production arms** pass (`remediation_state = 'maintainer_patched'`).

---

## 4. Verification Stages: Reproduction, Composable Chains, & 9-Arm `Fixes` (`ADR-0019`)

1. **Stage A — Locus-Bound Reproduction (`ajar claim reproduce`):**
   - `source`: Arms 1–4 (`clean+PoC`, `clean+control`, `micropatch+PoC`, `micropatch+control` overlapping `claim.locus`) + optional Arms `5A`/`5B` (`--release-cmd` / `--release-control-cmd` classifying `consistent | silent_wrap_escalated | debug_assert_only | trap_dos_only` and blocking `debug_assert_only` on `critical`/`high`).
   - `binary` & `live`: ASLR-normalized PC/ablation/guard (`binary`) and 128-bit CSPRNG canary + teardown (`live`).
2. **Stage B — Composable Chain Ablation (`ajar primitive promote-helper` + `ajar chain propose`):**
   - Dual-mode-verifies Python `StageContext` helpers and mounts them read-only (`0444`) in `repro/helpers/ajar_helpers/` outside `slot-<k>`.
   - Runs full chain + benign control + per-step marginal ablation (`AJAR_ABLATE_STEPS` or `--step-micropatch <step_id>:<diff>`), rejecting redundant padding steps.
3. **Stage C — Hardened 9-Arm Production Patch Gate (`ajar patch verify`):**
   - Arms 1–4 (locus-bound PoC/control contrast), Arm 5 (`--suite-cmd` diffed against cached clean-`HEAD` `baseline_suite.json`), Arm 6 (`>= 3` distinct `--variant-cmd` tests where `>= 1` fires on clean `HEAD`), Arm 7 (`--caller-audit` + optional `--caller-cmd`), Arm 8 (`--sibling-audit` + optional `--sibling-cmd`), and **Arm 9 (`git apply -R` patch-revert re-failure proof)**.

---

## 5. Deterministic SQL Closeout Gates (`ajar/gates.py`)

- **`G1` (Surface & Priority Task Coverage):** Under `exhaustive-high`, at least one surface is mapped, zero `critical`/`high` tasks remain `open` or `leased`, and every `critical`/`high` surface has at least one completed task.
- **`G2` (Zero Unresolved Claims):** Zero claims remain in `proposed`, `survived_falsify`, `needs_instrumentation`, or `config_gated` with an open/leased override probe.
- **`G3` (Causal Proof, Challenger Separation, & Release UB Gate):** Every `findings` row has passing 4-arm JSON receipts, `proposer_worker_id != falsifier_worker_id`, and zero `critical`/`high` findings classified as `debug_assert_only`.
- **`G4` (First-Principles Quota & Anti-Premature-`dry`):** Enforces `zero_skill` quota, verified `dry` guard loci, and blocks premature `dry` closure when an unchained guarded primitive lacks completed guard-break verification on its `guarded_by_locus`.
- **`G5` (Orphaned Anomaly & Stage-5 Converge Completeness):** Zero `unexplained` anomalies remain, and when `>= 2` composable signals or any guarded primitive exist, at least one Stage-5 `chain` task has completed.
