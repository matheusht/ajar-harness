# Native source setup turn

The signed scope and host authority receipt define authority. Read the original source at
`/source`; it is read-only. Your disposable, size-limited workspace is
`/workspace/project`. You have no target service or target network. The only
network path is the metered model relay. Do not run a target build, fetch
dependencies, or claim a security result.

Inspect the source and choose a runtime. Write `recipe.json` in your workspace.
For a signed full-engagement scope, use `native-setup-recipe-v2` with exactly
`kind`, `runtime`, `build_command`, `offline_dependencies`, and `outputs`.
List the files the offline build must produce in `outputs` as relative paths.
For a setup-only scope, use `native-setup-recipe-v1` with exactly the first four
fields. `runtime` has `version_command` (argv),
`version_stdout` (expected trimmed output), and `dependency_command` (argv).
`build_command` is an argv array. `offline_dependencies` is a list of specific
packages or source paths the host must supply before an offline build; use an
empty list only when none are needed. Write `THREAT_MODEL.md` with source-backed
entry paths, assets, actors, trust boundaries, assumptions, unknown conditions,
and a check that could disprove a material assumption. The host freezes this
initial model; later evidence-linked corrections belong in research notes.
The recipe and model are proposals, not authority or proof.

If the runtime or dependencies cannot be determined, leave a specific blocked
explanation in `THREAT_MODEL.md` and do not invent a passing recipe. If an action
may have had an effect but its result is unknown, stop and preserve its pending
record for host readback. Never retry an uncertain action automatically.
