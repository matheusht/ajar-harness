# Run-1 packets — INVALIDATED, retained as the record

These five packets were used for run 1 of the framing-invariance probe on 2026-08-12. **They are
contaminated and must not be used again.** They are kept because the run happened and deleting the
input would leave the outcome document unverifiable.

What is wrong with them, and why `verify` did not catch it, is in
`fixtures/preregistration/framing-invariance-OUTCOME.md`. In short: bare scores (4.9, 6.5, 7.7, 8.1,
8.8, 3.1, 4.3, 7.1, 7.4) and the audit's own narrative survived the scrub, and the verifier looked
only for what the scrubber already removed.

Running `tools/framing_probe.py verify` against any of these now reports the leaks, because the
detector was strengthened afterwards. That is the intended behaviour and the reason this directory is
excluded from the conformance sweep — the active packets live in `packets-v2/`.
