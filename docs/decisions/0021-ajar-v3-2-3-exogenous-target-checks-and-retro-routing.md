# ADR-0021: Ajar v3.2.3 Exogenous Target-Readiness Checks and Reviewer-Skill Retro Routing

- **Status:** Accepted (Active)
- **Date:** 2026-11-19
- **Builds on:** [ADR-0017](0017-ajar-v3-dual-mode-architecture.md), [ADR-0018](0018-ajar-v3-1-bug-brain-and-platform-economics.md), [ADR-0019](0019-ajar-v3-2-hooks-and-composable-repro.md), [ADR-0020](0020-ajar-v3-2-2-swarm-wire-profiles-and-reopen.md)

## Context

In `kona-wave1a` (`2026-11-19`), Ajar's closed-world verification engine reproduced `31` causal findings (`88%` of High/Criticals independently patched upstream by maintainers, including `2` full end-to-end Criticals), yet yielded `0` externally submittable bounties because:
1. The audited checkout (`op-rs/kona` `2586fc56`) was an archived repository whose `HEAD` commit subject announced migration to a monorepo `10` months earlier.
2. Threat-model synthesis concatenated trusted operator principals with unprivileged external callers.
3. Coupled protocol claims were promoted without checking sibling reference clients or downstream contracts, and executive tables mixed operator-gated findings with unprivileged entrypoint findings.
4. Target repositories increasingly ship root `CLAUDE.md` / `AGENTS.md` developer prompts that must never leak into `--envelope` snapshots.

At the same time, active Wave-1 campaigns across C (`git-wave1a`) and Rust (`kona-wave1b`) are in flight. Prematurely adding target-specific SQLite columns or new closeout gates before all Wave-1 runs complete would introduce unnecessary schema churn.

## Decision

1. **Offline Target Freshness Gate on `ajar init` (`ajar/target_check.py`, `ajar/workspace.py`):**
   - `inspect_local_target_freshness` inspects git `HEAD` commit age (`<= 90` days default), `HEAD` commit subject, and top `README` lines for explicit repository archival/migration notices, blocking `ajar init` (`EXIT_GATE_BLOCKED`) unless `--allow-historical-target` or `--diff` is supplied.
   - `UNTRUSTED_TARGET_AGENT_CONFIGS` strips target-root `CLAUDE.md` and `AGENTS.md` alongside `.claude`, `.mcp.json`, `.cursor`, and `.codex` during `--envelope` snapshotting.
2. **Extended `ajar doctor --target` Readiness Probe (`ajar/target_check.py`, `ajar/cli.py`):**
   - `ajar doctor --target <path|owner/repo|git_url> [--subdir <rel>] [--peer <path>] [--max-age-days 90] [--no-remote]` checks local git freshness, remote GitHub/Git liveness (`archived`, `disabled`, `default_branch`, `remote_head_sha`, `private_vulnerability_reporting`), subdirectory `Code` LoC and `35%` COGS quote, embedded agent-config files, Rust `#![no_std]` crates, sibling `--peer` checkouts, and `/tmp` + `HOME` free GiB.
3. **Reviewer & Mapper Skill Routing (`skills/ajar-{map,falsify,report}/SKILL.md`):**
   - Route judgment standards into `ajar-map` (principal separation and active-production surface ranking), `ajar-falsify` (`Check 5` external entrypoint, operator ceiling, and sibling peer/consumer verification), and `ajar-report` (separating unprivileged live entrypoint findings from operator/config/pre-activation findings), keeping root `AGENTS.md` / `CLAUDE.md` unchanged at `30` lines.
4. **Deferred Schema & Gate Decisions (`Post-Wave-1`):**
   - Defer SQLite schema additions (typed privilege/tier columns, new `G6`/`H9` gates, or peer-oracle FTS indexing) until all active Wave-1 multi-language campaigns conclude so `v3.3` consolidates empirical findings across C, Rust, Go, and Solidity in one pass.

## Consequences

- Archived, deprecated, or stale mirrors/repositories fail deterministically in `< 10ms` offline on `ajar init` and remotely via `ajar doctor --target`.
- Existing `v3.2.2` `run.db` ledgers remain `100%` schema-compatible with zero migration overhead.

## Risks and Revisit Triggers

- **Risks:** Legitimate mature C/library repositories may go `> 90` days without a commit despite remaining active in production; operators can verify upstream parity via `ajar doctor --target` and pass `--allow-historical-target` when appropriate.
- **Revisit Trigger:** Revisit typed privilege/reachability columns and peer-oracle indexing after all Wave-1 campaigns (`git-wave1a`, `kona-wave1b`, and Wave-1B Track 1/Track 2 runs) finish.
