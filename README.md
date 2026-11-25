# Ajar v3.6-Balanced

**Ajar** (built by **Ajar Labs**) is a Three-Ring Earned-Mass autonomous security auditing and `C3` verification engine (`L4 · C3 · B3`).

Legacy `v3.4` orchestration scaffolding (`~45k` LoC) is preserved in git history at tag `archive/v3.4-legacy`. `v3.6-Balanced` keeps bureaucratic middleware deleted while restoring the 7 load-bearing muscles inside a strict **Three-Ring** stdlib layout policed by [`extra/sz_ajar.py`](extra/sz_ajar.py).

## Three-Ring Layout (`11` Zero-Overlap Logic Modules in `src/ajar/`)

| Ring | Modules | Governance Rule (`extra/sz_ajar.py`) |
| --- | --- | --- |
| **Ring 0** *(Core Kernel)* | `cli.py`, `llm.py`, `agent.py`, `verify.py` | **`<= 1,800` SLOC hard cap**, `0` upward imports into Ring 1, `verify.py` is sole owner of `git worktree` and 5-stage `C3` minting |
| **Ring 1** *(7 Earned Muscles)* | `repomap.py`, `whiteboard.py`, `epistemic.py`, `chain_weaver.py`, `autobuild.py`, `swarm.py`, `bench.py` | Every muscle wires `--disable-<module>` (`7` flags), `epistemic.py <= 180` SLOC, anti-golf `Tokens/SLOC <= 10.5`, `0` semicolons |
| **Ring 2** *(Uncapped Perimeter)* | `tests/`, `extra/sz_ajar.py` | `$0` deterministic `pytest` + `sz_ajar.py` on commit; paid `ajar bench` runs strictly locally on demand |

## Quickstart

```bash
python3 -m pip install -e ".[dev]"
python3 extra/sz_ajar.py .
ajar bench --phase0
ajar run /path/to/target --workers 8 --budget-usd 50 --profile upstream
ajar verify /path/to/target --runs 3
ajar report /path/to/target --out ./reports
```

## Engineering Verification

```bash
scripts/verify-repo.sh --fast    # AGENTS.md <= 50 lines + CLAUDE.md parity, ruff, sz_ajar.py, arch_lint.py, mypy --strict, pytest
scripts/verify-repo.sh --full    # Adds archived historical reader checks under tools/legacy/
```

## Boundaries

1. Never run active exploitation or live network requests outside explicitly authorized scopes.
2. Never commit credentials, API keys, PII, or target `.ajar/` artifacts.
3. Obtain explicit founder authorization before any external disclosure or advisory submission.
