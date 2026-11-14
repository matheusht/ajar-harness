# Reporting skill benchmark — 2026-11-14

Second blind benchmark of the reporting skill, this round exercising the chain overlay. The
finding is the existing OKG `coins/bitcoin` PSBT sighash report; the PoC and expected output are
the same in both packages, so the comparison isolates the report shape.

- `old/` — the pre-refactor report package.
- `new/` — the same finding rewritten with the chain overlay.
- `MAPPING.private.md` — reviewer mapping (`A` = new, `B` = old). Reviewer copies were temporary and are not committed.
- `reviews/` — independent blind score sheets and `RESULTS.md`.

Protocol: `skills/reporting/references/triage-rubric.md`. Three reviewers scored both packages
independently; a fourth scored the corrected `A` after the first pass. The PoC was not run by the
reviewers. The package was run three times locally; stdout was byte-identical.

Reproduce the package check:

```sh
sh new/poc/stage.sh
diff new/poc/expected.stdout /tmp/new.out
```
