# Ajar Agent Instructions (v3.6-Balanced)

Ajar (built by Ajar Labs) is a Three-Ring Earned-Mass autonomous security verification engine (`L4 · C3 · B3`).
Your product is mechanical `C3` proof in a clean `git worktree`, not plausible prose. Every external advisory must pass 5-stage `C3` verification (`3x` attributed fail -> fuzzy patch apply -> mandatory post-patch rebuild -> `3x` pass + upstream suite -> Cross-Family Critic).

## Three-Ring Architecture (Policed by `extra/sz_ajar.py`)

1. **Ring 0 (`<= 1,800` SLOC hard cap, `0` upward imports):** `cli.py` (4 verbs: `run`, `verify`, `bench`, `report` + 7 `--disable-*` ablation flags), `llm.py` (stdlib async HTTP + reservation `CostMeter`), `agent.py` (free bash/read/search/edit inner loop + `SpanTracker`), `verify.py` (sole `git worktree` owner & 5-stage `C3` judge).
2. **Ring 1 (7 Toggleable Earned-Muscle Modules):** `repomap.py` (PageRank + `.ajar/REALITY.md`), `whiteboard.py` (lock-free `events.jsonl` -> atomic `WHITEBOARD.md`), `epistemic.py` (`<= 180` SLOC `seen_spans` guard), `chain_weaver.py` (12-Type `EffectType` + backward `WISH` abduction), `autobuild.py` (polyglot `.ajar/build.sh` + write-jailed Build Doctor + `Input Encoder`), `swarm.py` (8-worker async + 45m pivot + 65%/70% relay + 92% drain), `bench.py` (local Phase-0 + Leave-One-Out rent scorer).
3. **Ring 2 (Uncapped Assurance):** `tests/`, `extra/sz_ajar.py`, `prompts/GOAL-01..05.md`.

## Core Workflow (`ajar run` -> `ajar verify` -> `ajar report`)

- **Swarm Run:** `ajar run <repo> --workers 8 --budget-usd 50 --profile upstream [--disable-<module>]`
- **Mechanical `C3` Verification:** `ajar verify <repo> [--runs 3] [--offline]`
- **Local On-Demand Bench (`0` paid CI gates):** `ajar bench --phase0` / `python3 extra/sz_ajar.py .`
- **Export Reports:** `ajar report <repo> --out <dir>` (`advisories/` vs. `hardening-notes/`; withdrawn drafts omitted per `DEC-0139`; `100/100` voice lint).

## Non-Negotiable Boundaries

1. **Zero Third-Party LLM SDKs & Strict Ring Isolation:** `src/ajar/` stays pure Python stdlib; only `verify.py` invokes `git worktree`; Ring 0 never imports Ring 1 except lazy CLI dispatch.
2. **Pure Conductor Discipline & Two-Tier Pincer:** Exclude `tests/`/`docs/`/`benchmarks/` at minute zero; trace 100% forward entrypoints and 100% backward Crown-Jewel sinks.
3. **Secret & Path Hygiene:** Never commit credentials, tokens, PII, `.ajar/` artifacts, or developer home paths.
4. **External Action Gate:** Never submit advisories, contact vendors, or publish findings without explicit founder approval.
