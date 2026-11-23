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
| `ajar/domain/` | Pure zero-IO `StrEnum`s for all state machines (`enums.py`), frozen models & self-healing `AjarError`/`InvalidTransitionError` (`models.py`), explicit transition graphs & `derive_claim_axes` (`transitions.py`) |
| `ajar/store/` | `CURRENT_SCHEMA_VERSION`, `immediate_tx(conn)` (`BEGIN IMMEDIATE` + nested `SAVEPOINT`), `assert_run_mutable(conn)` (`tx.py`); `SCHEMA_SQL` & `_ensure_v31..v34_schema` (`migrations.py`); `open_run_db`, `O_NOFOLLOW`, `log_event`, `parse_tag_list`, `compute_harness_code_sha256`, `compute_lead_ev_formula`, `compute_root_plateau_throttles`, `compute_island_illumination` (`QD-Islands`), `compute_epistemic_potential` / `compute_epistemic_delta` (Lyapunov $\Phi(t)$), `evaluate_chain_failure_streak`, `apply_latest_finding_corrections`, and salience utilities (`util.py`) |
| `ajar/catalog.py` | Read-only Unified Issue & Gadget Catalog (`search_issue_catalog`) and backward sink-to-source call-cone slicer (`trace_backward_sink_slices` over `repomap_edges`) |
| `ajar/services/` | Unified transactional workflow mutations (`workflow.py`: surfaces, drivers, tasks, anomalies, primitives, claims, duplicate/same-root grouping, repro outcomes, chains, `cast_lead_vote`/`rank_leads`, `plan_swarm_wave`/`build_worker_dispatch_brief`, convergence-gated `advance_phase`, `close_run_early`, touches, spend, run finish) shared identically by `ajar/cli/` and `mcp.py`, plus proof & bundle helpers (`proof.py`: `DEC-0132` economics export, `P0-3` SHA-256 ledger preimages, and atomic `seal_bundle`/`verify_bundle`) |
| `ajar/db.py` | Portfolio-balanced & `QD-Islands` anti-monopoly task leases (`immediate_tx`), `hunt`/`remediate` phase split, `calibrate_finding`, `mark_primitive_dry`, prefix-stable `< 4 KB` context, `steers`, `pulse`, threat model, and backwards-compatible re-exports of `ajar/store/` |
| `ajar/chain_planner.py` | Suspended Open Doors (`crown_jewels`, `parked_doors`, `door_fts`), tri-modal reactive wakeup, `<= 2` bounded `bridge` hunters, conjunctive $2..10$-hop middle-unicorn percolation (`detect_percolated_multi_hop_paths`), Abductive Cut-Lemma PUCT gap scoring (`ah_puct_score`), `compute_chain_frontier`, and `evaluate_precondition_realism` |
| `ajar/epistemic_hooks.py` | Event-driven `H1`–`H9` epistemic micro-hooks (`0` overhead on clean code, mandatory `Kill Rule`, `stepping_stone` `H5` escalation, `H9_INVARIANT_SYMMETRY` peer-guard checks) and `provides_tags <-> requires_tags` capability bridges |
| `ajar/reactions.py` | Cross-module event reaction orchestrators (`on_primitive_added`, `on_anomaly_or_claim_recorded`, `on_finding_confirmed`) sitting strictly above `store`, `epistemic_hooks`, `chain_planner`, and `db` |
| `ajar/repro_helpers.py` | Pure-stdlib leaf runtime provisioning (`StageContext`, `sitecustomize.py` loopback guard, `ajar-helper-exec`) and AST validation for capability helpers |
| `ajar/repro_compose.py` | Zero-boilerplate `fnd-*`/`clm-*`/`prim-*`/`anom-*` chain composition with auto-inherited micropatches, `--backup-step` stage swaps, fail-closed step ablation, 2-strike `ajar chain probe` stagnation gate, `run_snapshot_chain_probe` (`--from-snapshot`, `--build-cmd`), and optional `StageContext` helpers |
| `ajar/repro_source.py` | Bare-shared `repo.git` mirror, shared 8-slot `slot-<k>` pool (with stale `.git/index.lock` auto-heal), replayable `repro/failures/<claim_id>-<n>.json` receipts, `--build-cmd`, fail-closed Arm-3 proof, non-strike `build_or_env_error`/`preflight_error`/`micropatch_error` separation (`poc_proven`), `--save-post-state` snapshots, strike-free `run_repro_try`, and 4-arm + Arms `5A`/`5B` runner |
| `ajar/slice_probe.py` | Zero-dependency `@VISITED` / `@UNREACHED` line-coverage and ASan/UBSan/TSan/MSan crash-frame slice probe (`run_slice_probe`) using Python `sys.settrace` (chaining loopback socket guard) and GCC `gcov --json-format` inside `repro/slot-<k>` |
| `ajar/patch_verify.py` | Hardened 9-Arm Production Remediation Gate (`remediate`-phase gated, warm `.o` preservation, `1800s` `--suite-timeout`, `verified_local` state, and Arm 9 `git apply -R` revert proof) |
| `ajar/swarm.py` | Stage-split `"Swarm Worker"` packet generator with severity-prioritized `portfolio` lanes (`investigate`, `bridge`, `falsify`, `reproduce`, `chain`, `portfolio`), boundary-invariant non-repro `regression_tdd` fallback prompts, and cross-VM `ajar reopen` |
| `ajar/target_check.py` | Offline target archival/freshness checks on `ajar init` (`--allow-historical-target`) and `ajar doctor --target` upstream/branch/subdir/peer/disk probes |
| `ajar/diff_sync.py` | Incremental PR differential state sync (`ajar init --diff <base..head> --parent-run <id>`) classifying `kept | closed | invalidated_guard | new` |
| `ajar/gates.py` | Pure-SQL closeout gates `G1–G5`, `crown-jewel` non-satisficing & bounded-exhaustion gate, `ready`-door & high-chain `G5` gate, guarded-primitive `dry` gate, and `35%` COGS margin gates |
| `ajar/repro_binary_live.py` | 4-arm `binary` (ASLR-normalized PC + ablation + runtime guard) and `live` (128-bit CSPRNG canary + teardown) runners |
| `ajar/repomap.py` | Pure-Python symbol extraction (excluding C/C++ file-local `static` helpers from cross-file edges), Personalized PageRank map, `--unvisited` slice filter (`scout_coverage_pct`, `list_unvisited_slices`), `--slice-cap` splitter, and `ajar quote` calculator |
| `ajar/graph.py` | Deterministic `Platform` component, hook, helper, coverage, and attack-flow JSON exporter (`ajar-platform-graph/2`) |
| `ajar/oracles.py` | SQLite FTS5 indexing and queries for `intent` (`[UNTRUSTED_TARGET_DOC]` tagged), `reachability`, and `precedent` |
| `ajar/hooks.py` | Host Mode `claude-stop` hook and `codex`/`omp` continuation loop with Grounded Lyapunov epistemic potential ($\Delta \Phi > 0$) 3-stall circuit breaker |
| `ajar/mcp.py` | Thin STDIO JSON-RPC MCP wrapper delegating all mutations to `ajar/services/` and slice probes to `ajar/slice_probe.py` (`0` inline SQL writes, structured JSON error payloads) |
| `ajar/runner.py` | Standalone Mode (`ajar run`) scheduler with `--until crown-jewel`, `--phase`, `--discover-passes N`, role-tier model routing, `detect_soliloquy_transcript`, and `80% / 20%` verify reserve |
| `ajar/report.py` | Markdown and JSON report compiler including `distinct_root_causes_count`, `harness_integrity`, `apply_latest_finding_corrections`, `realism_tier`, `ub_divergence_class`, `ablation_matrix_json`, and `patch_verifications` |
| `ajar/redact.py` | Pure-stdlib secret scanner/redactor and `scrubbed_subprocess_env` preserving `SDKROOT`/macOS `xcrun`, offline `rustup`/`cargo` toolchains, `$AJAR_RUN_DIR`, and dangling-symlink-clean `PATH` |
| `ajar/cli/` | Cohesive CLI package (`__init__.py`, `__main__.py`, `common.py`, `hunt.py`, `claims.py`, `repro.py`, `ops.py`, `parser.py`) delegating all state mutations to `ajar/services/` (`0` inline SQL writes) |
| `ajar/cli/repro.py` | CLI handler (`cmd_repro`) for strike-free `ajar repro try`, `@VISITED`/`@UNREACHED` `ajar repro slice-probe`, and `ajar repro snapshots` |
| `tools/arch_lint.py` | Mechanical architecture & invariant linter (10 rules, AST-cached, self-healing `fix_hint` diagnostics) |

## Rule-to-Enforcer Map

Every durable engineering rule is mechanically enforced in CI (never prose-only):

| Rule | Mechanical Enforcer |
| --- | --- |
| Zero LLM SDKs in `ajar/` & no `tools/legacy/` imports | `tools/arch_lint.py` (`ZERO_LLM_ENGINE`, `LAYER_DAG_BOUNDARY`) |
| Strict acyclic module DAG (`0` circular imports across `ajar/`) | `tools/arch_lint.py` (`LAYER_DAG_BOUNDARY`, `NO_CIRCULAR_IMPORTS`) + `mypy --strict ajar tools/arch_lint.py` |
| Single mutation path across CLI & MCP (`0` raw SQL writes in `ajar/cli/` and `ajar/mcp.py`) | `tools/arch_lint.py` (`NO_RAW_SQL_IN_MCP`, `CLI_RAW_SQL_RATCHET`) + `tests/test_arch_and_service_parity.py` |
| Transactional SQLite atomicity (zero `.commit()` no-ops, multi-write `immediate_tx`) | `tools/arch_lint.py` (`NO_COMMIT_NOOP`, `MULTI_WRITE_REQUIRES_IMMEDIATE_TX`) + `tests/dst/test_state_machine_sim.py` |
| No hardcoded developer paths or ambient `HOME`/`PATH` mutation in tests | `tools/arch_lint.py` (`NO_HARDCODED_DEVBOX_PATH`, `NO_AMBIENT_ENV_MUTATION`) |
| Explicit `filter=` on every `tarfile` extraction | `tools/arch_lint.py` (`NO_UNFILTERED_TAR_EXTRACT`) |
| Enum-to-SQL CHECK & `HookCode` parity + explicit state transitions | `tests/test_domain_and_migrations.py` |
| Root `AGENTS.md == CLAUDE.md <= 50` lines & zero doc/skill CLI flag drift | `tests/test_conformance.py` + `.github/workflows/conformance.yml` |

## Required Verification Before Opening a PR

Use the canonical repository verification driver (fast inner loop during development, full suite before opening a PR):

```bash
scripts/verify-repo.sh --fast    # Inner loop: AGENTS.md, ruff, arch_lint, mypy --strict, unit + parity + DST
scripts/verify-repo.sh --full    # Pre-PR outer loop: adds integration tests + archived legacy checks
```

Equivalent explicit commands run in CI:

```bash
test "$(wc -l < AGENTS.md)" -le 50 && cmp -s AGENTS.md CLAUDE.md
ruff check ajar tests tools/arch_lint.py
python3 tools/arch_lint.py
mypy --strict ajar tools/arch_lint.py
pytest -q
for t in tools/legacy/*-test.py; do python3 "$t"; done
```
