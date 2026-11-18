# Ajar Engineering Guide

Read this file before modifying `ajar/`, `skills/`, `benchmarks/`, `docs/`, or `tests/`.

## Architectural Invariants

1. **Zero-LLM Engine (`ajar/`):** Never add LLM SDK imports, prompt templates, or network inference calls inside `ajar/`. Keep `ajar/` deterministic, fast, and standard-library-first.
2. **Root `AGENTS.md` Budget (`<= 50` Lines):** Keep root `AGENTS.md` and `CLAUDE.md` identical, written in ASD-STE100 (imperative mood, one instruction per sentence, concrete commands), and strictly `<= 50` lines (`wc -l AGENTS.md`).
3. **External Run State:** Every runtime table, worktree, cache, and log belongs under `~/.ajar/runs/<run_id>/`. Never write `.ajar/` state files inside a target checkout.
4. **Terminology Hygiene:** Use Ajar's canonical product nouns (`Code`, `Fixes`, `Security reviews`, `Supply chain`) and canonical workflow verbs (`map`, `investigate`, `falsify`, `reproduce`, `chain`, `patch`, `report`). Never reintroduce retired v1/v2 terms enforced by the conformance test suite.
5. **Frozen Historical Closure (`tools/legacy/` and `engagements/`):** Treat `tools/legacy/` and `engagements/{cve-bench,cybench,xbow-benchmarks}` as read-only historical archives. Never import `tools/legacy/` from `ajar/`.

## Module Map (`ajar/`)

| Module | Responsibility |
| --- | --- |
| `ajar/db.py` | SQLite WAL schema, `O_NOFOLLOW` run directory creation, task leases, salience, bindings, anomalies, primitives, claims, pulse |
| `ajar/gates.py` | Pure-SQL closeout gates `G1–G5`, `dry` locus validation, attribution, and `Code` unit economics (`cost_usd_per_kloc`) |
| `ajar/repro_source.py` | Bare-shared `repo.git` mirror, `slot-<k>` worktrees, `+2 s` `watermark_ns`, anti-mitigation diff validator, 4-arm source runner |
| `ajar/repro_binary_live.py` | 4-arm `binary` (ASLR-normalized PC + ablation + runtime guard) and `live` (128-bit CSPRNG canary + teardown) runners |
| `ajar/repomap.py` | Pure-Python symbol extraction and Personalized PageRank token-budgeted map |
| `ajar/oracles.py` | SQLite FTS5 indexing and queries for `intent`, `reachability`, and `precedent` |
| `ajar/hooks.py` | Host Mode `claude-stop` hook and `codex`/`omp` continuation loop with 3-stall circuit breaker |
| `ajar/mcp.py` | Thin STDIO JSON-RPC MCP wrapper delegating directly to `ajar` operations |
| `ajar/runner.py` | Standalone Mode (`ajar run`) multi-worker scheduler with `80% / 20%` verification budget reserve |
| `ajar/report.py` | Markdown and JSON report compiler and `CLOSEOUT_RECEIPT` generator |
| `ajar/redact.py` | Secret pattern scanner and redactor enforced before SQLite writes and report emission |
| `ajar/cli.py` | Command-line interface entrypoint (`ajar`) |

## Extending Skills, Corpora, and Benchmarks

- **Contrastive Domain Packs (`skills/domains/<domain>/SKILL.md`):** Every pattern row must state (1) `Defect Pattern & Sinks`, (2) `Compensating Control That Makes It Safe`, and (3) `4-Arm Verification Recipe`, and preserve the Step-2 Divergence Exit rule (`ajar task dry`).
- **Reference Corpora (`skills/references/*.md`):** Cite primary CVE, GHSA, ZDI, Project Zero, or contest ruling identifiers with full untrimmed IDs, CVSS vectors, and 40-character commit SHAs where applicable.
- **Benchmarks (`benchmarks/foundry/` and `benchmarks/hermetic/`):** Every benchmark must pair a vulnerable case with a deterministic `patched-control` or negative-control twin and run offline without external credentials.

## Required Verification Before Opening a PR

Run all four checks from the repository root and disclose results in the PR description:

```bash
test "$(wc -l < AGENTS.md)" -le 50
ruff check ajar tests
pytest -q
for t in tools/legacy/*-test.py; do python3 "$t"; done
```
