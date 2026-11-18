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
| `ajar/db.py` | SQLite WAL schema (`v3.2`), `O_NOFOLLOW` run dirs, bi-directional task leases, `checkpoint_task`, `record_coverage_span`, prefix-stable `< 4 KB` context, `steers`, `rescope_claim`, bindings, pulse |
| `ajar/epistemic_hooks.py` | Event-driven `H1`–`H8` epistemic micro-hooks (`0` overhead on clean code, mandatory `Kill Rule`, `max_leases` expiry) and `provides_tags <-> requires_tags` capability bridges |
| `ajar/repro_compose.py` | `StageContext` runtime, `0444` `ajar primitive promote-helper`, container loopback socket guard (`sitecustomize.py`), `slot-<k>` chain reproduction with $N$-step causal ablation, and `slot-inst` `ajar claim instrument` |
| `ajar/repro_source.py` | Bare-shared `repo.git` mirror, `slot-<k>` worktrees, `+2 s` `watermark_ns`, `claim.locus` overlap validator, 4-arm source runner + Arms `5A`/`5B` `--release-cmd` UB differential |
| `ajar/patch_verify.py` | Hardened 9-Arm Production Remediation Gate (`ajar patch verify`: Arms 1–4 + cached baseline suite diff + clean-`HEAD` variant trigger check + caller/sibling cmds + Arm 9 `git apply -R` revert proof) |
| `ajar/diff_sync.py` | Incremental PR differential state sync (`ajar init --diff <base..head> --parent-run <id>`) classifying `kept | closed | invalidated_guard | new` |
| `ajar/gates.py` | Pure-SQL closeout gates `G1–G5`, `GAP-01`-hardened guarded-primitive `dry` gate, `config_gated` probe gate, `debug_assert_only` severity gate, and `35%` COGS margin gates |
| `ajar/repro_binary_live.py` | 4-arm `binary` (ASLR-normalized PC + ablation + runtime guard) and `live` (128-bit CSPRNG canary + teardown) runners |
| `ajar/repomap.py` | Pure-Python symbol extraction, Personalized PageRank map, `<= 3,500` LoC call-slice splitter (`--slice-cap`), `< 1 KB` `skeleton_md`, and `ajar quote` full/diff calculator |
| `ajar/graph.py` | Deterministic `Platform` component, hook, helper, coverage, and attack-flow JSON exporter (`ajar-platform-graph/1`) |
| `ajar/oracles.py` | SQLite FTS5 indexing and queries for `intent` (`[UNTRUSTED_TARGET_DOC]` tagged), `reachability`, and `precedent` |
| `ajar/hooks.py` | Host Mode `claude-stop` hook and `codex`/`omp` continuation loop with 3-stall circuit breaker |
| `ajar/mcp.py` | Thin STDIO JSON-RPC MCP wrapper delegating directly to `ajar` operations |
| `ajar/runner.py` | Standalone Mode (`ajar run`) scheduler with `--discover-passes N`, role-tier model routing, `detect_soliloquy_transcript`, dry-surface breaker, and `80% / 20%` verify reserve |
| `ajar/report.py` | Markdown and JSON report compiler including `ub_divergence_class`, `ablation_matrix_json`, `patch_verifications`, and `CLOSEOUT_RECEIPT` |
| `ajar/redact.py` | Secret pattern scanner and redactor enforced before SQLite writes and report emission |
| `ajar/cli.py` | Command-line interface entrypoint (`ajar`) |

## Required Verification Before Opening a PR

Run all four checks from the repository root and disclose results in the PR description:

```bash
test "$(wc -l < AGENTS.md)" -le 50 && cmp -s AGENTS.md CLAUDE.md
ruff check ajar tests
pytest -q
for t in tools/legacy/*-test.py; do python3 "$t"; done
```
