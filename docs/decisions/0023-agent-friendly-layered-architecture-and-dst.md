# ADR-0023: Agent-Friendly Layered Architecture, Mechanical Guardrails, and Deterministic Simulation Testing

- **Status:** Accepted (Active)
- **Date:** 2026-11-21
- **Builds on:** [ADR-0017](0017-ajar-v3-dual-mode-architecture.md), [ADR-0018](0018-ajar-v3-1-bug-brain-and-platform-economics.md), [ADR-0019](0019-ajar-v3-2-hooks-and-composable-repro.md), [ADR-0020](0020-ajar-v3-2-2-swarm-wire-profiles-and-reopen.md), [ADR-0021](0021-ajar-v3-2-3-exogenous-target-checks-and-retro-routing.md), [ADR-0022](0022-ajar-v3-3-reactive-open-doors-and-phase-split.md)

## Context

Forensic review of the `ajar-harness` codebase and git history before Phase 0 identified five structural risks that slowed agent-driven development and allowed subtle state-machine regressions to ship:

1. **Implicit String State Machines & CLI/MCP Drift:** Eighteen state machines (`runs`, `campaign_phase`, `tasks`, `claims`, `anomalies`, `primitives`, `parked_doors`, `crown_jewels`, `swarm_dispatches`, `epistemic_hooks`, and related axes) were enforced only by scattered `if` checks and SQLite `CHECK` strings. `ajar/cli.py` and `ajar/mcp.py` duplicated inline SQL mutations, creating TOCTOU races under WAL concurrency and inconsistent validation (for example whitespace-padded `worker_id` values or missing claim-axis updates).
2. **Prose-Only Architectural Rules:** Core invariants (zero LLM SDK imports in `ajar/`, no `tools/legacy/` imports, safe `tarfile` extraction filters, zero hardcoded devbox paths, CLI-vs-Docs flag parity) relied on manual review instead of mechanical enforcement.
3. **Unverified Multi-Worker Interleavings:** Unit and integration tests exercised happy paths individually without randomized multi-worker simulation, allowing cross-command state drift (such as `reopen_run` leaving stale `research_state`/`evidence_state` on unblocked claims).
4. **Slow Feedback & Redundant Hot-Path Work:** `open_run_db` executed 71 SQL migration statements on every warm connection, `index_target_oracles` performed 1,177 autocommit SQLite inserts and re-scrubbed static built-in `precedent` docs on every `ajar init` (`1.42s`), and running `pytest` serially took `95.5s` with no fast inner-loop lane.
5. **Language & Startup Proof Alignment:** Evaluating a Rust rewrite showed that runtime latency in Ajar is dominated by LLM inference and target compilation (`gcc`/`cargo`/`go`), not Python overhead. Rewriting before reaching the 2027-02-14 proof milestones would stall feature velocity without improving hunt throughput. Meanwhile, `DEC-0132` COGS/LoC calibration and `P0-3` commit-before-submit ledger commitments needed read-only, strictly advisory helpers that never block Host Mode operators.

## Decision

1. **Stay Pure Python (`>= 3.11.4`, Zero Third-Party Runtime Dependencies) with Strict Layer Boundaries (`ajar/domain/` -> `ajar/store/` -> `ajar/services/` -> `ajar/cli.py`, `ajar/mcp.py`):**
   - `ajar/domain/` (`enums.py`, `models.py`, `transitions.py`): Pure zero-IO `StrEnum`s for all 18 state machines, `AjarError` and `InvalidTransitionError(AjarError)`, explicit `ALLOWED_*_TRANSITIONS` tables, and pure `derive_claim_axes()`. `ajar/epistemic_hooks.py:HOOK_CODES` derives directly from `HookCode`.
   - `ajar/store/` (`tx.py`): `CURRENT_SCHEMA_VERSION = 330`, `immediate_tx(conn)` (`BEGIN IMMEDIATE` with nested `SAVEPOINT` support), and `assert_run_mutable(conn)`. `open_run_db` uses a `PRAGMA user_version` fast-path (`<= 4` SQL statements on warm opens) while keeping `PRAGMA synchronous=NORMAL` unconditional.
   - `ajar/services/` (`workflow.py`, `proof.py`): Single transactional source of truth for workflow mutations (`add_surface`, `close_task_done`, `close_task_dry`, `block_task`, `add_anomaly`, `explain_anomaly`, `propose_claim`, `rescope_claim_service`, `falsify_claim`, `survive_claim`, `block_claim`, `advance_phase`, `finish_run`). Every service acquires `immediate_tx(conn)` before reading mutable rows, checking `assert_run_mutable`, and enforcing transition guards. `ajar/mcp.py` carries `0` inline SQL writes.
2. **Mechanical Architecture Guardrails & CI Static Typing (`tools/arch_lint.py`, `pyproject.toml`, `.github/workflows/conformance.yml`):**
   - `tools/arch_lint.py` enforces `NO_RAW_SQL_IN_MCP`, `CLI_RAW_SQL_RATCHET`, `LAYER_DAG_BOUNDARY` (including relative imports), `ZERO_LLM_ENGINE`, `NO_HARDCODED_DEVBOX_PATH`, `NO_AMBIENT_ENV_MUTATION`, and `NO_UNFILTERED_TAR_EXTRACT` (literal `'tar'` or `'data'` filters), emitting a self-healing `fix_hint` for every violation.
   - CI runs `ruff check` (`E, F, I, W, B`), `python3 tools/arch_lint.py`, `mypy --strict ajar/domain ajar/store ajar/services tools/arch_lint.py`, `mypy ajar --ignore-missing-imports`, CLI-vs-Docs/Skills flag checks in `tests/test_conformance.py`, and full `pytest -q`.
3. **Seeded Multi-Worker Deterministic Simulation Testing (`tests/dst/test_state_machine_sim.py`):**
   - Runs seeded randomized multi-worker sequences (`AJAR_DST_SEEDS`, replayable via `AJAR_DST_SEED=<n>`) with a frozen logical clock, asserting 10 global invariants after every step (5-axis claim coherence, fresh-falsifier separation, orphaned anomaly survival, primitive `chained <-> status` sync, monotonic `campaign_phase`, hunt-phase patch gating, strict read-only `check_all_gates(..., auto_enqueue_chain=False)` row-snapshot purity, Host Mode advisory spend behavior, enum domain integrity, and `PRAGMA quick_check`) plus KV prefix-cache stability and non-vacuity coverage assertions.
4. **Fast Verification Inner Loop & Hot-Path Batching (`scripts/verify-repo.sh`, `ajar/oracles.py`, `ajar/cli.py`):**
   - `index_target_oracles` batches `oracle_docs`/`oracle_fts` writes inside a single `immediate_tx` and caches static built-in `precedent` rows by mtime+size (`ajar init` reduced from `1.42s` to `0.24s`); `ajar/cli.py` caches the stateless `argparse` tree via `_get_cached_parser()`.
   - End-to-end compiler/debugger suites carry `pytest.mark.integration`. `scripts/verify-repo.sh --fast` runs all static gates plus unit, conformance, parity, and DST checks in `~19s`, while `scripts/verify-repo.sh --full` and CI run the complete suite including integration and archived legacy checks.
5. **Host-Mode Advisory Budget Telemetry & Commit-Before-Submit Proof Helpers (`ajar/services/proof.py`):**
   - Host Mode budget breakers remain strictly advisory (`ajar spend add` and `ajar economics export` never mutate `runs.status` or block task leasing).
   - `ajar economics export` emits `ajar-economics-calibration/1` JSON for `DEC-0132` calibration.
   - `ajar ledger commit-preimage` builds `P0-3` SHA-256 commitments over redacted finding fields (`scrub_text`), hashes immutable `finding.created_at` for cross-second `--salt` determinism, isolates `private_preimage` from stdout when `--preimage-out` is set, and writes private preimages atomically (`O_CREAT | O_EXCL | O_NOFOLLOW` + `fchmod(0o600)` + `os.replace`).

## Consequences

- Agents and humans receive immediate, actionable mechanical feedback (`~19s` via `scripts/verify-repo.sh --fast`) on type safety, layer boundaries, CLI/MCP parity, CLI/doc flag drift, and randomized state-machine invariants.
- Any new workflow mutation must be added once in `ajar/services/` and invoked by both `ajar/cli.py` and `ajar/mcp.py`; `tools/arch_lint.py` blocks regressions automatically.
- `requires-python` is tightened to `>=3.11.4` to guarantee PEP 706 `tarfile` filter support without dead fallback branches.

## Risks and Revisit Triggers

- **Remaining inline SQL in `ajar/cli.py`:** `CLI_RAW_SQL_RATCHET` currently caps `ajar/cli.py` at 14 inline SQL writes (`surface_drivers`, `tasks`, `primitives`, `human_touches`, `spend_ledger`, `reproduce`, non-source `chain`). Lower `MAX_CLI_RAW_SQL_WRITES` in `tools/arch_lint.py` whenever another CLI subcommand migrates into `ajar/services/`.
- **Rust Rewrite Revisit Trigger:** Re-evaluate a Rust port of hot pure-CPU subsystems (such as `repomap` symbol extraction or FTS indexing) only after the 2027-02-14 proof milestones are met and profiling shows Python CPU time exceeding 10% of end-to-end run wall clock.
- **Repository Mirroring:** `matheusht/ajar-harness` continuously mirrors `main` and tags to `avenza-cloud/ajar` via `.github/workflows/mirror-sync.yml` without coupling runtime code to any single GitHub remote.
