# ADR-0018: Ajar v3.1 Bug-Brain Upgrades, 8-Arm Fixes Gate, and Platform Economics

- **Status:** Accepted (Active)
- **Date:** 2026-11-18
- **Extends:** [ADR-0017](0017-ajar-v3-dual-mode-architecture.md)

## Context

[ADR-0017](0017-ajar-v3-dual-mode-architecture.md) established Ajar's zero-LLM SQLite WAL verification kernel (`run.db`), dual-mode execution (Host Mode + Standalone Mode), 4-arm causal reproduction, and SQL closeout gates `G1–G5`. Reviewing the retired v1/v2 `engine/*.md` playbooks alongside live multi-target audit failure modes and unit-economics constraints revealed seven high-value bug-hunting capabilities and two product-boundary gaps that needed deterministic enforcement without reintroducing prose bloat:

1. **Entrypoint-only blindness & premature `dry` closures:** Mapping only external HTTP/RPC routes misses inner state/accounting sinks and FFI boundaries, and workers closing surfaces `dry` at the first upstream check miss multi-step guard breaks.
2. **Causal locus drift (`claim_mismatch`):** A 1–5 line micro-patch could pass Arms 1–4 while editing a file or function different from the claimed root-cause `locus`, and falsifiers lacked an in-place `rescope` transition when root cause or severity shifted.
3. **Production remediation regressions (`GhostLock` & variant bypasses):** A 1–5 line micro-patch proves causal root cause (`micropatched`), whereas shipping customer `Fixes` (`maintainer_patched`) requires full test suite execution, `>= 3` bypass variants, caller NULL/error-return safety, and sibling-route symmetry.
4. **Gross-margin inversion on `Code` quotes:** Setting `budget_usd == code_quote_usd` permits model token COGS to consume `100%` of revenue on dry surfaces unless commercial runs enforce a `35%` COGS ceiling and a per-surface zero-signal token breaker.
5. **Operator threat-model steering & `Platform` visibility:** Operators need first-class, attributable `Steers` (`scope_authority` vs `research_steering`) and a deterministic component/attack-flow JSON graph (`ajar export-graph`) feeding the `Platform` whiteboard.

## Decision

Extend `ajar` (`v3.1.0`) and `skills/ajar-*/SKILL.md` with nine deterministic mechanisms:

1. **Bi-Directional Task Directions (`tasks.direction`):** Support `outside_in`, `inside_out`, `native_ffi`, and `peer_symmetry` on `ajar task add`, seeded automatically across `--discover-passes N` in `ajar run`.
2. **Guarded-Primitive Anti-Premature-`dry` Gate (`primitives.guarded_by_locus`):** Reject `ajar task dry` (`check_guarded_primitive_dry_block`) whenever an unchained primitive on the same surface/subsystem has `guarded_by_locus != ''` and zero `chain` evaluation or `conditional_blocked` predicate exists.
3. **Locus-Bound 4-Arm Path Proof & `ajar claim rescope`:** Require source `--micropatch` hunks in `validate_micropatch_diff` to overlap `claim.locus` (`±60` lines) or an explicit `--shared-guard-locus`, raising `claim_mismatch:` otherwise; provide `ajar claim rescope` to update shifted loci, preconditions, or severity cleanly.
4. **Stage-5 `Converge` Synthesis (`skills/ajar-chain/SKILL.md` & `G5`):** Trigger Stage-5 `chain` convergence whenever `>= 2` composable signals or any guarded primitive exist, encoding Invariant-Pair Guard Breaking, the 6 Chain Angle-Shapes, Attack-Your-Own-Caps, and Marginal-Contribution Critique.
5. **Two-Stage Remediation (`ajar patch verify` — 8-Arm `Fixes` Gate):** Keep `ajar claim reproduce` fast (Arms 1–4 -> `micropatched`) and add `ajar patch verify` (`ajar/patch_verify.py`) enforcing Arms 1–4 + Arm 5 (`--suite-cmd`) + Arm 6 (`>= 3` `--variant-cmd` bypass variants) + Arm 7 (`--caller-audit`) + Arm 8 (`--sibling-audit`) before setting `remediation_state = 'maintainer_patched'`.
6. **Attributable Workspace `Steers` (`ajar steer add|list|revoke`):** Persist scoped rules (`global`, `subsystem`, `path`) in `steers`, automatically logging `human_touches` (`scope_authority` preserves `found_autonomously_by_ajar`; `research_steering` marks `found_with_ajar`).
7. **Prefix-Stable `< 4 KB` Prompt Caching & Role-Tier Model Routing:** Place run-invariant sections (`Goal`, `Active Workspace Steers`, sorted `Certified Bindings`) at the top of `render_task_context` for KV cache hits, and route Standalone tasks across `AJAR_MODEL_REASON`, `AJAR_MODEL_HUNT`, and `AJAR_MODEL_FALLBACK`.
8. **`ajar quote`, `35%` COGS Cap, & `25%` Dry-Surface Breaker:** Add `ajar quote <target> [--diff <base..head>]`; default commercial `cogs_cap_usd` to `0.35 * code_quote_usd` (`>= 65%` gross margin floor) while preserving explicit `--cogs-cap` / `--budget` overrides; throttle open `investigate` tasks on any surface burning `> 25%` of budget in `explore` phase with zero signal.
9. **Deterministic `Platform` Graph Exporter (`ajar export-graph`):** Emit `ajar-platform-graph/1` JSON combining surfaces, repomap call edges, primitives, anomalies, verified `dry` guards, active `Steers`, findings, and chains.

## Consequences

- Restores high-signal bug-hunting heuristics (12 PoC interrogation lenses, sample enumeration `N`, 6 chain angle-shapes, guarded-sink persistence, caller NULL-return checks) inside concise ASD-STE100 skills backed by SQL/Python gates rather than prose essays.
- Keeps root `AGENTS.md` and `CLAUDE.md` byte-identical at `<= 50` lines and maintains zero LLM imports inside core state/gate/reproduction modules.

## Risks

- **Over-strict locus window (`±60` lines):** Large functions where a root-cause check sits `> 60` lines above the crash line could trigger `claim_mismatch:`. Mitigated by `--shared-guard-locus` and `ajar claim rescope`.
- **Dry-surface breaker firing on huge monolith surfaces:** If an operator registers an entire repository as a single coarse surface, `25%` explore spend may trip early. Mitigated by granular surface registration in `skills/ajar-map/SKILL.md`.

## Revisit Triggers

- Revisit the `±60`-line locus overlap window if `> 10%` of valid source reproductions require `--shared-guard-locus`.
- Revisit the `0.35 * quote` COGS ratio and `25%` dry-surface threshold after the first 10 commercial `Code` repositories measure empirical token-cache hit rates.
