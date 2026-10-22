# Portable workspace integration: checks before implementation

The existing runner retains application bytes and native conversation storage,
but does not load the portable workflow or expose an ordinary continuation record.
The smallest complete change stages ordinary Markdown and one sanitized current
run snapshot through the existing runner; it adds no agent or provider framework.
OpenCode remains the pinned qualification integration. These checks establish
filesystem and caller behavior, never model adaptation or target qualification.

Before implementation, exercise these failures through public preparation and
the public research/resume/reconstruct commands. Substitute native API/dispatch
and the live allowance reader only where a running provider/target would otherwise
be needed; keep actual preparation, files, prompt composition and dispatch logic.

| Failure | Required check |
| --- | --- |
| Native history is the only useful research state | Preparation freezes the workflow and brief and seeds an ordinary `/workspace/RESEARCH.md`, outside the application source; scripts/results remain in the project. A fresh session reconstruct command consumes these files without an existing session ID. |
| Instructions exist but are never loaded | Actual research/resume/reconstruct dispatch prompts name `/research/WORKFLOW.md`, `/research/BRIEF.md`, `/research/RUN.json`, and `/workspace/RESEARCH.md`; prompt hash covers the injected prompt. |
| Worker can rewrite authoritative run state or a reviewer inherits the notebook | The research and resume mount is read-only `/research`; reviewer mounts have no research snapshot or notebook. Frozen workflow and brief hashes are verified before use. |
| A new context restores allowance or retries an uncertain effect | Under the existing turn lock, derive current consumed and remaining time/connections/bytes from the original allowance; archive the exact per-turn snapshot. Unknown dispatches, inactive runs, unavailable allowance, and exhausted allowance reject before any native API call. |
| Reconstruction silently resumes native history | Create a fresh session in the existing resume producer and same workspace; label it `fresh_context_from_workspace`, without claiming successful reconstruction. Ordinary resume retains its supplied session. |
| Old plans appear portable without the new files | Reconstruction refuses an old plan explicitly; original research/resume remain native-history-only. |
| Notes disappear or stale files overwrite work | Missing notebook or altered workflow rejects reconstruction; existing notebook/scripts/results survive dispatch and are never regenerated. Stop byte collection includes the ordinary notebook hash, without retaining its contents. |
| Advice becomes new authority or exposes protected material | Snapshot says it is advice at a point in time, keeps unknown provider request/cost metrics null, includes only source/scope identity and prior dispatch IDs/status, and excludes private scope text, credentials, target answers and reviewer content. |
| Provider lease expires before native-run deadline | The current allowance exposes the actual provider pool creation time plus duration; remaining time is the smaller of provider wall-clock expiry and native monotonic expiry. Missing/invalid provider expiry or an expired provider lease rejects before native calls. |
| Ordinary notebook bypasses bounded stop hashing | Reject a notebook larger than 8 MiB before hashing it in the stop snapshot, using the same limit as continuation. |

Run `PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_portable_research_workflow.py`.
Requirements: Python 3, OpenSSL, Docker CLI (no daemon calls), and the existing
pinned local relay file. Expected result: `PASS` with zero provider/target calls.
Save `--output /absolute/private/path/result.json` when a repeatable receipt is
needed. A failing preimplementation execution and the final execution are separate
observations; a synthetic dispatch never qualifies an adaptive research result.
