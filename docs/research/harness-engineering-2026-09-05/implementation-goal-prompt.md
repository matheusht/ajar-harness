# Implementation goal prompt

Prepared 2026-09-05 for the approved [specification #106](https://github.com/matheusht/redteam-harness/issues/106) and [six-ticket handoff](handoff.md). This document prepares execution; writing it does not start implementation or an experiment.

Copy the prompt below into the task that will own implementation. The repository's new [engineering wiki](../../wiki/index.md) lives at `docs/wiki/`; update it throughout execution.

---

Implement the approved trustworthy offline engineering evidence specification, [#106](https://github.com/matheusht/redteam-harness/issues/106), through its six child tickets [#107](https://github.com/matheusht/redteam-harness/issues/107), [#108](https://github.com/matheusht/redteam-harness/issues/108), [#109](https://github.com/matheusht/redteam-harness/issues/109), [#110](https://github.com/matheusht/redteam-harness/issues/110), [#111](https://github.com/matheusht/redteam-harness/issues/111) and [#112](https://github.com/matheusht/redteam-harness/issues/112). Complete the scoped implementation, necessary end-to-end validation and LLM Wiki documentation. Planning can be ambitious; execution must be lightweight. Constraints come first.

## First response: establish the contract

Before editing, restate these four points in your own words, grounded in the current checkout and approved tickets:

- **Intent:** make offline engineering evidence trustworthy enough to assess future recovery and communication choices.
- **Scope:** accurate active guidance, conservative Q02 admission, complete assigned-case accounting, read-only evidence reconstruction, and two concrete synthetic comparison packets.
- **Non-goals:** runtime replacement, a board service, provider adapters, paid/model experiments, live targets, exploit reproduction, autonomous offensive workflows, operational gate changes, historical recomputation, unrelated issue work and product strategy. The recovery and message-board tickets prepare experiments; they do not execute them.
- **Acceptance:** every applicable ticket criterion has evidence at its approved public boundary; complete and adverse synthetic cases behave correctly; source records remain intact; the final diff is scoped; added machinery has a demonstrated need; the LLM Wiki records decisions, changes, checks and limits. A passing synthetic check does not establish provider behavior, model benefit or production reliability.

Do not ask the user to reapprove the existing spec or breakdown. Resolve an actual conflict or missing required input while continuing independent work.

## Execution constraints

**Models and effort.** High handles planning only, including a specific design decision that blocks progress. Default implementation, test execution and review to **Astra Low** (`gpt-6-astra`, `low`). Allowed alternatives are **Sol Low** (`gpt-5.6-sol`, `low`), **Luna High** (`gpt-5.6-luna`, `high`) or **Terra Medium** (`gpt-5.6-terra`, `medium`). Luna High is the explicit implementation exception. Choose one before execution and record the actual selection. Prohibit Max, Ultra, XHigh and equivalent elevated modes throughout; never silently inherit the planner's effort into a worker. If the environment cannot establish an allowed execution setting, finish the plan and request the minimal model/handoff change; do not implement under an unapproved setting.

**Coordination.** Use one implementation worker at a time and reuse it across slices. The High planner hands off bounded work and returns only for a concrete planning decision. No random spawning, nested delegation, standing reviewer panels or orchestration framework. An additional worker requires an identified independent task, nonoverlapping ownership and a concrete expected saving; give it the same permitted model/effort limits. Sequential execution is the default even where tickets are independent.

**Tools and skills.** Use the repository's existing tools, standard library and installed dependencies. Prohibit heavy skills, broad research workflows and automatic chains of planning/review skills. Read only the governing instructions and narrowly relevant references. A research question earns more investigation only if its answer changes an acceptance criterion or the next implementation choice; bound the question and stop when answered.

**Necessity.** Before adding a module, dependency, schema layer, persistent store, abstraction or new command, name the approved requirement, the observable failure it fixes, the existing facility considered and the simplest adequate alternative. Prove necessity with code evidence or a bounded check, not hypothetical scale. Prefer deletion, then reuse, then a direct implementation. An unproven design stays deferred by default. Do not use this rule to omit an approved behavior: implement it simply or surface the specific conflict.

**Permissions and preservation.** This goal authorizes scoped local edits, synthetic tests, recoverable commits/worktrees and routine documentation in the identified LLM Wiki. Git rollback does not make an action irreversible; do not interrupt for ordinary reversible engineering. Preserve unrelated edits and uncommitted data. Confirm genuinely irreversible or externally consequential actions before performing them, including destructive data loss, deployment, publication/sharing, remote push/PR/merge, new paid runs and unapproved external communications. Prepare a concrete reviewable result first. Do not repeatedly ask about already authorized actions. Separate operational holds remain in force. Issue closure requires an explicit instruction; local evidence can be prepared without closing anything.

## Ground the work and implement in slices

Read the current `AGENTS.md`/`CLAUDE.md`, decision index, spec, ticket bodies and relevant comments. Record the source commit, working-tree state and actual model/effort. Use a clean isolated implementation checkout based on current main when the active checkout contains unrelated work. Preserve access to the approved [research index](README.md), [validation record](validation.md) and [handoff](handoff.md); historical research is evidence about its pinned revision, not proof of the current checkout.

These planning documents and `docs/wiki/` currently live on local branch `codex/research-harness-engineering-2026-09-05`. If the implementation checkout lacks them, carry the relevant documentation from that branch after checking for newer versions. Preserve one evolving wiki and current production source; do not replace current main with the older research base.

Main commit `0d8fe0c4ffb57a3bf1cfd5d4db013113b51d8c8d` already removed the broken setup references and updated the draft instruction pin. Recheck current main and reuse that work. Do not blindly replay a patch from the earlier research base.

Use this execution order unless current evidence makes a simpler order preferable:

| Slice | Deliverable and dependency |
| --- | --- |
| [#107](https://github.com/matheusht/redteam-harness/issues/107) | Finish only the remaining active guidance/status work; preserve history, mirrors and pin semantics. |
| [#109](https://github.com/matheusht/redteam-harness/issues/109) | Report every assigned offline case and supplied normalized activity, with separate quality, labor, usage and completeness limits. This unlocks both packets. |
| [#108](https://github.com/matheusht/redteam-harness/issues/108) | Repair the shared Q02 admission boundary while retaining its frozen decision rule, distinct M1/M6 units and limited conclusion license. |
| [#110](https://github.com/matheusht/redteam-harness/issues/110) | Explain admitted evidence, revisions, reviews and report state through a read-only public inspection. |
| [#111](https://github.com/matheusht/redteam-harness/issues/111) | After #109, prepare the benign recovery cases/protocol and validate illustrative accounts. |
| [#112](https://github.com/matheusht/redteam-harness/issues/112) | After #109, prepare the serial/direct-handoff/board comparison and validate illustrative accounts. |

The first four tickets have no dependency on one another. Q02 is not the general study evaluator. For each slice, trace the relevant flow and all callers before changing a shared function; write the smallest meaningful failing check, implement the behavior, run the relevant checks and inspect the diff. Commit coherent, verified increments and update the wiki. Leave sound unrelated code alone.

## End-to-end tests where they matter

Use the real public commands in temporary directories with harmless synthetic documents/metadata. Cover input files through exit status, output, conclusion limits and filesystem effects. Keep fixtures compact and reuse existing test infrastructure. Pure helper tests or invented expected traces alone do not satisfy these boundaries.

| Boundary | Required observable checks |
| --- | --- |
| Guidance conformance | Current pointers/status are accurate; entrypoint mirrors match; draft versus authorized pin behavior is preserved. Use existing checks; add no generic documentation crawler. |
| Q02 measurement → verdict | A fully bound admitted control; malformed inputs fail with exit 1 and no verdict/license/traceback; incomplete or unsupported evidence is inconclusive with exit 0 and explicit reasons. Exercise missing/adverse integrity, duplicate keys/identities, unavailable versus mismatched references and source/case/run mismatches. Include multiple eligible packages sharing one root-cause group: M1 and M6 keep their distinct units. Preserve the frozen rule and required quarantine/identity regressions. |
| Study inputs → report | Include every frozen case, especially failed, interrupted and no-output cases. Test complete and unknown scope, one unknown cost, duplicate delivery, conflicting receipt identity and unresolved human/runtime overlap. Separate case coverage, receipt coverage and completeness. A complete total requires scope evidence, complete measurement and nonoverlapping allocation for that metric; otherwise show a qualified subtotal. Missing measurement is never zero. |
| Dossier → reconstruction | Distinguish source and claim revisions, predecessor adjudication, review subject/reason, historical report and current event-derived acceptance. Preserve external identifiers and unknown mappings/loading/task context. Cover stale views, invalid indexed records, separately invalid supplements, missing coordination and final identity rejection. Compare source bytes and file inventory before/after: no writes or new coordination state; rejected final identity emits no valid summary. |
| Comparison packet → study report | Each packet supplies concrete synthetic records accepted by the same report boundary, plus incomplete/adverse records that remain qualified. Validate declared schedules, access and grader separation. Do not build a runtime or board to test a preparation artifact. |

For recovery, cover late corrections, recorded-but-unsupplied results, cooperative pause and simulated loss after a write without a receipt. Keep local admission, adapter invocation and unobserved provider receipt distinct; source inspection and illustrative traces cannot earn an execution pass.

For communication, keep all three arrangements: serial complete-source work; parallel direct handoff with curation; identical parallel work plus at most five short board notices per packet. Use the complete-source, complementary-evidence and late-correction packets, including a stale/unsupported notice. Match information, model/configuration, total budget and observation release timing. Count preparation, coordination, reading, curation, failures and human repair. Preserve independent initial observations and a fixed reference grader isolated from treatment labels, peer discussion, self-grades and other-case answers. Retained, available, used, correct and useful are different observations.

Run focused checks as slices change. At the end, run the repository-required regression/conformance suite appropriate to the touched contracts once, plus the integrated command cases above. Repeat only after relevant changes or unresolved failures. Record exact commands, revision, results and skipped checks with reasons. Fix failures introduced by this work; distinguish any reproduced baseline failure. Do not claim complete when a required acceptance check is unverified.

## Document in the LLM Wiki as work proceeds

Use the repository's `docs/wiki/`, starting with [its maintenance instructions](../../wiki/AGENTS.md) and [index](../../wiki/index.md). It was created for this work at the user's request. Reuse the relevant topic pages and preserve original decision/research sources in their existing locations. The wiki is maintained synthesis; it does not supersede an approved specification or turn a proposal into authority. Its location is resolved: ordinary scoped updates need no new permission.

Record the initial intent, constraints, source baseline, chosen execution model and ticket/test plan. At each completed slice or changed decision, update the relevant page and append a concise progress entry with source/commit links, implemented behavior, test evidence, limitations and any rejected/deferred design with its necessity rationale. Keep observations, hypotheses, proposals, implemented changes, verified results and untested claims distinct. Link primary evidence rather than duplicating raw transcripts. Preserve prior entries and provenance; include no credentials, private engagement material or unsupported performance claims.

## Completion gate and handoff

Before declaring completion, inspect the final diff and establish:

1. **Tested:** each ticket criterion maps to passing evidence or an explicitly reported blocker. The relevant end-to-end and required regression checks passed on the final implementation revision.
2. **Small diff:** every changed file serves the approved scope; no unrelated cleanup, redundant fixtures or avoidable generated artifacts remain. Small means sufficient, not omitted validation or safeguards.
3. **No unnecessary abstraction:** each addition has its necessity evidence; remove anything that cannot justify its existence.
4. **Documented:** the LLM Wiki records the outcome, source revisions, checks, decisions and remaining experimental prerequisites. Historical evidence and new results are clearly separated.

Report what changed, what passed, the final commit/diff, wiki links and material limits. Implementation completion means the offline tools and preparation packets are ready. The recovery and message-board experiments remain unexecuted. A later run needs established effective configuration, budget, cases, isolation and authorization; adoption needs repeated paired evidence and a predeclared practical benefit threshold. Stop at this boundary rather than building the unproven design.
