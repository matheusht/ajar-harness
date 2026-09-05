# Instruction and configuration evidence

Research date: 2026-09-05. Inspected repository: `6a47b64264b6bf8f1edf8923847cfc9952cd1ab8`, in a clean research worktree. Scope: documentation quality and read-only evidence of what a session was configured to receive. No runtime, settings, scope or gate changes.

## Answer

Fix specific broken guidance and make input provenance visible before treating repetition as a model-memory defect. Preserve the intentional entrypoint mirror and the existing distinction between draft and frozen evaluation pins. A file digest establishes which bytes were selected; it does not establish that a client loaded them or that a model applied them correctly.

The representative affected launch path remains unverified. An optional question was sent to the operator. This limits causal diagnosis and the choice of an ordinary-session baseline; it does not prevent identifying broken references or specifying honest missing-data behavior.

## Observations and measured checks

1. **Both entrypoints are identical, not competing versions.** A direct byte comparison passed. Each has 123 lines and SHA-256 `0dbf760b7a4d2d9b456a695973b4a98ba6468affce9a28590451a46ae13c0e51`. The repository explicitly decided to retain this mirror, and the conformance checker compares the hashes. Removing one copy or replacing it with an import would change that contract. [Confirmed mirror decision](../../engineering/002-decisions.md#d-03-keep-agentsmd-enforce-the-mirror-by-machine), [mirror check](../../../tools/check-conformance.py).

2. **Two referenced setup documents are absent.** Both entrypoints point to the missing issue-tracker document at line 117 and the missing domain document at line 123. The root entrypoints already provide the tracker and ADR location. The current investigation recovered the remaining conventions from existing tracker issues. Adding another source of instructions is not required to establish this defect. [Entrypoint](../../../CLAUDE.md), [current decision index](../../decisions/README.md).

3. **Current and historical status language are mixed.** The README contains the implemented record-kernel section and a final `v0` scaffold status. The architecture summary lists three conceptual record types, while the implemented records and reviews have richer semantics. These are navigation and freshness problems, not evidence that every historical statement should be rewritten. The dated engineering decision document also contains historical implementation and proposal states; it should remain historical evidence rather than silently becoming a current checklist. [README](../../../README.md), [architecture summary](../../architecture.md), [dated engineering decisions](../../engineering/002-decisions.md).

4. **The existing overlay checker already distinguishes draft drift from invalidated frozen evidence.** It discovers preregistrations, compares file pins, reports stale drafts and treats authorized drift as failure. Its update path refuses to repin an authorized record. The inspected A/B readiness record is currently `draft_not_authorized`, with `execution_authorized: false`; its AGENTS digest matches the current bytes. This is not evidence that a study ran. A later documentation edit must preserve the distinction between updating an unused draft and silently changing a frozen comparison. [Overlay checker](../../../tools/overlay_pins.py), [readiness record](../../../evals/research-kernel/ab-readiness/preregistration.json).

5. **The documented launch paths differ.** Harness-local project settings, an ordinary session in another project and a supervised session are different configurations. The session-end document describes the distinction explicitly. This research did not launch any of them, inspect personal permission values or infer which path explains the reported day-to-day behavior. [Session-end activation boundary](../../agents/session-end-backstop.md).

6. **Host version is observable, actual session configuration is not established here.** `claude --version` returned `2.1.261 (Claude Code)`. This identifies the host executable available to this shell, not every prior session or container image.

## Primary-source interpretation

Claude's current documentation distinguishes contextual instructions from enforced settings. It describes hierarchical instruction loading and a client view for checking loaded memory files. Settings have separate precedence and merging rules. These documents support recording the effective source and configuration, not assuming that file presence proves loading. Current documentation also has worktree-specific behavior, so a clean Git checkout alone is not necessarily a clean native-client configuration. [Instruction loading](https://code.claude.com/docs/en/memory), [settings](https://code.claude.com/docs/en/settings), relevant sections read September 5. Installed behavior was not exercised.

The documentation's suggested import arrangement does not override this repository's accepted mirror decision. There is no demonstrated gain that justifies changing that decision in this phase.

## Minimal direction for the specification

- Repair or remove the two broken setup references. Put a short current-state pointer where an old summary otherwise appears current. Keep historical decisions and retained controls intact.
- Reuse the existing mirror and pin checks. A focused check of active setup references can extend documentation conformance; it does not need a generic Markdown crawler or another configuration system.
- In the offline comparison/reconstruction record, distinguish **declared inputs**, **observed client loading**, and **recorded model input**. Mark the latter two unknown when no observation establishes them. An operator correction may identify a missing input; it does not retrospectively prove what the earlier request contained.
- Record only the metadata required to compare a trial: client/runtime version, launch category, model identifier when known, declared instruction/source digests and the provenance/availability of loading observations. Do not retain raw prompts, environment values, credentials or broad private configuration dumps by default.
- Keep a correction reason distinct from time spent. A complete labor account also includes useful preparation, review and repair that did not trigger a correction event.

These are proposed specification requirements, not implemented collection or loading behavior. The view is for read-only diagnosis; it must not launch a session, set permissions, select operational work or claim that a rule was obeyed merely because it was present.

## Test boundary and reversal

Use the existing documentation conformance boundary for mirror, active-reference and pin behavior. For the proposed read-only input report, use the same public offline-inspection boundary as evidence reconstruction: a harmless document v1/v2 case, one missing instruction reference, and an unavailable load observation should produce distinct supported, missing and unknown facts without writes to source records.

Reverse the additional metadata requirement if a field never distinguishes competing explanations or reduces reconstruction work. Do not remove unknowns to make the report look complete. Do not attribute a model-judgment failure to loading when complete, current input was demonstrably supplied.

## Reading coverage

Full reads: root entrypoint, README, architecture summary, decision index, session-end backstop, dated engineering decisions. Exact mirror/reference/hash check covered only the six named files, not every link in the repository. Sampled code: conformance lines 805–875 and 1518–1544; overlay-pin module lines 1–145; relevant telemetry/configuration references. Readiness JSON inspection selected status and safety-overlay fields. External documentation was sampled around instruction loading, checking loaded files, and settings precedence/worktree behavior. No target records, personal settings values, provider calls or operational execution were used.
