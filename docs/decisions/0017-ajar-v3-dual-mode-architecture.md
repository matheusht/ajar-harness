# ADR 0017: Ajar v3 Dual-Mode Verification Architecture

- **Status:** Accepted (Active)
- **Date:** 2026-11-18
- **Supersedes:** ADR-0001 through ADR-0013 (`0001-casebooks-patterns-routing.md` .. `0013-native-research-workspace-contract.md`) and unmerged v2 draft ADRs `0014`–`0016` (PRs `#209`, `#220`, `#224`)

## Context

Across v1 and v2, this repository accumulated two incompatible operating models (`legacy` Docker/JSONL record-kernel queues from Decisions 0005/0006 and an unfinished `candidate native` Python prototype), 1,275 files of prompt-jailbreak/steganography/target-specific scaffolding (`etrack`, `p4rs3lt0ngv3`, `st3gg`, `eni-novelist`, `Kanboard`, `GEPA`), and prose-heavy agent instructions (`AGENTS.md` + `docs/wiki/` + `engine/`). That complexity caused four recurring failure modes:

1. **Premature Stopping and Context Pollution:** Interactive coding agents declared completion after shallow surface reads, or lost real crash/state anomalies when an initial exploit hypothesis was refuted.
2. **Prose Over Causal Proof:** Multi-reviewer text panels (`adjudication`) rewarded persuasive narratives instead of deterministic root-cause execution evidence, while `Zone-2` confirmation gates blocked even offline local Anvil/Foundry tests.
3. **Checklist Anchoring:** Long vulnerability cards biased agents toward pattern-matching known templates instead of reading target state invariants from first principles or exiting quickly when an upstream guard held.
4. **Target-Tree Contamination and Subscription Friction:** Writing state inside target checkouts risked dirtying customer git trees or letting target-repo `CLAUDE.md`/`AGENTS.md` files shadow Ajar's rules, and requiring separate LLM SDK keys prevented zero-marginal-cost execution inside existing Claude Code, Codex, and OpenCode subscriptions.

## Decision

Adopt the **Ajar v3 Dual-Mode Verification Architecture** governed by 14 binding architectural decisions (`D-01` through `D-14`):

1. **`D-01` — Dual-Mode Execution & Zero-LLM Core (`ajar/`):** `ajar` ships as a lightweight Python 3.11+ CLI and optional 150-LOC STDIO MCP server (`ajar mcp`) with zero LLM SDK dependencies inside core modules. Host Mode runs inside interactive subscription coding agents; Standalone Mode (`ajar run <target> --budget <USD>`) schedules local worker processes against the same `run.db` with an `80% / 20%` explore-vs-verify budget reserve.
2. **`D-02` — External SQLite WAL State Store (`run.db`):** All active state lives in `~/.ajar/runs/<run_id>/run.db` (`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=30000;`), separating the **Work axis** (`surfaces`, `surface_drivers`, `tasks`) from the **Truth axis** (`claims`, `findings`, `chains`) with orthogonal `research_state`, `evidence_state`, `customer_state`, and `remediation_state` columns.
3. **`D-03` — Deterministic SQL Closeout Gates (`G1–G5`):** `ajar finish` enforces five pure-SQL invariants without LLM self-grading: `G1` (`exhaustive-high` vs `first-verified-high` coverage), `G2` (zero unresolved claims), `G3` (4-arm causal proof + `proposer_worker_id != falsifier_worker_id`), `G4` (Zero-Skill worker quota + verified `file:line` on `dry` closures), and `G5` (zero `unexplained` anomalies + multi-primitive `chain` evaluation).
4. **`D-04` — Dual Workspace Geometry (`--envelope` & `--in-place`) + Symlink Hardening:** Default `--envelope` creates `~/.ajar/runs/<run_id>/env/` (`AGENTS.md` + `skills/` + `./target` worktree) to prevent target prompt shadowing; `--in-place` supports fixed-path build environments while keeping `run.db` external. File operations enforce `O_NOFOLLOW` containment and mandatory secret redaction (`ajar/redact.py`).
5. **`D-05` — Warm Worktree Pool & 4-Arm `SourceAdapter`:** Source reproduction runs against a bare-shared `repo.git` mirror with reusable `worktrees/slot-<k>/` + `caches/cache-<k>/`, monotonic `+2 s` `watermark_ns` timestamp updates for sound incremental builds, an anti-mitigation diff validator (`1–5` production root-cause lines), and warm PoV-patch cross-kill deduplication (`duplicate_root_cause`).
6. **`D-06` — Multi-Target 4-Arm Verification (`source`, `binary`, `live`):** Binary targets prove causality via ASLR-normalized crash/trap PCs, input ablation, and runtime preload/wrapper guards; authorized live targets prove cross-principal impact via 128-bit CSPRNG canaries (`ajar_canary_<32hex>`) across all four arms plus verified teardown removal.
7. **`D-07` — Long-Horizon Memory & Anti-Context-Rot Primitives:** `anomalies` survive hypothesis falsification; `primitives` enable backward/forward exploit chaining; line-hashed `certified_bindings` bound `ajar context --task <id>` frames below `4 KB`; two unchanged failed reproductions trigger `needs_instrumentation`; and `ajar pulse` audits staleness every 8 closed tasks.
8. **`D-08` — Pure-Python Personalized PageRank `ajar map` & SQLite FTS5 Reference Indexes:** `ajar map` emits a token-budgeted (`1,500`-token default) structural map across Python, Rust, Solidity, Go, TS/JS, and C/C++, paired with SQLite FTS5 `intent`, `reachability`, and `precedent` query surfaces (`ajar ref query`).
9. **`D-09` — Contrastive Domain Packs + Zero-Skill First-Principles Quota:** Domain knowledge is consolidated into 5 contrastive packs (`evm-solidity`, `consensus-vm`, `rust-systems`, `web-api`, `auth-crypto`) with an explicit Step-2 Divergence Exit rule, paired with a mandatory `zero_skill` worker quota (`G4`) so novel logic bugs outside checklists are discovered from first principles.
10. **`D-10` — Progress-Aware Host Persistence Hooks (`3`-Stall Circuit Breaker):** `ajar hook claude-stop --if-active` and `ajar loop codex|omp` block premature Host Mode exits while `G1–G5` are unmet, releasing cleanly after 3 consecutive checks with zero new `events` progress.
11. **`D-11` — Clean ADR-0017 Cutover Without Disrupting Historical Archives:** Number this decision `0017`, mark `ADR-0001..0013` superseded, leave unmerged v2 draft PRs (`#209`, `#220`, `#224` occupying `0014..0016`) untouched on GitHub as superseded v2 drafts, and isolate the 54-file historical JSONL reader closure in `tools/legacy/` for frozen `engagements/{cve-bench,cybench,xbow-benchmarks}` records.
12. **`D-12` — Domain Scope Pruning:** Delete all prompt-jailbreak, persona, steganography, and single-target scaffolding; retain only the two general server-side application patterns (`untrusted-model-output-sink` from `llm05` and `client-controlled-tool-dispatch` from `llm06`) inside `skills/domains/web-api/SKILL.md`.
13. **`D-13` — Product Canon, Falsification Gate, Attribution & `Code` Unit Economics:** Align all nouns to `Code`, `Fixes`, `Security reviews`, and `Supply chain` and the canonical workflow `investigate -> falsify -> reproduce -> fix`; require `falsification_prediction` and `falsification_test` on every proposed claim; compute `found_autonomously_by_ajar` vs `found_with_ajar` from `human_touches`; and track `in_scope_loc` and `cost_usd_per_kloc` (`<= $2.00 / kLoC` COGS target).
14. **`D-14` — ASD-STE100 Documentation & Conformance Gate:** Keep root `AGENTS.md <= 50` lines in ASD-STE100 controlled technical English and enforce automated CI checks (`ruff`, `pytest`, `AGENTS.md` line budget, banned-jargon gate, and `tools/legacy/*-test.py`).

## Consequences

### Positive
- Eliminates dual-runtime ambiguity: one ~2,100-LOC zero-LLM Python package (`ajar`) powers interactive Host Mode and autonomous Standalone Mode identically.
- Replaces subjective prose panels with deterministic 4-arm reproduction (`Arm 1..4`) and independent challenger falsification (`proposer != falsifier`).
- Prevents context bloat and premature agent exit across large multi-hour repository audits while guaranteeing clean target checkouts.
- Preserves read-only auditability of historical benchmark runs via `tools/legacy/` without leaking retired terminology into active prompts or docs.

### Risks and Mitigations
- **Overly Broad Micro-Patches Masking Non-Bugs:** Mitigated by the AST/line-count anti-mitigation diff validator in `ajar/repro_source.py` plus Arm 4 benign-control regression checks.
- **Host Hook Infinite Loops on Externally Blocked Targets:** Mitigated by `ajar task block` (`conditional_blocked`), `ajar claim block`, and the 3-check zero-progress circuit breaker in `ajar/hooks.py`.
- **Regex Symbol Graph Gaps on Macro-Heavy Code:** Mitigated by `ajar ref query --kind reachability` FTS5 fallback and direct compiler/Foundry/cargo execution inside worktree slots.

## Revisit Triggers

1. **Tree-Sitter / SCIP Optional Indexer:** Revisit pure-Python regex symbol extraction if `ajar map` recall drops on macro-heavy C++ or procedural Rust crates (`> 250 kLoC`).
2. **Containerized Network Namespace Sandbox for `SourceAdapter`:** Add rootless `unshare -rn` / container wrapping around untrusted build scripts when onboarding `Supply chain` dynamic package-install targets.
3. **Maintainer Patch Benchmark Gate (Milestone 2):** Promote `Fixes` (`ajar-patch`) from micro-patch seeding to automated PR generation once maintainer-acceptance benchmarks validate idiom preservation and zero sibling-variant regressions.
