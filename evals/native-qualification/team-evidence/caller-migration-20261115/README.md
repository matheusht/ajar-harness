# Native caller migration CLI check

This local CLI scenario records route selection before and after the public facade migration.
It uses private temporary fixtures and makes zero provider, target, Docker, or SSH calls.

- `before.json`: expected red on the pre-migration CLI. Default help omitted v2 commands; equals-form v2 inputs and malformed input fell through to the v1 parser. Existing explicit v1 and state-only v1 routes passed.
- `after.json`: all eight checks passed after the route change. V2 is the default; explicit v1 inputs and state-only roots retain the v1 phase driver; mixed v1/v2 roots reject.

The v1 input fixture has the exact legacy input kind and required path fields, but its
signature material is intentionally invalid. It reaches legacy state initialization and
stops during provider-free preparation. This proves route dispatch/state ownership only,
not successful signed v1 execution; historical run artifacts remain untouched.

Repeat with:

```sh
python3 evals/native-qualification/smoke/check_native_caller_migration_e2e.py \
  --output evals/native-qualification/team-evidence/caller-migration-20261115/after.json
```

This is CLI routing evidence only. It does not verify provider use, runtime isolation, target behavior, or research acceptance.
