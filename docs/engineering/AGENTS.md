# Ajar Engineering Guide

Read this file before modifying `ajar/`, `skills/`, `benchmarks/`, `docs/`, or `tests/`.

## Architectural Invariants

1. **Zero-LLM Engine (`ajar/`):** Never add LLM SDK imports, prompt templates, or network inference calls inside core state, gate, hook, or reproduction modules (`ajar/db.py`, `ajar/epistemic_hooks.py`, `ajar/gates.py`, `ajar/repro_*.py`, `ajar/patch_verify.py`, `ajar/diff_sync.py`, `ajar/graph.py`). Keep `ajar/` deterministic, fast, and standard-library-first.
2. **Root `AGENTS.md` Budget (`<= 50` Lines):** Keep root `AGENTS.md` and `CLAUDE.md` byte-identical, written in ASD-STE100 (imperative mood, one instruction per sentence, concrete commands), and strictly `<= 50` lines (`wc -l < AGENTS.md`).
3. **External Run State & Prefix Cache Stability:** Every runtime table, helper, worktree, cache, and log belongs under `~/.ajar/runs/<run_id>/`. Never write `.ajar/` state files inside a target checkout, and keep the `Certified Run Prefix` in `render_task_context` byte-identical across workers (place per-task hooks and bridges inside `Task Delta`).
4. **Terminology Hygiene:** Use Ajar Labs' canonical product nouns (`Platform`, `Code`, `Fixes`, `Security reviews`, `Supply chain`) and canonical workflow verbs (`quote`, `map`, `investigate`, `falsify`, `rescope`, `instrument`, `reproduce`, `chain`, `patch`, `report`). Never reintroduce retired v1/v2 terms enforced by `tests/test_conformance.py`.
5. **Frozen Historical Closure (`tools/legacy/` and `engagements/`):** Treat `tools/legacy/` and `engagements/{cve-bench,cybench,xbow-benchmarks}` as read-only historical archives. Never import `tools/legacy/` from `ajar/`.

## Module Map (`ajar/`)

| Module | Responsibility |
| --- | --- |
| `ajar/domain/` | Pure zero-IO `StrEnum`s for all state machines (`enums.py`), frozen models & `AjarError`/`InvalidTransitionError` (`models.py`), explicit transition graphs & `derive_claim_axes` (`transitions.py`) |
| `ajar/store/` | Schema version constant (`CURRENT_SCHEMA_VERSION`), `immediate_tx(conn)` (`BEGIN IMMEDIATE` + nested `SAVEPOINT`), and `assert_run_mutable(conn)` (`tx.py`) |
| `ajar/services/` | Unified transactional workflow mutations (`workflow.py`: surfaces, tasks, anomalies, claims, phase advance, run finish) shared identically by `cli.py` and `mcp.py` |
| `ajar/db.py` | SQLite WAL schema (`v3.3` + `PRAGMA user_version` fast-path + auto-migration), `O_NOFOLLOW` run dirs, portfolio-balanced task leases, `hunt`/`remediate` phase split, `calibrate_finding`, `mark_primitive_dry`, prefix-stable `< 4 KB` context, `steers`, pulse |
| `ajar/chain_planner.py` | Suspended Open Doors (`crown_jewels`, `parked_doors`, `door_fts`), tri-modal reactive wakeup, `<= 2` bounded `bridge` hunters, $2..10$-hop middle-unicorn percolation (`detect_percolated_multi_hop_paths`), `compute_chain_frontier`, and `evaluate_precondition_realism` |
| `ajar/epistemic_hooks.py` | Event-driven `H1`–`H8` epistemic micro-hooks (`0` overhead on clean code, mandatory `Kill Rule`, `stepping_stone` `H5` escalation) and `provides_tags <-> requires_tags` capability bridges |
| `ajar/repro_compose.py` | Zero-boilerplate `fnd-*`/`clm-*`/`prim-*`/`anom-*` chain composition with auto-inherited micropatches, `run_snapshot_chain_probe` (`--from-snapshot`), optional `StageContext` helpers, and container loopback socket guard |
| `ajar/repro_source.py` | Bare-shared `repo.git` mirror, `slot-<k>` worktrees, `--build-cmd`, non-strike `build_or_env_error`/`preflight_error` separation, `--save-post-state` snapshots, strike-free `run_repro_try`, and 4-arm + Arms `5A`/`5B` runner |
| `ajar/patch_verify.py` | Hardened 9-Arm Production Remediation Gate (`remediate`-phase gated, warm `.o` preservation, `1800s` `--suite-timeout`, `verified_local` state, and Arm 9 `git apply -R` revert proof) |
| `ajar/swarm.py` | Stage-split `"Swarm Worker"` packet generator (`investigate`, `bridge`, `falsify`, `reproduce`, `chain`, `portfolio`), `direct -> swarm_patch_first -> regression_tdd` fallback ladder, and cross-VM `ajar reopen` |
| `ajar/target_check.py` | Offline target archival/freshness checks on `ajar init` (`--allow-historical-target`) and `ajar doctor --target` upstream/branch/subdir/peer/disk probes |
| `ajar/diff_sync.py` | Incremental PR differential state sync (`ajar init --diff <base..head> --parent-run <id>`) classifying `kept | closed | invalidated_guard | new` |
| `ajar/gates.py` | Pure-SQL closeout gates `G1–G5`, `crown-jewel` non-satisficing & bounded-exhaustion gate, `ready`-door `G5` gate, guarded-primitive `dry` gate, and `35%` COGS margin gates |
| `ajar/repro_binary_live.py` | 4-arm `binary` (ASLR-normalized PC + ablation + runtime guard) and `live` (128-bit CSPRNG canary + teardown) runners |
| `ajar/repomap.py` | Pure-Python symbol extraction (excluding C/C++ file-local `static` helpers from cross-file edges), Personalized PageRank map, `--slice-cap` splitter, and `ajar quote` calculator |
| `ajar/graph.py` | Deterministic `Platform` component, hook, helper, coverage, and attack-flow JSON exporter (`ajar-platform-graph/1`) |
| `ajar/oracles.py` | SQLite FTS5 indexing and queries for `intent` (`[UNTRUSTED_TARGET_DOC]` tagged), `reachability`, and `precedent` |
| `ajar/hooks.py` | Host Mode `claude-stop` hook and `codex`/`omp` continuation loop with 3-stall circuit breaker |
| `ajar/mcp.py` | Thin STDIO JSON-RPC MCP wrapper delegating all mutations to `ajar/services/` (0 inline SQL writes) |
| `ajar/runner.py` | Standalone Mode (`ajar run`) scheduler with `--until crown-jewel`, `--phase`, `--discover-passes N`, role-tier model routing, `detect_soliloquy_transcript`, and `80% / 20%` verify reserve |
| `ajar/report.py` | Markdown and JSON report compiler including `realism_tier`, `ub_divergence_class`, `ablation_matrix_json`, `patch_verifications`, and `CLOSEOUT_RECEIPT` |
| `ajar/redact.py` | Secret scanner/redactor and `scrubbed_subprocess_env` preserving `SDKROOT`/macOS `xcrun`, offline `rustup`/`cargo` toolchains, `$AJAR_RUN_DIR`, and dangling-symlink-clean `PATH` |
| `ajar/cli.py` | Command-line interface entrypoint (`ajar`) delegating core workflow mutations to `ajar/services/` |
| `tools/arch_lint.py` | Mechanical architecture & invariant linter with self-healing `fix_hint` diagnostics |

## Rule-to-Enforcer Map

Every durable engineering rule is mechanically enforced in CI (never prose-only):

| Rule | Mechanical Enforcer |
| --- | --- |
| Zero LLM SDKs in `ajar/` & no `tools/legacy/` imports | `tools/arch_lint.py` (`ZERO_LLM_ENGINE`, `LAYER_DAG_BOUNDARY`) |
| Strict layer DAG (`domain -> store -> services -> cli/mcp`) | `tools/arch_lint.py` (`LAYER_DAG_BOUNDARY`) + `mypy --strict` |
| Single mutation path across CLI & MCP (0 raw SQL writes in `mcp.py`, ratcheted `cli.py`) | `tools/arch_lint.py` (`NO_RAW_SQL_IN_MCP`, `CLI_RAW_SQL_RATCHET`) + `tests/test_arch_and_service_parity.py` |
| No hardcoded developer paths or ambient `HOME`/`PATH` mutation in tests | `tools/arch_lint.py` (`NO_HARDCODED_DEVBOX_PATH`, `NO_AMBIENT_ENV_MUTATION`) |
| Explicit `filter=` on every `tarfile` extraction | `tools/arch_lint.py` (`NO_UNFILTERED_TAR_EXTRACT`) |
| Enum-to-SQL CHECK & `HookCode` parity + explicit state transitions | `tests/test_domain_and_migrations.py` |
| Root `AGENTS.md == CLAUDE.md <= 50` lines & zero doc/skill CLI flag drift | `tests/test_conformance.py` + `.github/workflows/conformance.yml` |

## Required Verification Before Opening a PR

Run all checks from the repository root and disclose results in the PR description:

```bash
test "$(wc -l < AGENTS.md)" -le 50 && cmp -s AGENTS.md CLAUDE.md
ruff check ajar tests tools/arch_lint.py
python3 tools/arch_lint.py
mypy --strict ajar/domain ajar/store ajar/services tools/arch_lint.py && mypy ajar --ignore-missing-imports
pytest -q
for t in tools/legacy/*-test.py; do python3 "$t"; done
```
