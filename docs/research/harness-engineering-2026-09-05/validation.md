# Validation and handoff boundaries

2026-09-05. Inspected production source: `6a47b64264b6bf8f1edf8923847cfc9952cd1ab8`.

**Later publication update:** the operator subsequently approved the boundaries and breakdown. The [approved handoff](handoff.md) records publication and verification; the checks below describe the earlier research/draft validation and were not rerun as implementation acceptance.

## Executed evidence

- Evaluation's original batch characterized 15 synthetic cases plus Q02's 26 and flow's seven built-in assertions. Invalid favorable verdicts are observed defects, not accepted outcomes. The original flow fixture initialized one fabricated local event; this is explicitly documented and the generated record scaffolding was not retained.
- The narrower retained evaluation reproducer passed 16 checks using public Q02 commands and pure accounting helpers. It performs no record-kernel initialization, lifecycle operation, target or provider work. [Exact coverage, commands and manifests](checks/evaluation/README.md).
- The retained reconstruction reproducer passed: all six baseline outputs match the original bytes, three semantic input changes remain invisible, and the visible-revision positive control changes output. It runs only two AST-extracted pure renderer functions against handcrafted inputs. [Reproducer](checks/reconstruction_probe.py), [original results](checks/reconstruction/results.json).
- Both entrypoints were compared byte-for-byte, active reference absence was checked, the declared draft overlay pin matched, and the host Claude version was observed. This was not a session-loading test. [Instruction check limits](instructions.md).

The source and test bodies cited in the foundation/message-board research were inspected. No upstream runtime test, message-board agent experiment, operator-time comparison, paid study or production acceptance run was performed.

## Independent draft review

Three bounded reviews covered evaluation/accounting, record reconstruction and external-source/experiment fidelity. Corrections incorporated before handoff:

- M1 package counts and M6 root-cause groups retain distinct units, with compatibility unknown rather than an implicit conversion.
- Admission now has explicit malformed/incomplete/adverse/admitted outcomes and reference-binding requirements.
- The study report consumes normalized supplied records. Case coverage, recorded-receipt coverage and completeness evidence remain separate. A complete total requires scope, measurements and allocation to be complete for that metric.
- Graceful supplemental failure applies only outside existing base admission. Missing locks and final identity rejection cannot create or emit valid state.
- A grader receives designated final outputs against a fixed reference; treatment labels, peer discussion and self-grades are withheld. Scripted observations are available at the same declared release point across communication arrangements.

These are document reviews of a proposed contract. They do not validate an implementation.

## Artifact and workspace checks

The handoff check resolved 102 local Markdown destinations across 21 authored research/draft documents with no missing files; historical log paths are provenance rather than required inputs. Canonical evidence copies and hashes were checked during retention. The full staged whitespace check correctly flags the original blank-waste stdout, whose trailing spaces are the behavior being characterized. Those canonical bytes remain unchanged. The authored-content whitespace check excludes only the exact canonical evidence directory.

Only new research, retained benign checks and local specification/ticket drafts are included. The active checkout remains at the inspected commit with its seven pre-existing tracked edits preserved. No push, pull request, implementation, historical recomputation or operational gate change belongs to this handoff.

Research issues are resolved with source-backed comments under the engineering map. The map stays open while the user reviews the concrete test boundaries and ticket breakdown; the spec and implementation tickets have not been published as ready work.
