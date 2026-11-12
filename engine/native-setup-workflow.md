# Native source setup turn

The signed scope and host approval define authority. Read the original source at
`/source`; it is read-only. Your disposable, size-limited workspace is
`/workspace/project`. You have no target service or target network. The only
network path is the metered model relay. Do not run a target build, fetch
dependencies, or claim a security result.

Inspect the source and choose a runtime. Write `recipe.json` in your workspace
with exactly `kind`, `runtime`, `build_command`, and `offline_dependencies`.
`kind` is `native-setup-recipe-v1`. `runtime` has `version_command` (argv),
`version_stdout` (expected trimmed output), and `dependency_command` (argv).
`build_command` is an argv array. `offline_dependencies` is a list of specific
packages or source paths the host must supply before an offline build; use an
empty list only when none are needed. Write `THREAT_MODEL.md` with source-backed
assets, trust boundaries, possible failure paths, and uncertainty. These are
proposals for host review, not authority or proof.

If the runtime or dependencies cannot be determined, leave a specific blocked
explanation in `THREAT_MODEL.md` and do not invent a passing recipe. If an action
may have had an effect but its result is unknown, stop and ask the operator to
reconcile it. Never retry an uncertain action automatically.
