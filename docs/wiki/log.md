# Engineering wiki log

Append dated entries. Record durable source ingestion, decisions, implementation evidence and corrections; keep the earlier entries intact. Maintenance conventions are in [AGENTS.md](AGENTS.md).

## [2026-09-05] create | Engineering wiki and implementation goal

The user corrected the earlier request to update an existing LLM Wiki: none existed, and they asked to start one for engineering decisions and other documentation, supplying [Karpathy's LLM Wiki note](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). Read the complete note and adopted a small repository-local Markdown wiki with an index, topic synthesis, maintenance instructions and this append-only log. The [index](index.md) records the source-content hash and reading date.

Seeded [offline engineering evidence](engineering-evidence.md) and [recovery/communication experiments](comparison-experiments.md) from the approved September 5 investigation and six-ticket handoff. Linked the existing decision and engineering indexes without claiming to have ingested or revalidated their full history. Retained original sources in place.

Added the [implementation goal prompt](../research/harness-engineering-2026-09-05/implementation-goal-prompt.md): intent/scope/non-goals/acceptance first; High reserved for planning; the user's allowed implementation model/effort pool; bounded coordination; necessary command-level end-to-end checks; permission boundaries; incremental wiki updates; and the tested/small-diff/no-unnecessary-abstraction completion gate.

Source baselines: research `6a47b64264b6bf8f1edf8923847cfc9952cd1ab8`, reviewed plan `d150f8d04fd902b48f6a5914880637d39e29a2d1`, publication documentation `ed558ad271d008195a5153bdc3dd97312dbc74f2`. Main rechecked at `0d8fe0c4ffb57a3bf1cfd5d4db013113b51d8c8d`, preserving its already-completed guidance overlap in the synthesis.

This entry records planning/documentation only. No implementation worker, model experiment, board service or runtime change was started. No claim is made that wiki maintenance has reduced effort. Production tests are unnecessary for these documentation-only changes.

Verification: a bounded Python link check covered the eight authored/updated Markdown files and resolved all 72 local destinations; every wiki page is reachable from the index. Manual review checked the six ticket references, dependency order, execution-model constraints, four public test boundaries and the explicit experiment stop. Whitespace validation passed for the staged documentation diff. No application or test infrastructure was added.

## [2026-09-05] implement | Start execution and finish guidance slice #107

Started from clean isolated merge `f68caf673ef9ed12aae4f6e43d64b299c5a1ecc9` (main `0d8fe0c4ffb57a3bf1cfd5d4db013113b51d8c8d` plus research/wiki documentation). Branch: `codex/implement-harness-engineering-2026-09-05`. Actual execution setting: one `gpt-6-astra` worker at `low`; planner remains planning-only. Applied the installed `/implement` and Ponytail Full skills, now explicitly named in the [goal prompt](../research/harness-engineering-2026-09-05/implementation-goal-prompt.md). The optional `/tdd` skill was unavailable in installed skill directories; the approved documentation seam still used a failing public check before the repair.

The current #107 body was re-read with `gh issue view 107 --repo matheusht/redteam-harness --json body,state,updatedAt`: OPEN, updated `2026-09-05T18:30:57Z`, matching the local criteria. Reused main's removal of both absent setup references and draft-pin update. Added only current-status navigation in README and the historical architecture summary, a fixed active-reference conformance check, its bounded CLI option and compact temporary CLI regression controls. Entrypoint bytes, repository pins, historical decision files and operational instructions are unchanged.

Checks on this entry's implementation diff against the source baseline above:

- `python3 tools/check-conformance.py --engineering-guidance`: red before the documentation edit (12 checks, 4 failures for the missing current pointers), then green (12 checks, 0 failures).
- `python3 tools/engineering-guidance-test.py`: passed. Temporary copies invoke the actual conformance and overlay-pin CLIs; missing destinations, mirror divergence and reintroduced setup references fail; historical scaffold prose remains allowed. Draft drift is reported as stale by the overlay CLI and outstanding by conformance, explicit draft repin succeeds, authorized drift fails and repin refuses without changing bytes.
- `python3 tools/overlay_pins.py check --json`: 0 failures, 0 stale; readiness remains `draft_not_authorized`, `execution_authorized: false`, with all four pins matching.
- A bounded inline Python check of the six changed Markdown pages resolved all 42 local link destinations.
- `python3 -m py_compile tools/check-conformance.py tools/engineering-guidance-test.py` and `git diff --check`: passed. No typechecker is configured for this small stdlib Python/docs slice.

An initial `python3 tools/check-conformance.py` invocation preceded the bounded-mode decision and stopped at `check_finding_fixtures` with `validator_unavailable` because system Python lacked the pinned JSON-schema dependencies. It is not acceptance evidence. Inspection showed the default path also includes operational and historical checks; those are outside this offline goal, and the narrow option avoids them. No blanket suite result is claimed; final safe regression/review remains pending after the remaining slices. No experiments, target/provider calls, repository pin refresh or historical result recomputation were performed by the accepted checks. Local completion of this slice does not close any tracker issue or establish the six-ticket goal complete.
