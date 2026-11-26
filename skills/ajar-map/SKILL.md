---
name: ajar-map
description: Map attack surfaces, Crown-Jewel sinks, and build recipes using Ajar v3.6 repomap.py (.ajar/REALITY.md), autobuild.py (.ajar/build.sh), and stigmergic whiteboard seeding.
---

# Ajar Map (`v3.6-Balanced`)

Use this skill at the start of an audit to orient on production code, build a working sanitizer harness, and seed forward/backward targets on the stigmergic whiteboard.

## 1. Pure Conductor Discipline & Structural Map (`repomap.py`)

1. Exclude `tests/`, `docs/`, and `benchmarks/` at minute zero. Never spend mapping budget on test fixtures or mock harnesses.
2. Start the swarm or generate `.ajar/REALITY.md` and `.ajar/build.sh` via `ajar run` (or inspect `.ajar/REALITY.md` produced by `repomap.build_repomap_and_reality`):
   ```bash
   ajar bench --phase0
   ajar run <repo> --workers 8 --budget-usd 50 --profile upstream
   ```
3. Read `.ajar/REALITY.md` first: it ranks production files by Personalized PageRank, lists detected build manifests (`CMakeLists.txt`, `Cargo.toml`, `go.mod`, `pyproject.toml`, `package.json`, `foundry.toml`), and enumerates entrypoints and high-value sinks (`memcpy`, `realloc`, `system`, `subprocess`, `delegatecall`, `transferFrom`, `mulDiv`, `exec.Command`, `cursor.execute`, etc.).
4. Verify `.ajar/build.sh` and `.ajar/build_recipe.json` (synthesized by `autobuild.py` under `upstream`, `debian`, or `al2023` ASan/UBSan profiles). If the initial build fails, let `run_build_doctor` repair `.ajar/build.sh` inside its write-allowlist jail before deep auditing.

## 2. Two-Tier Pincer Coverage

Trace both directions so neither outer parsers nor deep state transitions are missed:

1. **100% Forward Entrypoints:** Unauthenticated network/RPC/HTTP/wire parsers, CLI/archive/file decoders, public smart-contract entrypoints, and cross-tenant APIs reachable by unprivileged principals.
2. **100% Backward Crown-Jewel Sinks:** Memory/FFI boundaries (`memcpy`, `memmove`, `realloc`, `free`, `unsafe`), command/SQL/file sinks, privilege/auth transitions, and asset/accounting mutations (`delegatecall`, `transferFrom`, `mulDiv`).
3. **Peer Symmetry & Sibling Routes:** Note paired lifecycle handlers (`create`/`update`/`delete`, `deposit`/`withdraw`, `v1`/`v2`) where one path may omit a check enforced on its sibling.

Separate **unprivileged external principals** from **permissioned operators or local admins** before prioritizing surfaces. Never rank operator-only or test-only paths as high-priority targets unless explicitly in scope.

## 3. Seed `.ajar/WHITEBOARD.md` (`whiteboard.py`)

Record verified orientation facts in `.ajar/events.jsonl` (projected atomically to `.ajar/WHITEBOARD.md`):

- **`insight` / `invariant`:** Exact trust boundaries, verified guards with `path:line` spans, and build/test commands.
- **`bounty`:** High-value unaudited entrypoints or sibling seams for `surface_scout` and `deep_auditor` workers.
- **`wish`:** Backward Crown-Jewel sinks awaiting a matching upstream `EffectType` and `CarrierKind` (consumed by `chain_weaver.py`).

## Exit Check

Before moving to deep investigation, confirm:
- `.ajar/REALITY.md` covers production entrypoints and Crown-Jewel sinks with `tests/`/`docs/`/`benchmarks/` excluded.
- `.ajar/build.sh` builds cleanly (or `static_only` is recorded honestly if no compiler/runtime exists).
- Initial `bounty`, `invariant`, and `wish` entries are visible in `.ajar/WHITEBOARD.md`.
