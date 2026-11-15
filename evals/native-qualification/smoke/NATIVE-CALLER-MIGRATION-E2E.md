# Native caller migration check

## Purpose

Keep the public `tools/native_engagement.py` route choice explicit while making v2 the
default. A v2 input or v2 engagement root must never be reinterpreted by the legacy phase
driver. Explicit v1 input and state-only v1 roots continue to reach their historical route.

## Failure-first scenarios

1. **Default help:** run `python3 tools/native_engagement.py --help`; output lists v2
   operator commands (`inspect`, `run`, `status`, `direction`, `resume`, `stop`, and
   `export`) and legacy commands remain discoverable.
2. **Equals-form v2 input:** run `run --inputs=PATH --engagement-root=ROOT` with a
   deliberately incomplete document whose kind is `native-engagement-inputs-v2`.
   The public command rejects it through v2 validation and creates no engagement root.
   The fixture has no usable signature or target/provider configuration, so no external
   call can occur.
3. **Malformed input:** an unreadable/malformed `--inputs=PATH` rejects without creating
   a v1 driver state or silently selecting the legacy parser.
4. **Explicit v1 input:** run the historical `run --inputs PATH --engagement-root ROOT`
   against a minimal v1 fixture. The resulting state kind is
   `native-engagement-driver-v1`; it does not create a v2 `events/` journal.
5. **State-only v1 root:** `status --engagement-root=ROOT` reads an existing
   `native-engagement-driver-v1` state file and returns its phase without creating v2
   contract/events files.
6. **Conflicting root:** a root containing both v1 `state.json` and v2 `events/` is
   rejected as a route conflict; neither route mutates the root.

All scenarios use private temporary files and a dummy non-runnable runtime path. The
command must not start a provider, Docker, SSH, or target operation. The check is local
CLI-routing evidence only; it does not qualify a native runtime or research result.

## Repeatable command

```sh
python3 evals/native-qualification/smoke/check_native_caller_migration_e2e.py \
  --output /private/results/native-caller-migration.json
```
