# Ajar Engineering Guide (`v3.6-Balanced`)

Read this file before modifying `src/ajar/`, `extra/`, `skills/`, `benchmarks/`, `docs/`, or `tests/`.

## Architectural Invariants

1. **Three-Ring Partition & Hard SLOC Caps (`extra/sz_ajar.py`):**
   - `src/ajar/` contains exactly `11` logic modules (`4` Ring 0 + `7` Ring 1) plus `__init__.py`.
   - Ring 0 (`cli.py`, `llm.py`, `agent.py`, `verify.py`) stays strictly `<= 1,800` SLOC with `0` upward imports into Ring 1 (except lazy dispatch inside `cli.py:main`).
   - `epistemic.py` stays strictly `<= 180` SLOC.
   - Anti-golf hygiene applies to every file in `src/ajar/`: `Tokens/SLOC <= 10.5` and `0` semicolons.
2. **Pure Python Stdlib & Zero Third-Party LLM SDKs:** Never import `openai`, `anthropic`, `litellm`, `langchain`, `llama_index`, `google.genai`, or `bedrock` in `src/ajar/`. All HTTP inference runs through `urllib.request` in `src/ajar/llm.py`.
3. **Sole `git worktree` Ownership (`verify.py`):** Only `src/ajar/verify.py` may invoke `git worktree`. All pre-patch/post-patch `C3` verification runs inside `clean_worktree`.
4. **Root `AGENTS.md` Budget (`<= 50` Lines):** Keep root `AGENTS.md` and `CLAUDE.md` byte-identical and `<= 50` lines (`wc -l < AGENTS.md`).
5. **Seven Ablation Flags:** Every Ring-1 capability must remain toggleable from `src/ajar/cli.py` via `--disable-repomap`, `--disable-whiteboard`, `--disable-epistemic`, `--disable-chain-weaver`, `--disable-autobuild`, `--disable-swarm`, and `--disable-microfuzz`.
6. **Secret, Path, & External-Action Hygiene:** Never commit credentials, tokens, PII, target `.ajar/` artifacts, or hardcoded developer home paths. Never submit advisories or contact vendors without explicit founder approval.
7. **Frozen Historical Archives:** Treat `tools/legacy/`, `docs/archive/`, `docs/decisions/0001..0025`, and `engagements/` as read-only historical context (full `v3.4` history lives at git tag `archive/v3.4-legacy`). Never import `tools/legacy/` from `src/ajar/`.

---

## Module Map (`src/ajar/`)

| Module | Ring | Responsibility |
| --- | --- | --- |
| `src/ajar/cli.py` | Ring 0 | Shared dataclasses (`Span`, `BuildRecipe`, `CrashSignature`, `Candidate`, `Verdict`, `AblationConfig`, `RunConfig`), `flock` JSONL I/O, `scrub_subprocess_env`, 4 CLI verbs (`run`, `verify`, `bench`, `report`), and 7 `--disable-*` flags |
| `src/ajar/llm.py` | Ring 0 | Stdlib async HTTP `StdlibLLMClient`, `MockLLMClient`, `ROLE_MODEL_MAP` (enforcing non-GLM cross-family `critic`), and reservation `CostMeter` (`92%` drain / `99%` hard cap) |
| `src/ajar/agent.py` | Ring 0 | Sandboxed `WorkspaceTools` (file read/search/edit, bash `exec_cmd`, write-allowlist jail), `SpanTracker`, `AgentHooks`, and `run_worker_loop` (`65%`/`70%` relay) |
| `src/ajar/verify.py` | Ring 0 | Sole `git worktree` owner (`clean_worktree`), 5-stage `C3` oracle (`verify_candidate`), `parse_crash_signature`, `apply_patch_fuzzy`, and voice-linted `export_reports` |
| `src/ajar/repomap.py` | Ring 1 | Polyglot symbol/call indexer, Personalized PageRank, slice queries, and deterministic `.ajar/REALITY.md` generator |
| `src/ajar/whiteboard.py` | Ring 1 | Lock-free `O_APPEND` `.ajar/events.jsonl` journal (`20m` `CLAIM` TTL evaporation) and atomic `.ajar/WHITEBOARD.md` projector |
| `src/ajar/epistemic.py` | Ring 1 | `<= 180` SLOC `EpistemicGuard` (`seen_spans` provenance, unopened-guard sink check, Jaccard `>= 0.80` rut break, pre-prove validation) |
| `src/ajar/chain_weaver.py` | Ring 1 | 12-type `EffectType` + 6 `CarrierKind` ontology, backward `WISH` abduction, deterministic `join_effects_and_wishes`, and LLM `weave_candidates` |
| `src/ajar/autobuild.py` | Ring 1 | Polyglot `.ajar/build.sh` synthesizer (`upstream`/`debian`/`al2023` ASan/UBSan), write-jailed Build Doctor, and sandboxed `Input Encoder` micro-fuzzer |
| `src/ajar/swarm.py` | Ring 1 | Async `1..8`-worker `LiveSwarm` (`45m` pivot, `30m` `.ajar/STATUS.md` heartbeat, `65%`/`70%` relay, `92%` drain reserve) |
| `src/ajar/bench.py` | Ring 1 | Local `$0` Phase-0 probes (`P0-A`..`P0-D`) and Leave-One-Out `evaluate_rent_rule` (`KEEP` / `EVICT`) |
| `extra/sz_ajar.py` | Ring 2 | Structural, SLOC, anti-golf, ring-isolation, worktree-ownership, and ablation-flag gate |
| `tools/arch_lint.py` | Ring 2 | Mechanical invariant linter (zero LLM SDKs, zero circular imports, zero hardcoded devbox paths, safe `tarfile` filters) |

---

## Rule-to-Enforcer Map

| Rule | Mechanical Enforcer |
| --- | --- |
| 11-module layout, Ring-0 `<= 1,800` SLOC, `epistemic.py <= 180` SLOC, `Tokens/SLOC <= 10.5`, `0` semicolons | `python3 extra/sz_ajar.py .` |
| `0` upward Ring-0 -> Ring-1 imports, sole `git worktree` in `verify.py`, all `7` `--disable-*` flags | `python3 extra/sz_ajar.py .` |
| Zero LLM SDKs in `src/ajar/`, `0` circular imports, no `tools/legacy/` imports, no hardcoded home paths | `python3 tools/arch_lint.py` |
| Strict typing across `src/ajar/`, `extra/sz_ajar.py`, `tools/arch_lint.py`, and `report_voice_lint.py` | `mypy --strict ...` |
| Root `AGENTS.md == CLAUDE.md` and `<= 50` lines | `scripts/verify-repo.sh` |
| Exported `C3` advisory voice & jargon hygiene (`100/100`) | `skills/security-advisory-report/scripts/report_voice_lint.py --strict` |

---

## Required Verification Before Opening a PR

Run the canonical single-command driver (`--fast` during iteration, `--full` before opening a PR):

```bash
scripts/verify-repo.sh --fast    # AGENTS.md parity, ruff, sz_ajar.py, arch_lint.py, mypy --strict, fast pytest
scripts/verify-repo.sh --full    # Full pytest + archived tools/legacy/*-test.py reader checks
```

Equivalent explicit commands:

```bash
test "$(wc -l < AGENTS.md)" -le 50 && cmp -s AGENTS.md CLAUDE.md
ruff check src/ajar extra/sz_ajar.py tests tools/arch_lint.py skills/security-advisory-report/scripts/report_voice_lint.py
python3 extra/sz_ajar.py .
python3 tools/arch_lint.py
mypy --strict src/ajar extra/sz_ajar.py tools/arch_lint.py skills/security-advisory-report/scripts/report_voice_lint.py
pytest -q
ajar bench --phase0
```
