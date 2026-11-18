# Ajar

Ajar is a verification-backed security engine for `Code`, `Fixes`, `Security reviews`, and `Supply chain`.

Every vulnerability claim must survive independent falsification and pass a deterministic **4-arm causal reproduction** (`ajar claim reproduce`) before Ajar reports it as a finding. All coordination state lives in an external SQLite WAL database (`~/.ajar/runs/<run_id>/run.db`), keeping target repositories clean.

## Operating Modes

1. **Host Mode (zero separate API billing):** Drive Ajar from an interactive coding agent session (Claude Code, Codex CLI, OpenCode, or any MCP-compatible client) using the `ajar` CLI or `ajar mcp` STDIO server.
   - `--envelope` (default): Creates an isolated directory (`~/.ajar/runs/<run_id>/workspace/`) containing `AGENTS.md`, `.mcp.json`, `.claude/settings.json`, and a read-only target snapshot (`target/`) so target-repo prompts cannot override verification rules.
   - `--in-place`: Runs directly inside an existing checkout (writing zero files into the target repository) when container mounts, Bazel caches, or build paths depend on absolute paths.
2. **Standalone Mode (`ajar run`):** Runs a headless multi-worker verification loop with an `80% / 20%` explore-vs-verify budget reserve and mandatory first-principles (`zero_skill`) worker quota.

## Quickstart

```bash
python3 -m pip install -e ".[dev]"
ajar doctor
```

### Host Mode Run

```bash
# 1. Initialize an isolated run against a local repository
ajar init /path/to/target --mode source --until exhaustive-high --budget 40

# 2. Map high-centrality symbols and register attack surfaces
ajar map --budget-tokens 1500
ajar surface add --name "auth-token-exchange" --kind http --subsystem auth \
  --locus "src/oauth.py:84" --priority critical \
  --trust-boundary "unauthenticated client -> token issuer"

# 3. Enqueue, lease, investigate, falsify, and reproduce
ajar task add --kind investigate --title "Check atomic single-use on auth_code" \
  --surface <surface_id> --locus "src/oauth.py:84" --priority critical
ajar task lease --worker w-explore-1 --kind investigate --recover

# 4. Check deterministic SQL gates G1-G5, seal the run, and emit markdown report
ajar gate check
ajar finish
ajar report --format markdown --output report.md
```

### Standalone Mode Run

```bash
ajar run /path/to/target --mode source --until exhaustive-high --budget 40 --workers 3
```

## 4-Arm Causal Reproduction

Ajar confirms a finding only when all four arms succeed:

| Arm | Target State | Input | Expected Result |
| --- | --- | --- | --- |
| **Arm 1** | Unmodified target | Exploit PoC | Triggers target security assertion, sanitizer crash, or cross-principal canary leak |
| **Arm 2** | Unmodified target | Benign control | Passes normal operation without firing the exploit assertion |
| **Arm 3** | Minimal root-cause fix (`1–5` lines or runtime guard) | Exploit PoC | Stops the exploit assertion from firing |
| **Arm 4** | Minimal root-cause fix (`1–5` lines or runtime guard) | Benign control | Passes normal operation without regression |

## Core CLI Commands

| Command | Purpose |
| --- | --- |
| `ajar init <target>` | Create `~/.ajar/runs/<run_id>/run.db`, mirror/worktree slots, and FTS5 indexes |
| `ajar status` / `ajar pulse` | Inspect run metrics, spend, active leases, stale bindings, and unchained primitives |
| `ajar map` | Rank repository symbols with Personalized PageRank within a token budget |
| `ajar ref query --kind intent\|reachability\|precedent <q>` | Search FTS5 indexes over docs/tests, symbol callers, and precedent corpora |
| `ajar surface add\|list` / `ajar driver add\|list` | Register attack surfaces and executable harness drivers |
| `ajar task add\|lease\|done\|dry\|block\|list` | Manage prioritized work items with TTL leases and `zero_skill` quotas |
| `ajar anomaly add\|explain\|list` | Persist unexpected behaviors independently of specific hypotheses |
| `ajar primitive add\|list` / `ajar binding set\|list` | Record composable capabilities and line-hashed verified code facts |
| `ajar claim propose\|falsify\|survive\|reproduce\|list` | Drive claims through falsification and 4-arm reproduction |
| `ajar chain propose\|list` | Verify multi-stage exploit chains end-to-end |
| `ajar gate check` / `ajar finish` / `ajar report` | Enforce SQL gates `G1–G5`, seal `CLOSEOUT_RECEIPT`, and render reports |
| `ajar mcp` / `ajar hook claude-stop` / `ajar loop codex\|omp` | Host Mode MCP server and session-persistence adapters |

## Repository Layout

```text
AGENTS.md                 <= 50-line ASD-STE100 agent instructions
ajar/                     Zero-LLM Python engine (SQLite WAL, gates, 4-arm repro, PageRank, FTS5, MCP)
skills/
  ajar-*/                 7 core workflow skills (map, investigate, falsify, reproduce, chain, patch, report)
  domains/                5 contrastive domain packs (evm-solidity, consensus-vm, rust-systems, web-api, auth-crypto)
  references/             8 curated CVE, exploit-chain, contest-ruling, fix-diff, and false-positive corpora
benchmarks/
  foundry/                3 offline Solidity vulnerable + patched-control twin benchmarks
  hermetic/               8 deterministic web/API target specifications
  polyglot/               4 executable C, Go, Rust, and Python live/binary/source QA targets
docs/
  architecture.md         Dual-mode engine, schema, state machines, and closeout gate specification
  decisions/              Architecture Decision Records (0017 active; 0001-0013 superseded)
  engineering/AGENTS.md   Contributor and CI verification guide
tests/                    Unit, gate, redaction, trap, and conformance test suite
tools/legacy/             Read-only historical readers for archived engagements/
```

## Authorization and Redaction

1. Run `--mode live` only against targets explicitly authorized in `scope_rules` (`--allow-live-requests` and `--allow-host`).
2. Never store credentials, tokens, session cookies, private keys, or signed URLs in any database row, artifact, or commit.
3. Obtain explicit operator approval before external disclosure, vendor contact, or publication.
