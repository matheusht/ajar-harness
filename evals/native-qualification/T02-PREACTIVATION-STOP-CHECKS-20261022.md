# Pre-activation operator stop: failure checks before code

Decision: use the existing `native_run.request_stop` marker once the launch has
durably created `controls/resources.json`. `NativeRun.prepare` already rejects a
pre-existing `STOP_REQUEST`; a new stop protocol would duplicate that control.
The simpler alternative, waiting for `RUN.json`, loses an operator stop while
the launcher creates its network and containers. The falsifier is a stop call
in that interval that returns without a marker and is followed by producer
startup.

| Failure | Provider-free check |
| --- | --- |
| Merely prepared run is stopped before any launch | Public `stop` returns `not_active` and creates no native state; a later approved start is not poisoned. |
| Operator stops after the launch resource ledger exists but before `RUN.json` | Public `stop` writes `STOP_REQUEST` and reports `stop_requested`; `NativeRun.prepare` rejects before it can start any producer. |
| Operator repeats the stop | The request stays idempotent, with the original marker bytes unchanged. |
| The owner closes before NativeRun starts | It calls exact-resource cleanup with `require_created=True`, so a producer found exited or paused cannot be removed under a false preactivation claim. |
| Owner is lost before native preparation after the stop | The existing `recover-start` `not_started` path keeps its created-stopped requirement and exact-resource cleanup; the stop marker does not claim a successful native freeze. |
| Stop races after `RUN.json` | The existing request path still closes dispatch through `STOP_REQUEST`. |

Run `PYTHONDONTWRITEBYTECODE=1 python3
evals/native-qualification/smoke/check_native_research_preactivation_stop.py`
from the repository root. It uses a private disposable run and the public stop
CLI, then checks the archived NativeRun pre-prepare guard. It makes no Docker,
provider, or application calls. It does not qualify a live stop-owner cleanup;
that still needs the native runtime acceptance path.
