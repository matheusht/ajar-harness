# Researcher-requested source action: failure-first check

This is the public native `continue` scenario for issue #203. It needs a **contained,
signed source-only fixture**, a running native owner, a current plan-bound approval,
an offline executor image, and an agent/provider route authorized for that fixture.
Keep the fixture and saved evidence outside this repository. This document does not
authorize a target or provider call. The deterministic local check below is synthetic
component evidence; a live native provider/target run remains a separate gate.

## Failure inventory written before implementation

| Failure | Required public behavior |
| --- | --- |
| Missing, duplicate-key, malformed, oversized, symlinked or stale `NEXT.json`; invalid or credential-like argv | Reject before freezing or dispatch. No source executor directory. |
| Request swaps after validation, or frozen command/source changes | Reject; an old grant or receipt cannot cover new bytes. |
| Agent `authority` prose or matching scope digest without source-only envelope | No host effect. Stop for an authority decision, counted separately from research help. |
| Non-source plan, changed/expired approval, stopped run, exhausted shared allowance | No dispatch. Preserve the next brief and record the reason. |
| Concurrent continuation/controller or source executor | One lease and turn lock; never two host batches for one request. |
| Crash before dispatch | Keep prepared ID and frozen hashes; resume only after checking the same request and inputs. |
| Crash after dispatch, before/after source receipt capture | Adopt only an exact captured receipt once. Missing/corrupt/unknown result stops for readback; never silently execute again. |
| A captured receipt appears after an earlier `unknown_effect` stop | Read back and adopt that exact receipt without calling the executor again; resume only if the same run is still active. |
| Crash after the frozen request is written but before `state.json` names it | Recover the one complete, matching pre-dispatch request after proving no source execution directory exists. |
| Crash during the freeze, leaving an incomplete action directory | Prove no execution directory or dispatch event, quarantine the pre-dispatch bytes and safely prepare a new ID. Otherwise stop as unknown. |
| Second action crashes before prepared state is saved | Distinguish earlier verified captured action directories, then recover the one complete new request or quarantine its incomplete freeze. Never assign a third ID for a complete orphan. |
| Captured state is saved but its journal event is interrupted | Verify the terminal, receipt and projection, then restore the missing event once before a later action replaces the state. A third action must not treat the first captured action as an orphan. |
| Duplicate request after capture, or changed request with the old ID | Do not dispatch twice. New request needs a new host action after the previous one is read. |
| Source execution repeats stdout | Report reproducibility only. Attacker reachability, protected effect, initial state, permission and causal control remain unproven. |
| Invalid captured receipt is later replaced with valid bytes | Pin the first observed bad receipt hash and reason; hold until explicit reconciliation. Do not auto-adopt replacement or run another effect. |
| Receipt/projection changed after capture | Reject adoption and further effects. |

## Public E2E scenario

1. Prepare and start a private, signed fixture through `python3 tools/native_research.py
   prepare` and `start` as described in `docs/agents/native-source-sdk.md`. Save the
   exact scope, plan, approval, image IDs, command, source manifest, model route,
   allowance and cleanup authority. The fixture's script should emit a benign
   distinguishable value and have a control that does not emit it.
2. The native researcher writes `researcher/NEXT.json` with one
   `host_action: {"kind":"native-source-execute-v1","command":[...]}` and no
   `next` or stop proposal. It chooses the script and writes the script inside
   `researcher/project`. The researcher cannot write host controls.
3. Run `python3 tools/native_research.py continue --run-root "$RUN_ROOT"
   --max-invocations 3`. Interrupt once after `prepared`, and in a second copy
   after `dispatched`. Resume with the same command. Save the CLI JSON, the
   continuation journal, immutable action request and terminal receipt, frozen
   input manifest, source executor receipt, and `/research/source-actions/<id>/RESULTS.json`.
4. Assert one action ID, one source execution ID, exactly three clean executor
   runs (initial plus two replays), matching frozen command and source hashes,
   one terminal receipt and no second execution on repeat `continue`. Assert
   the same native run reads the projection and changes its next hypothesis.
   Force each failure in the inventory above on disposable copies and assert
   no extra source execution. For an uncertain dispatch, require explicit
   readback or separately authorized reset.
5. Stop through `python3 tools/native_research.py stop --run-root "$RUN_ROOT"`.
   Save status and cleanup receipt, resource absence, command outputs and hashes,
   provider cost if measured, human authority/research assistance, and all
   unresolved effects. A repeatable result requires exact fixture inputs,
   environment requirements, expected/observed status and these saved outputs.

Passing this scenario demonstrates one contained host action and native readback.
Matching output does **not** establish a security effect. That needs independent
observation of the original entry path, starting state, attacker permissions,
protected state and a causal control, followed by fresh review.

## Local repeatable component check

With Docker 29.3.1 and the pulled Linux arm64 BusyBox image
`sha256:a7dbc319b1438115a207e11930dc4bb3e643dcb3ec0bdd694bb36cd8fad289ec`:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_native_source_action.py \
  --docker sha256:a7dbc319b1438115a207e11930dc4bb3e643dcb3ec0bdd694bb36cd8fad289ec
```

The check creates disposable private source copies, a synthetic approved plan
and fake native turns. It runs the actual Docker `source_execute` for one
request; its expected result is one batch, three executor runs, a captured
receipt, readback in the simulated next turn, and absent fixture containers
after cleanup. It also checks malformed and changed requests, missing class,
expired approval, exhausted allowance, a competing controller and crash
windows. [Saved local result](SOURCE-ACTION-LOCAL-CHECKS.json) records exact
source/check hashes, image ID, observed statuses and receipt hashes. Its
`native_tool_trace` and `provider_cost` are null: real native readback,
signed-target behavior and provider spend remain unverified.

The affected source-mode and continuation checks also passed locally:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_native_source_mode.py
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_native_continuation.py
```

These report four source-mode checks and six continuation checks. Both use
synthetic execution, so they do not qualify a native model, provider or target.
