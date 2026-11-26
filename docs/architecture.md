# Ajar v3.6-Balanced Architecture

**Ajar** (built by **Ajar Labs**) is a **Three-Ring Earned-Mass** autonomous security verification engine (`L4 · C3 · B3`).

Legacy `v3.4` orchestration scaffolding (`~45k` LoC) is archived in git at tag `archive/v3.4-legacy`. `v3.6-Balanced` keeps bureaucratic middleware deleted and enforces a pure-stdlib `11`-module layout inside `src/ajar/`, policed mechanically by [`extra/sz_ajar.py`](../extra/sz_ajar.py) and [`tools/arch_lint.py`](../tools/arch_lint.py).

Ajar's product is mechanical `C3` proof inside a clean `git worktree`, not plausible prose. Every external advisory must pass 5-stage `C3` verification before export.

---

## 1. Three-Ring Module Layout (`src/ajar/`)

| Ring | Modules | Hard Rules (`extra/sz_ajar.py`) |
| --- | --- | --- |
| **Ring 0** *(Core Kernel)* | `cli.py`, `llm.py`, `agent.py`, `verify.py` | **`<= 1,800` SLOC total**, `0` upward imports into Ring 1 (except lazy CLI dispatch in `cli.py:main`), `verify.py` is the sole owner of `git worktree` and `C3` verdicts |
| **Ring 1** *(7 Earned Muscles)* | `repomap.py`, `whiteboard.py`, `epistemic.py`, `chain_weaver.py`, `autobuild.py`, `swarm.py`, `bench.py` | Toggleable via `7` `--disable-*` CLI flags, `epistemic.py <= 180` SLOC, anti-golf `Tokens/SLOC <= 10.5`, `0` semicolons, pure Python stdlib |
| **Ring 2** *(Uncapped Assurance)* | `tests/`, `extra/sz_ajar.py` | `$0` deterministic `pytest` + `extra/sz_ajar.py` + `tools/arch_lint.py` on every commit; paid benchmarks run locally on demand via `ajar bench` |

### Ring 0: Core Kernel

- **`src/ajar/cli.py`**: Shared dataclasses (`Span`, `BuildRecipe`, `CrashSignature`, `Candidate`, `Verdict`, `AblationConfig`, `RunConfig`), crash-safe `flock` JSONL helpers (`append_jsonl`, `read_jsonl`), `scrub_subprocess_env`, and the 4 CLI verbs (`run`, `verify`, `bench`, `report`) plus 7 `--disable-*` ablation flags.
- **`src/ajar/llm.py`**: Pure-stdlib async HTTP client (`StdlibLLMClient`), deterministic `MockLLMClient`, role-tier model routing (`ROLE_MODEL_MAP`: `scout`/`doctor` -> Flash, `auditor`/`weaver` -> Pro, `critic` -> non-GLM cross-family model), and thread-safe reservation `CostMeter` (`92%` drain reserve, `99%` hard ceiling).
- **`src/ajar/agent.py`**: Sandboxed `WorkspaceTools` (`read_file`, `search`, `edit_file`, `exec_cmd` with optional write-allowlist jail), `SpanTracker` 1-indexed interval tracker, `AgentHooks` protocol, and `run_worker_loop` (`65%` soft relay capsule, `70%` hard worker recycle, `92%` context guard).
- **`src/ajar/verify.py`**: Sole `git worktree` owner (`clean_worktree` with `copytree` fallback), 5-stage mechanical `C3` verifier (`verify_candidate`), and voice-linted report exporter (`export_reports`).

### Ring 1: Seven Toggleable Earned-Muscle Modules

1. **`src/ajar/repomap.py`** (`--disable-repomap`): Polyglot symbol/call indexer (C/C++, Rust, Go, Python, JS/TS, Solidity), Personalized PageRank ranking, slice queries, and deterministic `.ajar/REALITY.md` builder. Excludes `tests/`, `docs/`, and `benchmarks/` at minute zero.
2. **`src/ajar/whiteboard.py`** (`--disable-whiteboard`): Lock-free `O_APPEND` journal (`.ajar/events.jsonl`) with `20m` `CLAIM` TTL evaporation and atomic `.ajar/WHITEBOARD.md` projection across 8 sections (`claim`, `bounty`, `insight`, `invariant`, `effect`, `encoder`, `wish`, `dead_end`).
3. **`src/ajar/epistemic.py`** (`--disable-epistemic`, `<= 180` SLOC): Mechanical 4-inflection `EpistemicGuard` (`seen_spans` provenance, unopened-guard sink closure check, Jaccard `>= 0.80` rut detector, and pre-prove gate checking observed `entry_span`, non-placeholder `repro_cmd`, and concrete `failure_oracle`). Zero pre-bash blocking.
4. **`src/ajar/chain_weaver.py`** (`--disable-chain-weaver`): 12-type `EffectType` ontology, 6 `CarrierKind`s, `EFFECT_COMPAT`/`CARRIER_COMPAT` matrices, backward `WISH` abduction, deterministic `join_effects_and_wishes`, and LLM-assisted `weave_candidates`.
5. **`src/ajar/autobuild.py`** (`--disable-autobuild`, `--disable-microfuzz`): Polyglot `.ajar/build.sh` synthesizer across `upstream`, `debian`, and `al2023` ASan/UBSan profiles, write-jailed Build Doctor (`run_build_doctor`), and sandboxed `Input Encoder` micro-fuzzer.
6. **`src/ajar/swarm.py`** (`--disable-swarm`): Live `1..8`-worker async `LiveSwarm` orchestrator across 5 roles (`build_cartographer`, `surface_scout`, `deep_auditor`, `bounty_resolver`, `downstream_prover`), `45m` stagnation pivot, `30m` heartbeat to `.ajar/STATUS.md`, `65%`/`70%` context relay, and `92%` budget drain into `C3` verification.
7. **`src/ajar/bench.py`**: Local on-demand Phase-0 deterministic probes (`P0-A`..`P0-D`) and Leave-One-Out empirical rent scorer (`evaluate_rent_rule` returning `KEEP` or `EVICT`).

---

## 2. CLI Surface & `.ajar/` Workspace State

Ajar exposes exactly **4 CLI verbs** and **7 ablation flags**:

```bash
ajar run <repo> [--workers 8] [--budget-usd 50] [--hours 6] [--profile upstream] [--disable-<module>]
ajar verify <repo> [--candidate-id <id>] [--runs 3] [--profile upstream] [--offline]
ajar bench [suite] [--phase0] [--out bench-out] [--workers 4] [--budget-usd 10] [--disable-<module>]
ajar report <repo> [--out <dir>]
```

Ablation flags: `--disable-repomap`, `--disable-whiteboard`, `--disable-epistemic`, `--disable-chain-weaver`, `--disable-autobuild`, `--disable-swarm`, `--disable-microfuzz`.

All runtime state for a target checkout lives inside `<repo>/.ajar/` (gitignored; never committed):

```text
<repo>/.ajar/
├── REALITY.md         # Deterministic PageRank map, entrypoints, and sink inventory (repomap.py)
├── WHITEBOARD.md      # Atomically projected stigmergic coordination board (whiteboard.py)
├── STATUS.md          # Periodic swarm heartbeat, coverage, budget, and C3 totals (swarm.py)
├── events.jsonl       # Lock-free append-only stigmergic event journal (whiteboard.py)
├── build.sh           # Executable polyglot sanitizer build script (autobuild.py)
├── build_recipe.json  # Serialized BuildRecipe (profile, build_script, test_cmd, env)
├── candidates.jsonl   # Proposed and chained Candidate records awaiting C3 verification
├── verdicts.jsonl     # Append-only mechanical Verdict receipts emitted by verify.py
└── reports/           # Default export output: advisories/ (C3) and hardening-notes/ (C1/C2)
```

---

## 3. Five-Stage Mechanical `C3` Verification (`verify.py`)

`ajar verify` runs every candidate inside an isolated `clean_worktree` with scrubbed environment variables (`scrub_subprocess_env`):

1. **Pre-Patch Attributed Fail (`3x` default):** Rejects tautological repros (`exit 1`, `false`, source-grep cheats), runs `.ajar/build.sh` if present, executes `repro_cmd` `3x`, parses a deterministic `CrashSignature` (or concrete `failure_oracle`), requires `sink_symbol` in output when specified, and rejects flaky `stack_hash` drift across runs.
2. **Fuzzy Patch Apply (`apply_patch_fuzzy`):** Applies `cand.patch_diff` cleanly inside the isolated worktree.
3. **Mandatory Post-Patch Rebuild:** Re-executes `.ajar/build.sh` after patching so stale binaries can never falsify a fix.
4. **Post-Patch Pass (`3x`) + Upstream Regression Suite:** Re-runs `repro_cmd` `3x` requiring exit code `0`, zero crash signatures, and zero `failure_oracle` matches, then executes `recipe.test_cmd` if configured.
5. **Cross-Family Critic:** In online mode, submits the candidate and `CrashSignature` to a distinct model family (`resolve_role_model("critic")`, rejecting `zhipu-glm` self-critique) to mint `truth_level = "C3"`. Offline verification caps at `C2`.

### Report Export & Voice Lint (`export_reports`)

`ajar report <repo> --out <dir>` writes:
- `advisories/`: `VERIFIED` `C3` security advisories, each checked against [`skills/security-advisory-report/scripts/report_voice_lint.py`](../skills/security-advisory-report/scripts/report_voice_lint.py) (`--strict`, requiring `100/100`).
- `hardening-notes/`: Verified `C1`/`C2` or explicit `hardening`/`informational` items.
- Withdrawn (`cand.withdrawn == True`) and `REJECTED`/`WITHDRAWN` candidates are omitted completely per `DEC-0139`.

---

## 4. Mechanical Guardrails & Historical Context

- **Architecture & Anti-Golf Gate:** `python3 extra/sz_ajar.py .` checks module count (`11`), Ring-0 SLOC (`<= 1,800`), `epistemic.py` SLOC (`<= 180`), `Tokens/SLOC <= 10.5`, zero semicolons, zero upward Ring-0 -> Ring-1 imports, sole `git worktree` ownership in `verify.py`, and all 7 `--disable-*` flags.
- **Invariant Linter:** `python3 tools/arch_lint.py` enforces zero third-party LLM SDK imports, zero circular imports (Tarjan SCC), zero hardcoded developer home paths, and safe `tarfile` extraction filters.
- **Campaign Evaluation & Roadmap:** See [campaigns-and-roadmap.md](campaigns-and-roadmap.md) and [decisions/README.md](decisions/README.md).
