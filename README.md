# Ajar v3.5

**Ajar** (built by **Ajar Labs**) is a first-principles autonomous security auditing and verification engine.

Following the v3.5 cutover ("Deeper, Not Bigger"), the core engine deletes >95% of legacy orchestration scaffolding (`31,645` LoC -> `< 1,500` LoC across 9 pure-stdlib modules in `src/ajar/`, permanent `<= 1,800` LoC ceiling). Legacy v3.4 code is preserved verbatim in git history under tag `archive/v3.4-legacy`.

## Architecture (`src/ajar/` — 9 Pure-Stdlib Modules)

| Module | Responsibility |
| --- | --- |
| `src/ajar/__init__.py` | Package version (`3.5.0`) and `MAX_PYTHON_LOC = 1800` |
| `src/ajar/schemas.py` | Flat `.ajar/` JSONL primitives (`0` SQLite tables) and `4x3` Diagonal Kill Matrix evaluator |
| `src/ajar/worktree.py` | Disposable clean-room git worktrees, 1-hop delegate mounts (`D1`), 3-profile build matrix (`D2`), fail-closed network isolation (`D6`) |
| `src/ajar/reality.py` | Living Adaptive Threat Model (`.ajar/REALITY.md`, works with or without `SECURITY.md`), 5 Cross-Seam Lenses, comment-stripped guard check (`D6`) |
| `src/ajar/microfuzz.py` | In-slot boundary + stateful micro-fuzzer with mandatory clean-worktree public entrypoint replay |
| `src/ajar/verify.py` | Clean-room judge (`ajar prove` & `ajar critique`): Red/Green patch replay, Wrong-Bug Trace Guard, `D5` deterministic/statistical race gates, Cross-Family Critic |
| `src/ajar/chain_cmd.py` | Stigmergic `CAN <-> [Normal Feature Bridge] <-> WISH` chain matcher and clean-worktree E2E prover |
| `src/ajar/campaign.py` | Up to 8-worker stigmergic campaign sentinel (`D3` 45m physical-signal pivot, `D4` 65%/70% compaction relay, `< 35%` COGS cap) |
| `src/ajar/cli.py` | 8-verb CLI (`reality`, `microfuzz`, `prove`, `chain`, `critique`, `campaign`, `bench`, `report`) + 100/100 engineering voice linter |

## Quickstart

```bash
python3 -m pip install -e ".[dev]"
ajar reality /path/to/target --profiles upstream,debian
ajar microfuzz /path/to/target --entrypoint "python3 cli.py {input}" --mode both
ajar prove /path/to/target --finding-json finding.json --test-cmd "pytest -q"
ajar critique /path/to/target --finding-json finding.json
ajar chain /path/to/target
ajar campaign /path/to/target --workers 8 --budget-usd 100
ajar report /path/to/target --out ./reports
ajar bench --check-loc   # Local on-demand yardstick only (0 CI gates)
```

## Engineering Verification

```bash
scripts/verify-repo.sh --fast    # AGENTS.md <= 50 lines + CLAUDE.md parity, ruff, arch_lint, mypy --strict, pytest
scripts/verify-repo.sh --full    # Adds archived historical reader checks under tools/legacy/
```

## Boundaries

1. Never run active exploitation or network requests outside explicitly authorized scopes.
2. Never commit credentials, API keys, PII, or target `.ajar/` artifacts.
3. Obtain explicit operator authorization before external advisory submission or publication.
