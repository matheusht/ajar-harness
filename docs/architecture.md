# Ajar v3.1 Architecture

**Ajar** (built by **Ajar Labs**) is a zero-LLM deterministic verification engine (`ajar/`) paired with ASD-STE100 workflow skills (`skills/`) for `Platform`, `Code`, `Fixes`, `Security reviews`, and `Supply chain`.

Ajar never calls an LLM API inside its core state, gate, graph, or reproduction modules. Agents supply hypotheses, minimal patches, and exploit scripts; `ajar` enforces state transitions, workspace isolation, locus-bound 4-arm causal proof, 8-arm production patch verification, secret redaction, and SQL closeout gates.

---

## 1. Dual-Mode Execution, Discovery Funnel, and Model Routing (`D-01`, `D-10`, `ADR-0018`)

Both operating modes share the same SQLite WAL database (`run.db`), CLI commands, and closeout gates:

1. **Host Mode (Interactive Subscription Agents):**
   - Driven by Claude Code, Codex CLI, Antigravity, OpenCode, or any MCP client via `ajar <subcommand>` or `ajar mcp`.
   - **Session Persistence:** `ajar hook claude-stop --if-active` and `ajar loop codex|omp` evaluate SQL gates `G1–G5` when an agent attempts to stop. If gates remain unmet, the hook blocks exit (`rc=2`) and returns the unmet blockers, guarded by a **3-stall circuit breaker** (`MAX_CONSECUTIVE_STALLS = 3`).
2. **Standalone Mode (`ajar run`):**
   - `ajar run <target> [--cogs-cap <USD>] --workers <N> --discover-passes <K>` dispatches bounded explore, falsify, reproduce, chain, and patch workers against `run.db`.
   - **Keep-Biased `Best-of-N` Discovery -> Kill-Biased Funnel:** `--discover-passes K` seeds bi-directional exploration passes across `outside_in`, `inside_out`, `native_ffi`, and `peer_symmetry` before independent `falsify` and locus-bound `reproduce` kill false positives.
   - **Role-Tier Model Routing & Refusal Fallback:** `select_model_for_task` routes deep architectural reasoning (`map`, `chain`, `patch`, `falsify`, and `zero_skill` `investigate`) to `AJAR_MODEL_REASON`, mechanical search/PoC tasks (`domain` `investigate`, `reproduce`, `instrument`) to `AJAR_MODEL_HUNT`, and automatically retries safety-refused prompts once on `AJAR_MODEL_FALLBACK`.
   - **Dry-Surface Token Breaker & 80/20 Verify Reserve:** Spending `> 25%` of `cogs_cap_usd` on a single surface in `explore` phase with `0` anomalies, `0` primitives, and `0` claims throttles remaining open `investigate` tasks on that surface to `conditional_blocked`. Spending `>= 80%` of total budget transitions the run to `verify_only`.

---

## 2. Workspace Geometry and Symlink Safety (`D-04`)

All run state lives outside the target tree under `~/.ajar/runs/<run_id>/`:

```text
~/.ajar/runs/<run_id>/
├── run.db                 # SQLite WAL database (busy_timeout = 30000 ms)
├── repo.git/              # Bare-shared git clone of source target
├── env/                   # Default --envelope working directory (AGENTS.md + skills/ + target/)
├── worktrees/slot-<k>/    # Isolated 4-arm and 8-arm reproduction worktrees
└── caches/cache-<k>/      # Per-slot build caches (CARGO_TARGET_DIR, GOCACHE, FOUNDRY_OUT)
```

File reads and state writes enforce `O_NOFOLLOW` / path-containment checks, and every string written to `run.db` passes through `ajar.redact.scrub_text`.

---

## 3. SQLite WAL State Model (`D-02`, `D-07`, `D-13`, `ADR-0018`)

`ajar/db.py` separates **Work**, **Long-Horizon Memory**, **Truth**, **Platform Graph**, and **Economics**:

### Work Axis
- `surfaces` & `surface_drivers`: Mapped entrypoints, trust boundaries, and executable harnesses.
- `tasks`: Prioritized work items (`map`, `investigate`, `falsify`, `reproduce`, `instrument`, `chain`, `patch`) with `direction` (`outside_in`, `inside_out`, `native_ffi`, `peer_symmetry`), statuses `open -> leased -> done | dry | conditional_blocked`, TTL recovery, `skill_mode` (`domain` vs `zero_skill`), and `salience_score`.
- `steers`: Attributable operator threat-model and scope rules (`scope` in `global|subsystem|path`, `touch_kind` in `scope_authority|research_steering`).

### Long-Horizon Memory & Prefix-Stable Context Axis
- `anomalies`: Durable observations (`unexplained`, `benign_explained`, `consumed_by_claim`, `consumed_by_chain`). Falsifying a claim restores its linked anomaly to `unexplained`.
- `primitives`: Verified bounded capabilities (`preconditions`, `postconditions`, `guarded_by_locus`, `guard_assumption`, `evidence_cmd`).
  - **Anti-Premature-`dry` Gate:** `check_guarded_primitive_dry_block` rejects `ajar task dry` when an unchained guarded primitive on the same surface/subsystem still awaits guard-break testing.
- `certified_bindings`: Line-hashed verified code constants (`file_sha256`, `valid`).
- **Prefix-Stable `< 4 KB` Context (`render_task_context`):** Places run-invariant sections (`Goal`, `Active Workspace Steers`, name-sorted `Certified Bindings`) at the exact top of every prompt so multi-worker calls hit LLM KV prompt caches, followed by the task-specific delta at the tail (`<= 50` lines, `< 4096` bytes).

### Truth & Remediation Axis
- `claims`: Hypotheses carrying mandatory `falsification_prediction` and `falsification_test`, progressing through `proposed -> survived_falsify | falsified -> reproduced | needs_instrumentation | rejected_repro | duplicate_root_cause | blocked`, plus `ajar claim rescope` when locus, preconditions, or severity shift during disconfirmation or `claim_mismatch`.
- `findings`: Created exclusively by `ajar claim reproduce` after all 4 arms + causal locus alignment pass (`remediation_state = 'micropatched'`).
- `patch_verifications`: Created by `ajar patch verify` after all **8 production arms** pass, promoting `claims.remediation_state` to `'maintainer_patched'`.
- `chains`: Stage-5 `Converge` end-to-end verified multi-stage exploit compositions (`step_ids_json`, `e2e_poc_cmd`, `control_cmd`, `verified`).

### `Platform` Graph & `Code` Unit Economics (`ADR-0018`)
- `ajar export-graph` (`ajar/graph.py`): Compiles `surfaces`, `repomap_edges`, `primitives`, `anomalies`, `findings`, `chains`, `dry` guards, and active `steers` into a deterministic `ajar-platform-graph/1` JSON feed.
- `ajar quote` & `35%` COGS Cap: `compute_quote_summary` sizes full repositories or PR diffs (`--diff <base..head>`) at `$0.05 / LoC` (`$25` floor, `$2,500` self-serve cap) and sets default commercial `cogs_cap_usd = 0.35 * code_quote_usd` (`>= 65%` gross margin floor), while allowing explicit `--cogs-cap` / `--budget` overrides on bounty hunts.

---

## 4. Two-Stage Verification: 4-Arm Discovery & 8-Arm `Fixes` (`D-05`, `D-06`, `ADR-0018`)

### Stage A: Locus-Bound 4-Arm Reproduction (`ajar claim reproduce`)

| Target Mode | Arm 1 (Clean + PoC) | Arm 2 (Clean + Control) | Arm 3 (Guard/Fix + PoC) | Arm 4 (Guard/Fix + Control) |
| --- | --- | --- | --- | --- |
| **`source`** (`ajar/repro_source.py`) | Exploit PoC fires assertion/sanitizer on unmodified worktree | Benign control passes on unmodified worktree | `1–5` line production `micropatch` overlapping `claim.locus` (`±60` lines) blocks PoC | Benign control passes with `micropatch` applied |
| **`binary`** (`ajar/repro_binary_live.py`) | PoC hits consistent ASLR-normalized PC/signal; ablated input does not | Benign control exits cleanly | Runtime preload/wrapper guard blocks crash/corruption | Benign control exits cleanly under runtime guard |
| **`live`** (`ajar/repro_binary_live.py`) | Seed Principal A `ajar_canary_<32hex>`; Principal B PoC leaks/mutates canary | Principal B benign control does not leak/mutate canary | Principal A authorized request succeeds (`200` + canary) | Mandatory `--teardown-cmd` removes canary (`404`/absent verified) |

If a `source` micro-patch modifies files or lines outside `claim.locus` (and `--shared-guard-locus`), `validate_micropatch_diff` rejects it with `claim_mismatch:` so agents cannot confirm a misdiagnosed hypothesis with an unrelated patch.

### Stage B: 8-Arm Production Patch Gate (`ajar patch verify`)

Before promoting `remediation_state` from `micropatched` to `maintainer_patched`, `ajar/patch_verify.py` verifies:
1. **Arms 1–4:** Clean/Patched PoC and Control contrast plus `finding.locus` overlap.
2. **Arm 5 (`--suite-cmd`):** Full project test suite exits `0` on the patched worktree.
3. **Arm 6 (`--variant-cmd`, `>= 3`):** At least 3 distinct bypass variants fail to trigger the exploit oracle on the patched worktree.
4. **Arm 7 (`--caller-audit`):** Documented caller NULL/error-return safety check (`GhostLock` regression guard).
5. **Arm 8 (`--sibling-audit`):** Documented sibling-route and peer-hook symmetry audit.

---

## 5. Deterministic SQL Closeout Gates (`D-03`, `ADR-0018`)

`ajar gate check` and `ajar finish` evaluate five SQL invariants in `ajar/gates.py`:

- **`G1` (Surface & Priority Task Coverage):** Under `exhaustive-high`, at least one surface is mapped, zero `critical`/`high` tasks remain `open` or `leased`, and every `critical`/`high` surface has at least one `done` or `dry` task.
- **`G2` (Zero Unresolved Claims):** Zero claims remain in `proposed`, `survived_falsify`, or `needs_instrumentation`.
- **`G3` (Causal Proof & Challenger Separation):** Every `findings` row has passing 4-arm JSON receipts and its parent claim satisfies `proposer_worker_id != falsifier_worker_id`.
- **`G4` (First-Principles Quota & Anti-Premature-`dry`):** `zero_skill_leases >= 1` whenever `>= 2` distinct workers leased tasks, every `dry` task cites an existing target `file:line` locus plus `>= 15`-character guard explanation, and zero unchained guarded primitives (`guarded_by_locus != ''`) were prematurely closed `dry`.
- **`G5` (Orphaned Anomaly & Stage-5 Converge Completeness):** Zero `unexplained` anomalies remain, and when `>= 2` composable signals or any guarded primitive exist, at least one Stage-5 `Converge` (`chain`) task has completed.
