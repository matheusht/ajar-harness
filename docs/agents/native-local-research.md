# Native local research (candidate route)

This route is staged for issues #166–170. It becomes the ordinary path only
for the class named in a **scoped adopt** decision on #165, after the cited
unhinted outcome, review, controls, and historical access pass. Until then,
follow the [legacy engagement route](../../CLAUDE.md#4-the-runbook-legacy-engagement)
for supported work. A pilot, repair, no-go, or closed issue without an adopt
decision does not activate this route.

## Start and resume

1. Read root `AGENTS.md`/`CLAUDE.md`, the actual task permission, effect and
   escalation ceiling, target/source identity, exclusions, stop conditions,
   allowance, and cleanup authority. Verify the target-local signed
   `engagements/<id>/scope.md` before any run. Use only a vulnerability card
   with a benign `safe_signal`.
2. Give the native runner a brief that states the target and objective,
   permission boundary, allowance, exact source if relevant, and what evidence
   would disprove the main claim. Put any authorized optional reference or
   tool file into the frozen source tree before `prepare`, and name it in the
   brief. The runner admits regular copied files only; it does not inherit
   ambient home, Git history, plugins, MCP, or external mounts. Use a
   persistent run root outside `engagements/<id>`; never initialize the legacy
   queue or record kernel for this native task.
3. Use `python3 tools/native_research.py prepare --help` for the current
   source/brief/scope, target-runtime, image, model, and pinned relay/CA
   inputs. Inspect its frozen plan. For the current qualification route, a
   human-authored approval file records explicit permission bound to that
   plan and scope. After a scoped #165 adopt, a standing signed authorization
   can supply that permission only if the runner binds its exact target,
   model, effect and expiry pins. Then call `start --run-root
   <absolute-path> --approval-file <file>`. The runner owns the target and
   research containers, observer capture, runtime limits, and exact resource
   cleanup. A permission prompt alone does not prove an effect was contained.
   Save actual inputs, outputs, observations, and contrary results as ordinary
   research files in the run root.
4. For continuation, use `resume --run-root <absolute-path> --session
   <exact-native-session> --prompt-file <file>` after inspecting the previous
   result and unresolved effects. Keep a material strong lead as unfinished
   when time or access stops work. For stop, use `stop --run-root
   <absolute-path>` and inspect `status --run-root <absolute-path>` with the
   runner's actual cleanup and any remaining effects. An unknown dispatched
   effect stays unknown until reconciled.

Research can choose and revise experiments. Budget, user, safety, and blocked
stops are honest stopping reasons; none implies exhaustive coverage. Native
work does not require queue admission, manual event pairs, harmless-file
registration, generated-view repair, signed report acceptance, memory
disposition, or formal engagement closure.

## Review and result

Freeze a sanitized observer-owned handoff for a fresh independent reviewer.
The reviewer must see the exact claim/evidence version, original-target
effect origin and reachability, contrary evidence, and what remains uncertain.
A changed material claim or evidence invalidates the affected conclusion and
needs fresh review. A material strong lead may be deprioritized as unfinished;
calling it disproved or irrelevant requires fresh review of that dismissal.

Write the requested internal result in the run root. Bind each supported
effect and condition to observation and review, state negative controls and
limits plainly, and reconcile the result after material edits. Local output
is not external delivery or a canonical confirmed finding. External action,
severity escalation, and Zone-2 artifact creation still follow the current
root policy and signed scope. Redact credentials, tokens, signed URLs, and
personal data from saved evidence.

Existing work that depends on `tools/run-work-queue.py`, `tools/run-engagement.py`,
`tools/finding_lifecycle.py`, or the historical ledger keeps that
[legacy procedure](docker-work-queue.md). Native research does not convert or
rewrite those records. The [cutover contract](native-cutover-contract.md)
lists the retained callers and checks that must pass before adopting the
default.
