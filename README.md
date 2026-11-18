# Ajar

**Ajar** (built by **Ajar Labs**) is a verification-backed security engine powering `Platform`, `Code`, `Fixes`, `Security reviews`, and `Supply chain`.

Every vulnerability claim must survive independent disconfirmation and pass a deterministic **locus-bound 4-arm causal reproduction** (`ajar claim reproduce`), and every production remediation must pass the **8-arm `Fixes` gate** (`ajar patch verify`). All coordination state lives in an external SQLite WAL database (`~/.ajar/runs/<run_id>/run.db`), keeping target repositories untouched.

## Product Lineup Powered by `ajar`

- **`Platform` (`ajar export-graph`, `ajar steer`):** Deterministic component, trust-boundary, and attack-flow graph (`ajar-platform-graph/1`) with attributable operator `Steers`.
- **`Code` + `Fixes` (`ajar quote`, `ajar run`, `ajar patch verify`):** Continuous PR/diff and full-repository verification with `35%` COGS margin enforcement (`cogs_cap_usd <= 0.35 * quote`) and 8-arm verified patches.
- **`Security reviews` (`ajar finish`, `ajar report`):** Deep researcher-signed engagements backed by Stage-5 `Converge` chain synthesis and reproducible 4-arm artifacts.
- **`Supply chain` *(Coming soon)*:** Reachability-gated dependency and native-extension exploitability verification.

## Operating Modes

1. **Host Mode (zero separate API billing):** Drive Ajar from an interactive coding agent session (Claude Code, Codex CLI, Antigravity, OpenCode, or any MCP client) using the `ajar` CLI or `ajar mcp` STDIO server.
   - `--envelope` (default): Creates an isolated workspace (`~/.ajar/runs/<run_id>/env/`) containing `AGENTS.md`, `.mcp.json`, `.claude/settings.json`, and a clean target checkout (`target/`).
   - `--in-place`: Runs directly against an existing checkout (writing zero files into the target repository) when build paths or container mounts depend on absolute paths.
2. **Standalone Mode (`ajar run`):** Runs a headless multi-worker verification loop with keep-biased `--discover-passes N`, role-tier model routing (`AJAR_MODEL_REASON`, `AJAR_MODEL_HUNT`, `AJAR_MODEL_FALLBACK`), dry-surface token breakers, and an `80% / 20%` explore-vs-verify reserve.

## Quickstart

```bash
python3 -m pip install -e ".[dev]"
ajar doctor
ajar quote /path/to/target
```

### Host Mode Run

```bash
# 1. Initialize an isolated run (defaults COGS cap to 0.35 * Code LOC quote, or pass --cogs-cap)
ajar init /path/to/target --mode source --until exhaustive-high

# 2. Record workspace Steers, map symbols, and register surfaces
ajar steer add --scope global --kind scope_authority --rule "Do not mutate production fixtures"
ajar map --budget-tokens 1500
ajar surface add --name "auth-token-exchange" --kind http --subsystem auth \
  --locus "src/oauth.py:84" --priority critical \
  --trust-boundary "unauthenticated client -> token issuer"

# 3. Enqueue bi-directional tasks, lease, investigate, falsify/rescope, reproduce, and patch
ajar task add --kind investigate --direction inside_out \
  --title "Check atomic single-use on auth_code sink" \
  --surface <surface_id> --locus "src/oauth.py:84" --priority critical
ajar task lease --worker w-explore-1 --kind investigate --recover

# 4. Verify SQL gates G1-G5, export Platform graph, seal run, and emit report
ajar gate check
ajar export-graph --output graph.json
ajar finish
ajar report --format md --output report.md
```

### Standalone Mode Run

```bash
ajar run /path/to/target --mode source --until exhaustive-high --workers 3 --discover-passes 2
```

## Two-Stage Verification: 4-Arm Discovery & 8-Arm `Fixes`

| Stage | Command | Arms Enforced |
| --- | --- | --- |
| **Finding Proof (`reproduced`)** | `ajar claim reproduce` | **Arms 1–4 + Locus Match:** Clean+PoC fires, Clean+Control passes, `1–5` line micro-patch at `claim.locus` blocks PoC, Micro-patch+Control passes |
| **Production Fix (`maintainer_patched`)** | `ajar patch verify` | **Arms 1–8:** Arms 1–4 + **Arm 5** full test suite + **Arm 6** `>= 3` bypass variants blocked + **Arm 7** caller NULL/error-return audit + **Arm 8** sibling-route/peer-hook symmetry audit |

## Core CLI Commands

| Command | Purpose |
| --- | --- |
| `ajar quote <target> [--diff <base..head>]` | Preview deterministic `Code` LOC quote (`$0.05/LoC`, `$25` min) and `35%` COGS cap |
| `ajar init <target>` | Create `~/.ajar/runs/<run_id>/run.db`, mirror/worktree slots, and FTS5 indexes |
| `ajar steer add\|list\|revoke` | Manage attributable workspace `Steers` (`scope_authority` vs `research_steering`) |
| `ajar status` / `ajar pulse` | Inspect run metrics, COGS margin, active leases, bindings, and reopened tasks |
| `ajar map` / `ajar export-graph` | Build Personalized PageRank symbol map and export `Platform` attack-flow JSON graph |
| `ajar ref query --kind intent\|reachability\|precedent <q>` | Search FTS5 indexes over docs/tests, symbol callers, and precedent corpora |
| `ajar surface add\|list` / `ajar driver add\|list` | Register attack surfaces and executable harness drivers |
| `ajar task add\|lease\|done\|dry\|block\|list` | Coordinate bi-directional work items with anti-premature-`dry` guard enforcement |
| `ajar anomaly add\|explain\|list` | Persist unexpected behaviors independently of specific hypotheses |
| `ajar primitive add\|list` / `ajar binding set\|list` | Record composable/guarded capabilities and line-hashed verified code facts |
| `ajar claim propose\|rescope\|falsify\|survive\|reproduce\|list` | Drive hypotheses through disconfirmation, rescoping, and locus-bound 4-arm proof |
| `ajar chain propose\|list` | Run Stage-5 `Converge` guard-breaking and end-to-end chain verification |
| `ajar patch verify\|list` | Enforce the 8-Arm Production Remediation Gate (`maintainer_patched`) |
| `ajar gate check` / `ajar finish` / `ajar report` | Enforce SQL gates `G1–G5`, seal artifacts, and render Markdown/JSON reports |
| `ajar mcp` / `ajar hook claude-stop` / `ajar loop codex\|omp` | Host Mode MCP server and session-persistence adapters |

## Repository Layout

```text
AGENTS.md                 <= 50-line ASD-STE100 agent instructions (mirrored in CLAUDE.md)
ajar/                     Zero-LLM Python engine (SQLite WAL, gates, 4/8-arm repro, graph, quote, MCP)
skills/
  ajar-*/                 7 core workflow skills (map, investigate, falsify, reproduce, chain, patch, report)
  domains/                5 contrastive domain packs (evm-solidity, consensus-vm, rust-systems, web-api, auth-crypto)
  references/             8 curated CVE, exploit-chain, contest-ruling, fix-diff, and false-positive corpora
benchmarks/               Foundry, hermetic web/API, and polyglot C/Go/Rust/Python verification targets
docs/
  architecture.md         v3.1 engine, schema, 4/8-arm gates, COGS economics, and closeout specification
  decisions/              Architecture Decision Records (0017 and 0018 active; 0001-0013 superseded)
  engineering/AGENTS.md   Contributor invariants and required pre-PR verification commands
tests/                    Unit, gate, v3.1 bug-brain, redaction, trap, and conformance test suite
tools/legacy/             Read-only historical readers for archived engagements/
```

## Authorization and Redaction

1. Run `--mode live` only against targets explicitly authorized in `scope_rules` (`--allow-live-requests` and `--allow-host`).
2. Never store credentials, tokens, session cookies, private keys, or signed URLs in any database row, artifact, or commit.
3. Obtain explicit operator approval before external disclosure, vendor contact, or publication.
