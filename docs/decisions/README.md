# Architecture Decision Records

This directory records architectural decisions for Ajar.

## Active Decisions

| ADR | Title | Status | Summary |
| --- | --- | --- | --- |
| [0017](0017-ajar-v3-dual-mode-architecture.md) | Ajar v3 Dual-Mode Verification Architecture | **Accepted (Active)** | Defines the zero-LLM SQLite WAL state engine (`run.db`), Host Mode + Standalone Mode execution, 4-arm causal reproduction (`source`/`binary`/`live`), deterministic SQL gates `G1–G5`, contrastive domain packs, `zero_skill` first-principles quota, and ASD-STE100 documentation rules. |
| [0018](0018-ajar-v3-1-bug-brain-and-platform-economics.md) | Ajar v3.1 Bug-Brain Upgrades, 8-Arm Fixes Gate, and Platform Economics | **Accepted (Active)** | Adds bi-directional task search, anti-premature-`dry` guarded primitives, locus-bound 4-arm path proof + `claim rescope`, Stage-5 `Converge`, 8-arm `ajar patch verify`, attributable `Steers`, prefix-stable KV caching, `ajar quote` + `35%` COGS cap + `25%` dry-surface breaker, and `ajar export-graph`. |
| [0019](0019-ajar-v3-2-hooks-and-composable-repro.md) | Ajar v3.2 Event-Driven Epistemic Hooks, Composable Stage Builders, and 9-Arm Fixes Gate | **Accepted (Active)** | Adds zero-overhead epistemic micro-hooks (`H1`–`H8`) with mandatory `Kill Rule` lines, cross-subsystem `provides_tags <-> requires_tags` bridges, `StageContext` helpers + $N$-step chain ablation, Arm 5A/5B `--release-cmd` UB differential, 9-arm `ajar patch verify` (`git apply -R`), `<= 3,500` LoC call slices, and PR `--diff` state sync. |
| [0020](0020-ajar-v3-2-2-swarm-wire-profiles-and-reopen.md) | Ajar v3.2.2 Stage-Split Swarm Wire Profiles, Runtime Anti-Cheat Gates, Hybrid Storage, and Cross-VM Reopen | **Accepted (Active)** | Adds `ajar swarm {packet,fallback,complete,status}` (`direct -> swarm_patch_first -> regression_tdd` + batch splitting), structural claim prose & `--env-blocker` gates, entrypoint fidelity + anti-source-grep enforcement, `/tmp/ajar-build-cache` + compact shared mirror sync, and cross-VM `ajar reopen`. |

## Superseded Historical Decisions

- **`0001` through `0013` (`0001-*.md` .. `0013-*.md` in this directory):** **Superseded by [ADR-0017](0017-ajar-v3-dual-mode-architecture.md).** Retained strictly as immutable historical context for the archived benchmark runs under `engagements/{cve-bench,cybench,xbow-benchmarks}` and the read-only reader closure in `tools/legacy/`.
- **`0014` through `0016` (unmerged v2 pull-request drafts `#209`, `#220`, `#224`):** **Superseded before merge by [ADR-0017](0017-ajar-v3-dual-mode-architecture.md).**

## Authoring Rules

1. Read [ADR-0017](0017-ajar-v3-dual-mode-architecture.md), [ADR-0018](0018-ajar-v3-1-bug-brain-and-platform-economics.md), [ADR-0019](0019-ajar-v3-2-hooks-and-composable-repro.md), [ADR-0020](0020-ajar-v3-2-2-swarm-wire-profiles-and-reopen.md), and [docs/architecture.md](../architecture.md) before proposing any structural change.
2. Number new decision records sequentially starting at `0021`.
3. Write in concise ASD-STE100 technical prose and include explicit Context, Decision, Consequences, Risks, and Revisit Triggers sections.
4. Never delete or rewrite historical ADR files; mark superseded records with a pointer to the replacing ADR.
