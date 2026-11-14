# Linux native startup diagnostics

The third hosted attempt at `9fde78c0`, run
[43594367421](https://github.com/matheusht/redteam-harness/actions/runs/43594367421),
passed both pinned image checks and OMP installation, then failed before native
session readiness. Original Codex and OMP result bytes are retained beside this
file. Codex rejected `environment/info` because its exec-server transport closed.
OMP reported `environment_create_unknown`: cleanup discovered and removed the
exact staging container, but the public artifact omitted the operation outcome.
These observations do not establish either root cause.

This engineering driver change retains the existing controller's exact
safe environment-observation events, including event hashes, timestamps, grants,
status and return codes, before cleanup. Intent/result timestamps and grant expiry
can then distinguish command duration from expiry without changing production
admission or timeout behavior.

For Codex, a fixture-local subprocess proxy captures stderr only when the
command ends with the exact fixed native exec-server argv. The original argv,
stdin, stdout, environment, process result and isolation remain unchanged.
The proxy delegates every other subprocess call. A reader drains stderr to avoid
backpressure, retains at most 8 KiB privately, withholds oversized/incomplete data,
and applies the existing publication filter and known synthetic provider/bridge
secrets before limiting public text to 2,048 characters. No model process,
provider requests, WebSocket bearer frames or raw tool requests are captured.

Before implementation, `diagnostic-e2e.py` checks exact real controller event
readback with simulated environment observations, secret rejection, corrupted
journal refusal, and actual inert process stderr: safe exit failure, sensitive
text, each known secret, oversized output, and unrelated command exclusion.
No Docker, native executable, external provider or target is used locally.

Repeat from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/team-evidence/linux-startup-diagnostics-20261114/diagnostic-e2e.py \
  --source evals/native-qualification/smoke/check_linux_model_native_e2e.py \
  --output /tmp/linux-startup-diagnostics.json
```

Expected: all diagnostic cases pass; command/stdin/stdout/exit status stay exact,
unsafe diagnostics never appear, original events remain unchanged, and the
journal can be reopened. These checks validate observation only. The next hosted
run must identify the actual failures; no production runtime fix is claimed.

The [before](before.json) and [after](after.json) receipts cover nine diagnostic
cases. All nine fail before the helpers exist and pass afterward. The earlier
[request diagnostic regression](request-diagnostic-regression.json) passes all
five cases. [Source pins](manifest.json) identify the checked driver and scenario.
