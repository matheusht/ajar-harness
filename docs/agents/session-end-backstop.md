# Session-end backstop

The Stop hook is a last check on the computed work queue. It does not run work, change queue or
coverage truth, infer an engagement, or replace the local close/render precondition.

## Activation boundary

The hook is inert unless `HARNESS_ACTIVE_ENGAGEMENT` names one explicit absolute target-local path
with the shape `/absolute/target/repo/engagements/<id>`. It never scans the harness checkout,
mounts target workspaces centrally, or selects between multiple engagements. Paths inside this
portable harness checkout are rejected.

Only Claude Code's top-level `Stop` event is registered. There is deliberately no `SubagentStop`
registration. A subagent-shaped payload is also released if it is ever misrouted to the executable.

## Harness-local settings

The tracked `.claude/settings.json` is for a Claude session whose project directory is this harness
checkout. Its command resolves through `${CLAUDE_PROJECT_DIR}` and has a ten-second timeout. A
timeout, missing executable, malformed input, reducer failure, or any unexpected exception releases
the turn; the executable never exits with status 2.

## Target-repository launch

A session launched with a target repository as its cwd does not discover this harness checkout's
project settings. The launcher must pass explicit additional settings while preserving the target's
own settings. Generate the additional JSON with the exact Python interpreter that should execute
the hook:

```sh
/absolute/harness/.venv/bin/python \
  /absolute/harness/tools/claude-stop-hook.py \
  --print-additional-settings
```

Pass that JSON (or a file containing it) through Claude's `--settings <file-or-json>` launch option.
The generated command contains absolute interpreter and hook paths, so it still resolves when cwd
is the target repository. Do not copy or merge the harness settings file into the target repository.

The scoped-session driver additionally exports the exact pre-session record head as opaque values:

- `HARNESS_EXPECTED_LEDGER_HASH` is the reduced `ledger_hash`.
- `HARNESS_EXPECTED_SOURCE_HASHES` is a JSON object containing exactly the reduced
  `events.jsonl`, `attempts.jsonl`, and `artifacts.jsonl` source hashes.

Both variables are required together. A driver-scoped hook does not write the target: it sends a
separate `session_end_check` request to the parent broker containing only the authenticated runtime
UUID, the one-way hash of the hook session id, `stop_hook_active`, and a one-way digest of the exact
hook delivery. The broker authenticates the Unix peer's exact OS session, retains the engagement
inode, and rechecks the source head, scope bytes, canonical queue gate, and any schema-valid
`session.end_checked` tail for that same hook hash under the record-kernel lock. Exact delivery
retries return the cached response without another append. A runtime gets at most the documented
six blocking appends plus one release, and consumption permits only one release for the stale
session. This audit RPC never consumes, rearms, or substitutes the one selected work action. A
replaced endpoint can cause only a release/denial, never a target mutation. Sessions not launched by
that driver omit the endpoint and retain the generic behavior described below.

## Recorded behavior

When active blocking work remains, reduction, streak derivation, the typed
`session.end_checked` append, and the post-append invariant check share one existing target-local
record-kernel lock. In driver mode the trusted parent performs that transaction; outside driver mode
the hook performs the same generic transaction directly. The event contains only opaque session/turn
references, counts, and state/queue digests. Raw stdin, transcript paths, and assistant messages are
neither retained nor logged.

The first six consecutive blocking responses use the exact documented top-level shape
`{"decision":"block","reason":"..."}`. The seventh releases, records
`block_budget_exhausted`, and returns the remainder through the universal, user-visible
`systemMessage` field. It never uses Stop `additionalContext` for a release because that field
continues the conversation and spends another continuation. The message directs the operator to
the canonical `next` command. Every non-hook-forced delivery starts a new streak;
`stop_hook_active: true` without a matching opaque session record releases. Once the selected driver
action has been consumed, a blocking queue produces one audit-only release at the outer-driver
boundary instead of continuing inside the stale session; the outer driver then reduces and selects
again.

Clean releases (inactive, parked, terminal/empty, and operator-only queues) do not append session
events. This keeps the backstop from becoming queue machinery or review-freshness noise.
