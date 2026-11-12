# Native local research

The candidate native route is the default for new local source research.
Runtime qualification and adoption remain unverified.
Read [product direction](../wiki/product-and-engineering-direction.md) for design
choices and [dated status](../wiki/native-research-status.md) for capability claims.
Actual runs still require permission, a frozen allowance and the enforced effect
boundary. If native preparation, access or evidence capture is unavailable, retain
the work as blocked or unfinished; do not initialize a legacy queue or record
kernel as a fallback. Existing record-backed workflows keep their explicit legacy
procedure described below.

## Start and resume

For source with no application listener, use
[source mode](native-source-sdk.md). Its environment and paid-provider
requirements differ from the service profile below. Source implementation is
available; live qualification is still pending.

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
3. Use `python3 tools/native_research.py prepare --help` as the source for
   current preparation inputs and inspect the frozen plan. For the pinned
   Kanboard T01 protected API route, opt into both `--t01-capture` and
   `--origin-ingress`. Use the exact
   [workspace brief](../../evals/native-qualification/RESEARCHER-BRIEF-T01-WORKSPACE.md)
   for researcher-led setup and normal web/API experiments in the own-copy
   workspace; its separate protected copy still supports only T01 API evidence.
   Startup checks the workspace image's PHP dependencies before native research.
   The historical API-only brief retains its narrower contract;
   `--kanboard-capture` selects the separate S10 UI case. Read the
   [T04 limits](../../evals/native-qualification/T04-UNHINTED-PREFLIGHT.md#workspace-research-with-a-separate-protected-api-copy)
   before treating either capture path as evidence for a selected effect.
   Use `capture-stage --help` for staging each private target copy. Read the
   current `start`, `research`, `resume`, `reconstruct`, and `stop` help before invoking them;
   keep the human-authored approval bound to the frozen plan and exact target
   state. After the exact run has stopped, use the relevant `reconcile-*`
   command help and reconcile the selected dispatch. Transport attribution
   from `reconcile-origin-transport` is not semantic effect proof;
   `reconcile-t01-semantic` separately checks the frozen T01 API receipts and
   stopped target state. `assess-poststop-review` still requires reviewer
   target effect/control receipts, completed reviewer actions, and
   process-origin attribution for the selected requests. A successful
   assessment produces at most a partial candidate for operator review. It
   still requires live qualification, clean replay and fixed-control evidence;
   review strong-lead dispositions separately when needed. Source and offline
   checks do not qualify a provider or target.
   Any standing permission still needs exact target/model/effect/expiry binding.
   Session setup and each native turn recheck the archived approval bytes and
   expiry. A source-mode `source-execute` call does the same before a new batch;
   a rejected call does not renew approval or shared allowance. An
   already-running turn can end after the approval expires, so review its
   effects before further work.
   The runner stages the portable
   [research workflow](../../engine/native-research-workflow.md), frozen brief,
   and current host-derived allowance snapshot at read-only `/research`.
   Keep the material interpretation, pending conditions and links to scripts,
   observations, review and internal output in `/workspace/RESEARCH.md`. Save each
   experiment or review once in its actual file or captured evidence and link it;
   do not mirror it into attempt/event pairs or a second record system.
   The notebook is advisory: its absence does not block native resume or make
   intact protected byte evidence incomplete. Recover material state from the
   saved scripts, results and evidence; missing facts remain unknown, not proven.
4. For continuation, inspect the previous result and unresolved effects. Use
   `continue --help` for repeated bounded turns over one active run; the controller
   reads the saved `NEXT.json` and stops rather than inventing the next experiment.
   Use `resume --help` to continue the exact native session or `reconstruct --help`
   to create a fresh context over the same files and run. Reconstruction is
   distinct from restoring native history; it cannot restore spent allowance or
   authorize retry of an unknown effect. The per-turn run snapshot is an observation
   of the shared allowance, not a new grant. Keep a material
   strong lead as unfinished when time or access stops work. Use `stop --help`
   and `status --help` to stop the run and inspect actual cleanup and remaining
   effects. After owner loss, use `recover-start --help` only for the runner's
   exact verified-stopped resources. An unknown dispatched effect stays
   unknown until reconciled from stopped-run evidence. `stop_reason` in status,
   final receipts, and recovery reports the first recorded stop trigger;
   absent or unreadable records leave the reason unknown. Check cleanup separately.

The current owner keeps an authorized run available. `continue` is the candidate durable
controller: it reads `controls/continuation/state.json` and `researcher/NEXT.json`,
holds one loop lease, and calls `research`, `resume`, or `reconstruct` one bounded
turn at a time. It writes a pending-dispatch marker before each turn and keeps an
append-only journal. A lost or invalid receipt can first return `invocation_failed`
while retaining the pending marker; the next continuation requires reconciliation
instead of retrying. It reuses the existing run and approval. Its allowance counters do
not add monetary accounting or reconciled provider billing.

`NEXT.json` is the checkpoint-level handoff. It records one of `supported`,
`refuted`, `blocked`, or `inconclusive`, what the result rules out, useful
capabilities and coverage, and the next brief or a stop proposal. An explicit stop
proposal or a `strong_lead` change from true to false produces
`closure_review_required`; a fresh reviewer or operator writes
`controls/continuation/closure-review.json` with mode `0600`:

```json
{"kind": "native-continuation-closure-review-v1",
 "request_sha256": "<sha256 of closure-request.json>",
 "decision": "accept",
 "reason": "what the review checked",
 "test": "required when decision is reopen; the concrete discriminating test"}
```

For approved source-only runs, `NEXT.json` may instead request one typed
[source check](native-source-sdk.md#researcher-requested-source-check). The host
freezes the source and command, executes under the offline envelope, and makes a
hash-only protected result visible to the next native turn. A missing envelope
stops for an authority decision; an older plan cannot be changed in place to
grant it. The result does not establish a security effect.

A reopen also requires a concrete next brief in `researcher/NEXT.json`; the
review's `test` is recorded in the closure review, and the researcher must put the
concrete next test in `NEXT.json` before the reopen continues. Budget or operator
stop is immediate and bypasses review. A refutation can close a lead; a blocked
surface remains unresolved. Coverage is a map with explicit limits, not proof that
no effect exists. The controller checks declared checkpoint markers; it does not
infer every negative conclusion from prose or prove reviewer independence. A
`refuted` result alone is not a final-closure marker. Fresh independent checking
remains the operator's procedural obligation.

If the controller returns `reconciliation_required`, inspect the exact dispatch
with the existing `status` and `reconcile-*` commands. Write a private operator
observation file, then run:

```sh
python3 tools/native_research.py continue --run-root <root> \
  --reconcile-dispatch-id <dispatch-id> \
  --reconcile-decision no_effect \
  --reconcile-evidence <private-observation-file>
```

`no_effect` clears the pending marker; `effect_observed` clears pending but keeps
the stop and records the observation. The dispatch ID must identify a real dispatch
record. The evidence file must be an absolute regular file with mode `0600` (for
example, write it under `umask 077`). Do not delete `state.json` to bypass the
marker. An `acknowledged` dispatch is a completed turn, not an unknown effect; the
controller refuses to reconcile it as pending. Inspect its receipt and stop state
instead of clearing it.

The 24-hour run ceiling is unchanged. The runner rejects `duration_seconds` above
86400 and approval expiry more than 24 hours after `approved_at`. A wall-clock
multi-day run therefore needs both a new frozen plan/approval and a reviewed change
to those validators; raising one timeout is insufficient. Long-horizon continuation
and its comparison remain unqualified; the
[evaluation plan](../../evals/native-qualification/LONG-HORIZON-PREREGISTRATION.md)
records the checks required before making that claim.

Research can choose and revise experiments. Budget, user, safety, and blocked
stops are honest stopping reasons; none implies exhaustive coverage. The stopping
reason does not need an empty queue, a frozen corpus denominator or a signed ending
exception. Native work does not require queue admission, manual event pairs,
harmless-file registration, generated-view repair, signed internal-review/report
acceptance, memory disposition or formal engagement closure.

## Review and result

The public `review` command takes an observer-selected frozen packet and a fresh
reviewer slot. After stop, `assess-poststop-review` checks the reviewer-target
T01 effect/control chain and process-origin attribution for the reviewer's
actions. A successful assessment is at most a partial operator-review
candidate; live qualification, clean replay, fixed control, and fresh review
of strong-lead dismissal remain separate as applicable. Freeze a sanitized
observer-owned handoff for each fresh independent reviewer.
The reviewer must see the exact claim/evidence version, original-target
effect origin and reachability, contrary evidence, and what remains uncertain.
A changed material claim or evidence invalidates the affected conclusion and
needs fresh review. A material strong lead may be deprioritized as unfinished;
calling it disproved or irrelevant requires fresh review of that dismissal.

Write the requested internal result under `/workspace/project` and link it from
`/workspace/RESEARCH.md` if maintained; on the host, these live under
`<run-root>/researcher`.
Bind each supported effect and condition to observation and review, state negative
controls and limits plainly, and reconcile every affected claim and dependent
conclusion after material edits. Drafting this ordinary internal file needs no
separate report-generation or report-acceptance step. A harmless quotation cannot
block native research, and an unsupported paraphrase cannot establish impact.
Generated summaries, stale displays or unrelated scratch do not decide whether an
effect is supported or work can resume. Missing material evidence remains unknown;
tampered frozen inputs, unsafe paths or corrupted evidence still fail their checks.

Verify actual cleanup and remaining effects independently of the output's wording
or a saved status. Stop and clean up resources the run created even when no finding
was made. If there are no effects or owned resources to reconcile, no additional
cleanup ceremony is needed. Learning is optional and must follow current memory
and redaction permissions; it is not a condition of ending research.

Local output is not external delivery or a canonical confirmed finding. External
action, severity escalation, and Zone-2 artifact creation still follow the current
root policy and signed scope. This route does not run the record kernel, so a
kernel-enforced standing local-PoC grant does not transfer to it: obtain fresh
human confirmation before Zone-2 creation until equivalent enforcement is
explicitly qualified and adopted. Redact credentials, tokens, signed URLs, and
personal data from saved evidence.

Existing work that depends on `tools/run-work-queue.py`, `tools/run-engagement.py`,
`tools/finding_lifecycle.py`, or the historical ledger keeps that
[legacy entry procedure](legacy-local-research.md). Native research does not convert
or rewrite those records. Explicit legacy filing or export keeps its original
validation, signature and acceptance rules; an ordinary native note is not imported
as a confirmed finding. Historical hashes, signatures, grades, waivers and frozen
source/campaign pins retain their original meaning. The
[native acceptance inventory](../../evals/native-qualification/NATIVE-ACCEPTANCE-INVENTORY-CHECKS.md)
checks private artifact bytes and receipt relationships after a run; a complete
inventory or a stopped-run status is not accepted research output, native
qualification or an adoption decision.
