# ADR-0024: Zero-Cycle Modular DAG, Universal Strict Typing, Atomic Transactions, and Swarm Resilience

- **Status:** Accepted (Active)
- **Date:** 2026-11-21
- **Supersedes:** None (extends [ADR-0023](0023-agent-friendly-layered-architecture-and-dst.md))

## Context

[ADR-0023](0023-agent-friendly-layered-architecture-and-dst.md) established the `ajar/{domain,store,services}/` layer boundary, removed inline SQL from `ajar/mcp.py`, and introduced `tools/arch_lint.py` plus seeded deterministic simulation testing (`tests/dst/`). Four operational bottlenecks remained as multi-worker swarms scaled across long-horizon targets:

1. **Remaining coupling & monolithic files:** `ajar/cli.py` (`2,438` LOC) and `ajar/db.py` (`2,827` LOC) concentrated unrelated concerns, `ajar/cli.py` still held inline SQL writes outside `ajar/services/workflow.py`, and two circular import strongly connected components (`repro_compose <-> repro_source`, `db <-> epistemic_hooks <-> chain_planner`) forced function-scoped lazy imports.
2. **Transaction & typing gaps:** Multi-statement write paths outside `workflow.py` issued bare autocommit queries or dead `.commit()` no-ops under `isolation_level=None`, `findings.build_cmd` lacked a schema column (`v331`), and `mypy --strict` covered only `domain`/`store`/`services` instead of the entire `ajar/` package.
3. **Swarm hunt friction:** `ajar repro try` contended on a single `slot-inst.lock`, crashed workers could leave stale `.git/index.lock` files in slot worktrees, failed reproductions emitted no replayable JSON artifact, `swarm packet` instructed workers to run raw SQL against `run.db`, `InvalidTransitionError` and MCP errors lacked self-healing metadata, and noisy telemetry events could reset the 3-stall circuit breaker.
4. **Inner-loop latency:** Dual `mypy` invocations, uncached AST reparsing in `tools/arch_lint.py`, and full-schema setup per test kept `scripts/verify-repo.sh --fast` near `19s`.

## Decision

1. **Universal `mypy --strict` and Fast Verification Loop:** Enforce a single `mypy --strict ajar tools/arch_lint.py` pass across all of `ajar/` and `tools/arch_lint.py`, cache parsed ASTs in `tools/arch_lint.py`, prefilter conformance jargon rules with exact 1:1 literal anchors, and clone a template SQLite database in unit/DST suites (`scripts/verify-repo.sh --fast` `~10s`).
2. **Zero Raw SQL in CLI and Mandatory `immediate_tx` Atomicity:** Lock `MAX_CLI_RAW_SQL_WRITES = 0`, route all CLI state writes through `ajar/services/workflow.py`, add `findings.build_cmd` (`CURRENT_SCHEMA_VERSION = 331`), wrap all multi-write functions in `with immediate_tx(conn):` (never across subprocess execution), and enforce `NO_COMMIT_NOOP` and `MULTI_WRITE_REQUIRES_IMMEDIATE_TX` in `tools/arch_lint.py`.
3. **Zero-Cycle Module DAG and Cohesive Package Split:**
   - Split `ajar/cli.py` into `ajar/cli/{__init__,__main__,common,hunt,claims,ops,parser}.py` with backwards-compatible re-exports on `ajar.cli`.
   - Extract `ajar/store/migrations.py` (`SCHEMA_SQL`, `_ensure_v31..v33_schema`) and `ajar/store/util.py` (connection, symlink checks, `log_event`, `parse_tag_list`, salience helpers) from `ajar/db.py`.
   - Extract pure-stdlib leaf `ajar/repro_helpers.py` from `ajar/repro_compose.py`, and hoist cross-module event reactions (`on_primitive_added`, `on_anomaly_or_claim_recorded`, `on_finding_confirmed`) into `ajar/reactions.py`.
   - Enforce `0` import cycles across all `ajar.*` modules (including function-scoped lazy imports) via Tarjan SCC `NO_CIRCULAR_IMPORTS` in `tools/arch_lint.py`.
4. **Swarm-Hunt Resilience, Self-Healing Errors, and Expanded DST:**
   - Move `run_repro_try` onto the shared 8-slot pool (`_acquire_slot`), auto-clear stale `.git/index.lock` / `.git/shallow.lock` while holding `slot-<k>.lock`, and persist scrubbed replayable failure receipts to `repro/failures/<claim_id>-<n>.json`.
   - Populate `allowed_targets` and `fix_hint` on every `InvalidTransitionError` and serialize `AjarError` as structured JSON in MCP `tools/call` error responses.
   - Filter non-progress telemetry actions (`stop_hook_check`, `spend_added`, `task_checkpoint`, `human_touch_recorded`) and compare a 5-element semantic progress tuple in `ajar/hooks.py`.
   - Embed scrubbed structured claim and task records directly in `ajar swarm packet` output and remove raw `SELECT ... FROM claims` instructions.
   - Add `ajar doctor --run <id> [--prune-slots]` for SQLite `PRAGMA quick_check`, stale-lease reporting, and lock-safe slot worktree pruning.
   - Expand `tests/dst/test_state_machine_sim.py` to cover the 2-strike instrumentation pivot, primitive-to-door wakeup and multi-hop percolation, `diff_sync` `build_cmd` preservation, and 2-connection concurrent WAL contention.

## Consequences

- Agents and contributors edit small, single-purpose modules (`<= 1,500` LOC) with zero circular imports and full `mypy --strict` coverage across `ajar/`.
- Concurrent swarm workers share the 8-slot reproduction pool without `slot-inst` contention, self-heal stale git locks, receive actionable error payloads over CLI and MCP, and never need raw SQL access to `run.db`.
- Every structural rule (`NO_RAW_SQL_IN_MCP`, `CLI_RAW_SQL_RATCHET`, `LAYER_DAG_BOUNDARY`, `NO_COMMIT_NOOP`, `MULTI_WRITE_REQUIRES_IMMEDIATE_TX`, `NO_CIRCULAR_IMPORTS`) runs mechanically in CI.

## Risks

- Re-export shims on `ajar.cli`, `ajar.db`, `ajar.store`, and `ajar.repro_compose` keep existing callers compatible, but future edits must avoid reintroducing upward imports into `ajar/store/` or `ajar/domain/`.
- `MULTI_WRITE_REQUIRES_IMMEDIATE_TX` verifies function-level `immediate_tx` presence rather than per-statement control-flow dominance; code review must continue ensuring transactions never span subprocesses.

## Revisit Triggers

- Revisit if any single module under `ajar/` grows past `1,800` LOC or acquires mixed transport/persistence responsibilities.
- Revisit if `scripts/verify-repo.sh --fast` exceeds `15s` on standard CI runners.
