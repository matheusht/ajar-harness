# Ajar Engineering Guide

Read this file before modifying `ajar/`, `skills/`, `benchmarks/`, `docs/`, or `tests/`.

## Architectural Invariants

1. **Zero-LLM Engine (`ajar/`):** Never add LLM SDK imports, prompt templates, or network inference calls inside core state, gate, or reproduction modules (`ajar/db.py`, `ajar/gates.py`, `ajar/repro_*.py`, `ajar/patch_verify.py`, `ajar/graph.py`). Keep `ajar/` deterministic, fast, and standard-library-first.
2. **Root `AGENTS.md` Budget (`<= 50` Lines):** Keep root `AGENTS.md` and `CLAUDE.md` byte-identical, written in ASD-STE100 (imperative mood, one instruction per sentence, concrete commands), and strictly `<= 50` lines (`wc -l < AGENTS.md`).
3. **External Run State:** Every runtime table, worktree, cache, and log belongs under `~/.ajar/runs/<run_id>/`. Never write `.ajar/` state files inside a target checkout.
4. **Terminology Hygiene:** Use Ajar Labs' canonical product nouns (`Platform`, `Code`, `Fixes`, `Security reviews`, `Supply chain`) and canonical workflow verbs (`quote`, `map`, `investigate`, `falsify`, `rescope`, `reproduce`, `chain`, `patch`, `report`). Never reintroduce retired v1/v2 terms enforced by `tests/test_conformance.py`.
5. **Frozen Historical Closure (`tools/legacy/` and `engagements/`):** Treat `tools/legacy/` and `engagements/{cve-bench,cybench,xbow-benchmarks}` as read-only historical archives. Never import `tools/legacy/` from `ajar/`.

## Module Map (`ajar/`)

| Module | Responsibility |
| --- | --- |
| `ajar/db.py` | SQLite WAL schema (`v3.1`), `O_NOFOLLOW` run dirs, bi-directional task leases, prefix-stable `< 4 KB` context, `steers`, `rescope_claim`, bindings, anomalies, primitives, pulse |
| `ajar/gates.py` | Pure-SQL closeout gates `G1–G5`, anti-premature-`dry` guarded-primitive gate, `25%` dry-surface token breaker, attribution, and `Code` `35%` COGS margin gates |
| `ajar/repro_source.py` | Bare-shared `repo.git` mirror, `slot-<k>` worktrees, `+2 s` `watermark_ns`, anti-mitigation + `claim.locus` overlap validator, 4-arm source runner |
| `ajar/patch_verify.py` | 8-Arm Production Remediation Gate (`ajar patch verify`: Arms 1–4 + full suite + `>= 3` bypass variants + caller NULL/error audit + sibling-route symmetry) |
| `ajar/repro_binary_live.py` | 4-arm `binary` (ASLR-normalized PC + ablation + runtime guard) and `live` (128-bit CSPRNG canary + teardown) runners |
| `ajar/repomap.py` | Pure-Python symbol extraction, Personalized PageRank map, `ajar quote` full/diff LOC counter, and `35%` COGS cap calculator |
| `ajar/graph.py` | Deterministic `Platform` component, trust-boundary, and attack-flow JSON exporter (`ajar-platform-graph/1`) |
| `ajar/oracles.py` | SQLite FTS5 indexing and queries for `intent`, `reachability`, and `precedent` |
| `ajar/hooks.py` | Host Mode `claude-stop` hook and `codex`/`omp` continuation loop with 3-stall circuit breaker |
| `ajar/mcp.py` | Thin STDIO JSON-RPC MCP wrapper delegating directly to `ajar` operations |
| `ajar/runner.py` | Standalone Mode (`ajar run`) scheduler with `--discover-passes N`, role-tier model routing, dry-surface breaker, and `80% / 20%` verify reserve |
| `ajar/report.py` | Markdown and JSON report compiler including `active_steers`, `patch_verifications`, and `CLOSEOUT_RECEIPT` |
| `ajar/redact.py` | Secret pattern scanner and redactor enforced before SQLite writes and report emission |
| `ajar/cli.py` | Command-line interface entrypoint (`ajar`) |

## Extending Skills, Corpora, and Benchmarks

- **Contrastive Domain Packs (`skills/domains/<domain>/SKILL.md`):** Every pattern row must state (1) `Defect Pattern & Sinks`, (2) `Compensating Control That Makes It Safe`, and (3) `4-Arm Verification Recipe`, while respecting the anti-premature-`dry` rule when guarded inner primitives exist.
- **Reference Corpora (`skills/references/*.md`):** Cite primary CVE, GHSA, ZDI, Project Zero, or contest ruling identifiers with full untrimmed IDs, CVSS vectors, and 40-character commit SHAs where applicable.
- **Benchmarks (`benchmarks/foundry/` and `benchmarks/hermetic/`):** Every benchmark must pair a vulnerable case with a deterministic `patched-control` or negative-control twin and run offline without external credentials.

## Required Verification Before Opening a PR

Run all four checks from the repository root and disclose results in the PR description:

```bash
test "$(wc -l < AGENTS.md)" -le 50 && cmp -s AGENTS.md CLAUDE.md
ruff check ajar tests
pytest -q
for t in tools/legacy/*-test.py; do python3 "$t"; done
```
