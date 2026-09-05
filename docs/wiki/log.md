# Engineering wiki log

Append dated entries. Record durable source ingestion, decisions, implementation evidence and corrections; keep the earlier entries intact. Maintenance conventions are in [AGENTS.md](AGENTS.md).

## [2026-09-05] create | Engineering wiki and implementation goal

The user corrected the earlier request to update an existing LLM Wiki: none existed, and they asked to start one for engineering decisions and other documentation, supplying [Karpathy's LLM Wiki note](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). Read the complete note and adopted a small repository-local Markdown wiki with an index, topic synthesis, maintenance instructions and this append-only log. The [index](index.md) records the source-content hash and reading date.

Seeded [offline engineering evidence](engineering-evidence.md) and [recovery/communication experiments](comparison-experiments.md) from the approved September 5 investigation and six-ticket handoff. Linked the existing decision and engineering indexes without claiming to have ingested or revalidated their full history. Retained original sources in place.

Added the [implementation goal prompt](../research/harness-engineering-2026-09-05/implementation-goal-prompt.md): intent/scope/non-goals/acceptance first; High reserved for planning; the user's allowed implementation model/effort pool; bounded coordination; necessary command-level end-to-end checks; permission boundaries; incremental wiki updates; and the tested/small-diff/no-unnecessary-abstraction completion gate.

Source baselines: research `6a47b64264b6bf8f1edf8923847cfc9952cd1ab8`, reviewed plan `d150f8d04fd902b48f6a5914880637d39e29a2d1`, publication documentation `ed558ad271d008195a5153bdc3dd97312dbc74f2`. Main rechecked at `0d8fe0c4ffb57a3bf1cfd5d4db013113b51d8c8d`, preserving its already-completed guidance overlap in the synthesis.

This entry records planning/documentation only. No implementation worker, model experiment, board service or runtime change was started. No claim is made that wiki maintenance has reduced effort. Production tests are unnecessary for these documentation-only changes.

Verification: a bounded Python link check covered the eight authored/updated Markdown files and resolved all 72 local destinations; every wiki page is reachable from the index. Manual review checked the six ticket references, dependency order, execution-model constraints, four public test boundaries and the explicit experiment stop. Whitespace validation passed for the staged documentation diff. No application or test infrastructure was added.
