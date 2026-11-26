# Architecture Decision Records

This directory preserves Ajar's architectural decision history.

## Active Architecture (`v3.6-Balanced`)

The active system is **Ajar v3.6-Balanced** (Three-Ring Earned-Mass autonomous verification engine, `L4 · C3 · B3`), documented in:

- [docs/architecture.md](../architecture.md) — Ring 0 (`cli.py`, `llm.py`, `agent.py`, `verify.py`), Ring 1 (7 toggleable muscles), 4 CLI verbs (`run`, `verify`, `bench`, `report`), `.ajar/` state layout, and 5-stage `C3` verification.
- [docs/campaigns-and-roadmap.md](../campaigns-and-roadmap.md) — Phase-0 probes (`P0-A`..`P0-D`) and the Leave-One-Out Earned-Mass rent rule.
- [docs/engineering/AGENTS.md](../engineering/AGENTS.md) — Mechanical enforcers (`extra/sz_ajar.py`, `tools/arch_lint.py`) and pre-PR verification.

## Superseded Historical Decisions (`archive/v3.4-legacy`)

All prior ADRs (`0001` through `0025`) are **superseded by `v3.6-Balanced`**. They remain untouched in this directory strictly as immutable historical context; the legacy `v3.4` codebase they describe is preserved in git at tag **`archive/v3.4-legacy`**. Do **not** invoke CLI commands, schemas, or modules referenced in `0001..0025` against `v3.6-Balanced`.

| ADR Range | Era | Status | Notes |
| --- | --- | --- | --- |
| `0001`–`0013` (`0001-*.md` .. `0013-*.md`) | `v1` / `v2` | **Superseded** | Historical context for archived benchmark runs under `engagements/` and read-only readers under `tools/legacy/`. |
| `0014`–`0016` | Unmerged `v2` drafts | **Superseded** | Never merged; superseded before `v3.0`. |
| `0017`–`0025` (`0017-*.md` .. `0025-*.md`) | `v3.0`–`v3.4` | **Superseded by `v3.6-Balanced`** | Legacy dual-mode SQLite orchestration architecture preserved at git tag `archive/v3.4-legacy`. |

## Authoring Rules for New ADRs

1. Read [docs/architecture.md](../architecture.md), [docs/engineering/AGENTS.md](../engineering/AGENTS.md), and [`extra/sz_ajar.py`](../../extra/sz_ajar.py) before proposing any structural change.
2. Number new `v3.6+` decision records sequentially starting at `0026`.
3. Keep prose plain-spoken and concise, with explicit **Context**, **Decision**, **Consequences**, **Risks**, and **Revisit Triggers** sections.
4. Never delete or rewrite historical ADR files `0001..0025`.
