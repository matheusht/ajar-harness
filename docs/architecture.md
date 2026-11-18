# Ajar v3 Architecture

Ajar is a zero-LLM deterministic verification engine (`ajar/`) paired with ASD-STE100 workflow skills (`skills/`) for `Code`, `Fixes`, `Security reviews`, and `Supply chain`.

Ajar never calls an LLM API inside its core state, gate, or reproduction modules. Agents supply hypotheses, minimal patches, and exploit scripts; `ajar` enforces state transitions, workspace isolation, 4-arm causal proof, secret redaction, and SQL closeout gates.

---

## 1. Dual-Mode Execution (`D-01`, `D-10`)

Both operating modes share the same SQLite database (`run.db`), CLI commands, and closeout gates:

1. **Host Mode (Interactive Subscription Agents):**
   - Driven by Claude Code, Codex CLI, OpenCode, or any MCP client via `ajar <subcommand>` or the thin STDIO wrapper (`ajar mcp`).
   - **Session Persistence:** `ajar hook claude-stop --if-active` (wired in `.claude/settings.json`) and `ajar loop codex|omp` evaluate SQL gates `G1–G5` when an agent attempts to stop. If gates remain unmet, the hook blocks exit (`rc=2`) and returns the exact unmet blockers. A **3-stall circuit breaker** (`MAX_CONSECUTIVE_STALLS = 3` checks with zero new `events` rows) releases stuck sessions cleanly (`exit_hint = 4`) so loops never spin indefinitely.
2. **Standalone Mode (`ajar run`):**
   - `ajar run <target> --budget <USD> --workers <N>` dispatches bounded explore, falsify, reproduce, chain, and patch workers against `run.db`.
   - **80/20 Verification Reserve:** Spending >= 80% of `budget_usd` transitions the run from `active` to `verify_only`, halting speculative `investigate` leases and reserving the final 20% exclusively for `falsify`, `reproduce`, `chain`, and `patch` tasks.

---

## 2. Workspace Geometry and Symlink Safety (`D-04`)

All run state lives outside the target tree under `~/.ajar/runs/<run_id>/`:

```text
~/.ajar/runs/<run_id>/
├── run.db                 # SQLite WAL database (busy_timeout = 30000 ms)
├── repo.git/              # Bare-shared git clone of source target
├── env/                   # Default --envelope working directory (AGENTS.md + skills/ + target/)
├── worktrees/slot-<k>/    # Isolated 4-arm reproduction worktrees
└── caches/cache-<k>/      # Per-slot build caches (CARGO_TARGET_DIR, GOCACHE, FOUNDRY_OUT)
```

- **`--envelope` (Default):** Places the agent inside `~/.ajar/runs/<run_id>/env/` with Ajar's `AGENTS.md` and a clean checkout at `./target/` so instructions inside an untrusted repository cannot shadow Ajar's verification rules.
- **`--in-place`:** Operates directly against an existing checkout path when build containers or toolchains hardcode absolute paths, while keeping `run.db` in `~/.ajar/runs/<run_id>/` and checking `git status --porcelain` before closeout.
- **Symlink & Secret Hardening:** File reads and state writes enforce `O_NOFOLLOW` / path-containment checks so symlinks inside an untrusted repo cannot redirect reads or writes outside the workspace. Every string written to `run.db` passes through `ajar.redact.scrub_text`.

---

## 3. SQLite WAL State Model (`D-02`, `D-07`, `D-13`)

`ajar/db.py` separates **Work**, **Long-Horizon Memory**, **Truth**, and **Economics**:

### Work Axis
- `surfaces`: Mapped entrypoints (`surface_id`, `name`, `kind`, `subsystem`, `locus`, `priority`, `trust_boundary`, `invariants_json`).
- `surface_drivers`: Executable harnesses (`setup_cmd`, `invoke_template`, `teardown_cmd`, `verified`).
- `tasks`: Prioritized work items (`map`, `investigate`, `falsify`, `reproduce`, `instrument`, `chain`, `patch`) with statuses `open -> leased -> done | dry | conditional_blocked`, TTL lease recovery (`lease_expires_at`), `skill_mode` (`domain` vs `zero_skill`), and integer `salience_score`.

### Long-Horizon Memory Axis
- `anomalies`: Durable observations (`unexplained`, `benign_explained`, `consumed_by_claim`, `consumed_by_chain`). Falsifying a claim leaves its linked anomaly `unexplained` so real crashes or state differentials are never lost when a first hypothesis fails.
- `primitives`: Verified bounded capabilities (`preconditions`, `postconditions`, `evidence_cmd`) available for multi-step exploit composition.
- `certified_bindings`: Line-hashed verified code constants (`file_sha256`, `line_start`, `line_end`, `valid`). `ajar context --task <id>` assembles a `< 4 KB` context frame from valid bindings, relevant anomalies, and surface metadata so workers never re-read full transcripts.
- `pulse`: Periodic sweep (triggered manually via `ajar pulse` or every 8 closed tasks) that flags invalidated bindings, unblocked `conditional_blocked` tasks, and unchained primitives.

### Truth Axis
- `claims`: Hypotheses carrying mandatory `falsification_prediction` and `falsification_test`, progressing through `proposed -> survived_falsify | falsified -> reproduced | needs_instrumentation | rejected_repro | duplicate_root_cause | blocked`. Each claim also tracks four orthogonal dimensions:
  - `research_state`: `candidate | rejected_during_research | confirmed`
  - `evidence_state`: `unverified | falsified | reproduced`
  - `customer_state`: `pending | accepted | disputed`
  - `remediation_state`: `unpatched | micropatched | maintainer_patched`
- `findings`: Created exclusively by `ajar claim reproduce` after all 4 arms pass (`arm1_clean_poc_json` .. `arm4_patch_ctrl_json`, `micropatch_diff`, `attribution`).
- `chains`: End-to-end verified multi-stage exploit compositions (`step_ids_json`, `e2e_poc_cmd`, `control_cmd`, `verified`).

### Attribution and `Code` Unit Economics (`D-13`)
- `human_touches`: Records operator interventions (`scope_authority`, `env_rescue`, `research_steering`, `poc_repair`, `review_signoff`).
  - Zero `research_steering` + zero `poc_repair` -> `research_independence_pass = true` -> finding attribution `found_autonomously_by_ajar` (otherwise `found_with_ajar`; human-seeded claims receive `validated_by_ajar`).
  - Zero `env_rescue` -> `product_operability_pass = true`.
- `spend_ledger` & `runs.in_scope_loc`: Tracks `explore` vs `verify` USD spend, token counts, and `cost_usd_per_kloc` against the `<= $2.00 / kLoC` COGS target.

---

## 4. Multi-Target 4-Arm Causal Reproduction (`D-05`, `D-06`)

| Target Mode | Arm 1 (Clean + PoC) | Arm 2 (Clean + Control) | Arm 3 (Guard/Fix + PoC) | Arm 4 (Guard/Fix + Control) |
| --- | --- | --- | --- | --- |
| **`source`** (`ajar/repro_source.py`) | Exploit PoC fires assertion/sanitizer on unmodified worktree | Benign control passes on unmodified worktree | `1–5` line production `micropatch` stops exploit assertion | Benign control passes with `micropatch` applied |
| **`binary`** (`ajar/repro_binary_live.py`) | PoC hits consistent ASLR-normalized PC/signal; ablated input does not | Benign control exits cleanly | Runtime preload/wrapper guard blocks crash/corruption | Benign control exits cleanly under runtime guard |
| **`live`** (`ajar/repro_binary_live.py`) | Seed Principal A `ajar_canary_<32hex>`; Principal B PoC leaks/mutates canary | Principal B benign control does not leak/mutate canary | Principal A authorized request succeeds (`200` + canary) | Mandatory `--teardown-cmd` removes canary (`404`/absent verified) |

**Incremental Build Integrity & Dedup (`source`):**
- Modified files in `slot-<k>` receive a monotonic `+2 s` `utime` watermark (`watermark_ns`) so `cargo`, `make`, `ninja`, and `forge` never skip recompilation on sub-second patch swaps while preserving warm build caches.
- **Anti-Mitigation Diff Validator:** Rejects test-only patches, `exit(0)` / `os._exit(0)`, blanket `except Exception: pass` swallowers, and unconditional early returns.
- **PoV-Patch Cross-Kill Deduplication:** Running `--sibling-poc-cmd` against a confirmed finding's micro-patch tests whether two claims share one causal root cause (`duplicate_root_cause`).
- **2-Fail Telemetry Pivot:** Two consecutive failed reproduction runs with an identical observation hash transition the claim to `needs_instrumentation` and spawn an `instrument` task.

---

## 5. Orientation, FTS5 Reference Indexes, and Skill Quota (`D-08`, `D-09`)

1. **Personalized PageRank Map (`ajar/repomap.py`):** Builds a symbol definition/reference graph across Python, Rust, Solidity, Go, TypeScript/JavaScript, and C/C++, ranking top structural entrypoints within `--budget-tokens` (default `1500`).
2. **SQLite FTS5 Indexes (`ajar/oracles.py`):** Indexes three queryable views exposed via `ajar ref query --kind <kind> "<query>"`:
   - `intent`: READMEs, architecture docs, ADRs, inline docstrings, and test assertions.
   - `reachability`: Symbol definitions, callers, route mounts, and trait/interface implementations.
   - `precedent`: All 8 curated corpora in `skills/references/*.md`.
3. **Zero-Skill First-Principles Quota (`D-09`):** When `>= 2` workers execute in a run, at least one `investigate` lease runs with `skill_mode = zero_skill` (pure code-first invariant derivation without domain checklists), while `domain` leases use contrastive packs (`skills/domains/*/SKILL.md`).

---

## 6. Deterministic SQL Closeout Gates (`D-03`)

`ajar gate check` and `ajar finish` evaluate five SQL invariants in `ajar/gates.py`:

- **`G1` (Surface & Priority Task Coverage):** Under `exhaustive-high`, at least one surface is mapped, zero `critical`/`high` tasks remain `open` or `leased`, and every `critical`/`high` surface has at least one `done` or `dry` task. Under `first-verified-high`, >= 1 `critical`/`high` finding is reproduced with zero active verification leases (or all `critical`/`high` surfaces closed `dry`).
- **`G2` (Zero Unresolved Claims):** Zero claims remain in `proposed`, `survived_falsify`, or `needs_instrumentation`.
- **`G3` (Causal Proof & Challenger Separation):** Every `findings` row has passing 4-arm JSON receipts and its parent claim satisfies `proposer_worker_id != falsifier_worker_id`.
- **`G4` (First-Principles Quota & Anti-Bulk-Dismissal):** `zero_skill_leases >= 1` whenever `>= 2` distinct workers leased tasks, and every `dry` task cites an existing target `file:line` locus plus a `>= 15`-character guard explanation.
- **`G5` (Orphaned Anomaly & Chain Completeness):** Zero `unexplained` anomalies remain, and when `>= 2`composable primitives or low/medium findings exist, at least one `chain` evaluation task has completed.
