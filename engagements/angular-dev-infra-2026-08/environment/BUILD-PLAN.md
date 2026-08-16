# BUILD-PLAN.md — research environment for angular/dev-infra

> Nothing here has been executed. Host not chosen (`progress.md` B1).

## 0. Host — resolved 2026-08-12

**Running on the macOS arm64 workstation. Approved; reasoning recorded in `progress.md` §2a.**

| | Measured |
|---|---|
| Host | macOS arm64 (Darwin 25.5.0), 10 cores, 16 GB RAM |
| Free disk | **46 GiB** (requirement was ≥ 30 GB) |
| Docker | 29.3.1, `linux/aarch64` — **native arm64 Linux containers, no emulation** |
| node / pnpm | v25.9.0 / 10.33.0 |
| bazelisk / act | 1.29.0 / 0.2.89 |

**The amd64 divergence and its bound.** GitHub's real runners are `ubuntu-latest` = linux/amd64.
Architecture is irrelevant for pure Node and TypeScript actions, which is nearly all of the surface.
If a lane hits an action that shells out to a prebuilt amd64 binary, run that one under
`act --container-architecture linux/amd64` (emulated, slower) and **record that you did**.

**Do not mistake the OS for faithfulness.** An `act` run on Linux proves no more about the real
trigger filter, `if:` conditions, `permissions:` block, or GitHub-side event validation than an `act`
run on macOS. §5 carries the evidence, not the operating system.

## 1. Clone and pin

```sh
git clone https://github.com/angular/dev-infra.git upstream/dev-infra
cd upstream/dev-infra && git checkout <PINNED_SHA>   # progress.md §3
git rev-parse HEAD    # record this
```

Also clone the three consuming repos **read-only, for interface reading only**:
`angular/angular`, `angular/angular-cli`, `angular/components`. Hunting inside them is out of scope
(`scope.md`).

**The hunt does not read the history.** No `git log`, no changelog, no release notes, no issue
tracker, no advisory search, no web search for known dev-infra issues **during the hunt**. That route
rediscovers an n-day and presents it as a find, and it short-circuits the mechanism understanding the
later stages depend on. Novelty checking is a deliberate late act (Part 3 of the goal prompt).
Carve-outs where the internet IS allowed: GitHub Actions documentation, `@actions/*` toolkit source
read from `third_party/`, Node and TypeScript semantics, Bazel documentation.

## 2. Toolchain

```sh
corepack enable && corepack prepare pnpm@latest --activate   # repo uses pnpm-lock.yaml
pnpm install --frozen-lockfile
npm i -g @bazel/bazelisk        # or brew install bazelisk
```

`act` for local workflow replication, plus Docker with the `ubuntu-latest` runner image.

`zizmor` is optional and **Stage-1 only**. The repo already carries a zizmor suppression, so their
team runs it. Anything zizmor alone finds is almost certainly already known. Use it to narrow, never
to decide, and never as a source of findings.

## 3. The local proving rig — build this before Round 0

Three components. All local. No real credential ever enters any of them.

**3.1 Mock GitHub API that records calls.** A local HTTP server speaking enough of the GitHub REST
and GraphQL surface for an action to run against, which **logs every call with method, path, body and
auth header shape**. The safe signal `bot_performs_unintended_privileged_action` is "a call appears in
this log that is outside the action's intended vocabulary."

**3.2 Synthetic canary secrets.** Distinctive random strings with no real value, placed exactly where
the real workflow places the real secret. The signal `secret_reaches_attacker_controlled_sink` is
"this exact string appears in a sink an attacker controls." Give every canary an id and track it in
`cleanup.md`.

**3.3 Direct action drivers.** Most of these actions are TypeScript or JavaScript with an entry
point. Driving that entry point directly, with a controlled event payload and the mock API, is faster
and more faithful than a full `act` run — and it is the level at which output handling can actually
be inspected. Build a driver per action under audit.

## 4. Oracle calibration — before Round 0, not after

`oracle-validity-per-namespace`: an oracle calibrated once proves it works only where you calibrated
it. Each signal needs a matched positive and negative control, and the raw output goes in
`evidence/oracle-calibration/`.

| Signal | Positive control | Negative control |
|---|---|---|
| `secret_reaches_attacker_controlled_sink` | plant a canary and deliberately echo it to the sink — the detector must fire | a benign run — the detector must stay silent. A detector that fires on both is useless |
| `unreviewed_code_lands` | feed the gate the change it is designed to reject — it must reject | feed it a benign change — it must accept. Prove the gate works before claiming it does not |
| `injected_step_executes` | a marker command that provably runs | the identical harness with benign input, no marker |
| `bot_performs_unintended_privileged_action` | a call deliberately outside the vocabulary | a normal run producing only in-vocabulary calls |
| `integrity_check_silent_accept` | a deliberately mismatched artifact — must hard-fail | the matching artifact — must pass |

**Re-run the negative control in every namespace.** Calibrating on `labeling/issue` proves nothing
about `post-approval-changes`.

## 5. Faithfulness — the reward-hack that will happen here if it is not guarded

The failure mode is specific and it is not hypothetical:

> An agent builds a local driver for an action, feeds it a crafted payload, observes the marker fire,
> and reports `confirmed` — while the **real GitHub Actions control flow would never have reached
> that code with that input**, because a trigger filter, an `if:` condition, a permissions block, a
> GitHub-side event-shape constraint, or an earlier job step would have stopped it.

A local driver is a tool for **finding** the path. It is not proof the path is real. Before any
`confirmed`, a fresh-context pass must answer, in writing:

1. Which real trigger delivers this event, and does the workflow's `on:` filter accept it?
2. Does every `if:` between the trigger and the sink evaluate true with attacker-controllable values?
3. Does the job's `permissions:` block actually grant what the impact claims?
4. Is the input field attacker-controlled **on GitHub**, or only in our synthetic payload?
5. Would GitHub itself reject this event shape?

If any answer is "not checked", the verdict is not `confirmed`. **Confirm from raw output, never from
a wrapper's summary** — the local `rtk` hook has been observed reporting wrong test outcomes, wrong
diff equality and wrong grep counts.

## 6. Cleanup

Delete the clones, `node_modules`, the pnpm store, the Bazel output base, and `act` runner images at
closure. Delete any private throwaway fork and revoke every canary. Record reclaimed space and canary
disposal in `cleanup.md`.
