# engine/hunter-envelope.md — hunter execution envelope

> Complements `engine/roster.md` (who drives) and `engine/loop.md` (when). This is the **runtime
> envelope** for a hunter: what it may see, where it runs, and what it may return. It does **not**
> replace Plane 2. Orchestrator, oracle, Zone-2, and record authority stay where they are.

## Branch delta (`feat/engineering-phase0`)

`https://github.com/matheusht/redteam-harness/tree/feat/engineering-phase0` was **not reachable**
(GitHub 404 / private) at implementation time. This contract is grounded in local `origin/main`
(Decision 0004–0006). Re-diff if that branch later shows a graph runner or sandbox; do not assume
it already shipped either.

## Why this exists

Role isolation (orchestrator never drives; hunter returns `attempt`) is policy. Live hunters have
historically been Cursor/Claude Code subagents on the **same checkout** as the orchestrator: they
could `Read` `evals/` gold, engagement findings, and sibling transcripts unless the brief forbade
it. Eval/GEPA worktrees isolate *candidates*, not hunters. Target Docker isolates the *target*,
not the *agent*.

A more assertive hunter on that path leaks more. The envelope inverts it: the hunter may be given
tools and time **inside** a withheld-path, OS-isolated environment; gold, findings, and the
orchestrator's graph stay **outside**.

## Isolation unit

One envelope = one of:

- `hypothesis` — requires `hypothesis_ref` (Decision 0005 search node)
- `card_rung` — CTF/calibration: one card (and optional ladder rung) without a hypothesis ledger yet

Not a graph scheduler. Spawning one envelope per open hypothesis is a later loop change; this
file only defines the envelope.

## Context contract (mechanical)

The hunter's staged tree contains **only**:

- listed Plane-1 card files (`allowed_paths`)
- the bounded `brief` (no gold, no flags, no sibling transcripts)
- `target-handle.json` (url / local_path / none — never credentials, never flags)
- an empty `artifact_out` directory

Default **withheld** prefixes (must appear in `withheld_paths`; may not appear in `allowed_paths`):

```
evals/  fixtures/  casebooks/  engagements/
```

Fail closed: `hunter_gold_path_allowed` if an allowlisted path sits under a withheld tree.
A hunter that can `cat` gold **fails** envelope qualification (`tools/run-hunter-envelope.py
--self-test`).

`local` provider is the context allowlist + scrubbed-cwd jail. It does **not** block absolute
host paths. OS isolation is `docker` or `harbor`.

## Environment contract (provider)

Public provider interface — nothing else:

```
start_env(spec) -> handle
run_hunter(handle, argv) -> {returncode, stdout, stderr}
collect_artifacts(handle) -> [{name, relative_path, sha256, ...}]
teardown(handle)
```

| Provider | What it is | Residual |
| --- | --- | --- |
| `local` | staged tempdir, scrubbed env, cwd = envelope | absolute host reads still possible |
| `docker` | same staged tree bind-mounted; `--network none` when `network_policy=no-network` | requires Docker |
| `harbor` | renders a Harbor **task** (`instruction.md`, `task.toml`, `environment/Dockerfile`, `tests/test.sh`) with **separate verifier**. Live `harbor run` is not the orchestrator | requires Harbor CLI for a live run; this spike renders the task |

Harbor/Docker are **environment providers**, not Plane 2. The two-layer oracle, gates, and
`python3 tools/run-engagement.py` stay outside the container. Harbor `instruction.md` is the
brief only — never gold (that would re-contaminate the agent).

A sandbox is **not** Zone-2 authorization. `zone2_authorized` is `false` on the spec; capability
`executor` remains unbuilt.

## Record

Schema: `schemas/hunter-run.schema.json`. Validated through `validate_record(..., "hunter-run")`.
This is an envelope spec, not a claim record. Attempts still go to the engagement ledger; the
hunter may propose `suspected_success` only.

## Qualification

```
python3 tools/run-hunter-envelope.py --self-test
```

Must fail if gold is readable inside a correctly configured envelope. Must reject a spec that
allowlists `evals/`. Docker, when present, must also fail a host-absolute gold `cat`. Harbor CLI
absence is an honest skip, not a silent pass of a live Harbor run.
