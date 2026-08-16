# Outcome — PREREG-20260809-spotify-phase2

**Decision: DO NOT graduate the gate. The gate stays.**

Recorded 2026-08-09 against `spotify-phase2.json`, which was declared before the data. That file is
unchanged, as it must be. This is the separate decision record required by `engine/autonomy.md` §8.

## The declared rule

The preregistration allowed exactly three outcomes. Graduate, keep, or inconclusive. There is no
partial pass.

> `declare_inconclusive_if`: "fewer than 40 negative verdicts are produced, or any withheld path was
> readable during the run"

## What happened

**The run never qualified as a measurement.** `tools/preflight_holdout.py` returned BLOCKED with 6 of
6 withheld paths leaking. One of the leaks was our own Phase-1a corpus,
`fixtures/interventions/backfill-corpus.json`, which quotes the Spotify policy-gate reversal. The
operator then chose Option C: keep Spotify for the cascading and hypothesis-generation test, and
graduate the gate later on a fresh engagement where no answer key exists. So no autonomy measurement
was available from this run, and none is claimed.

That alone forces `inconclusive`. The rest is why the answer is stronger than that.

## Why the answer is KEEP, not merely inconclusive

The gate under test was **oracle-negative re-confirmation**: batch the negatives and surface only
disagreements, low-confidence verdicts, and any `suspected_success`.

The run registered seven findings on **fifteen `claim_adjudication` reviews that a script generated**.
`tools/generate-spotify-findings.py` built each review record with the verdict already set:

```python
"verdict": "supported",
"independence": {"reviewer_id": "reviewer-external-canonical",
                 "fresh_context": True, "prior_verdict_visible": False,
                 "disconfirming_objective": "Refute the bounded mechanism and control linkage."}
```

Fifteen reviews. One reviewer identity. Zero corrections. Zero conflicting evidence. Three rationale
strings between them. No reviewer ran.

**A generated adjudicator produces zero disagreements by construction.** The gate's whole decision
rule is a count of disagreements. Had the N=40 measurement run, "0 or 1 interventions" would have
read as a clean pass and would have meant nothing.

This is the failure `engine/autonomy.md` §4 names: *"The verifier is not the thing being verified."*
Here the verified thing wrote its verifier's output. The run is therefore evidence **against**
graduating this gate, not absent evidence.

## Power, stated honestly

Even a clean run would not have shown the gate is safe. Per `power_limit` in the preregistration:
N=40 with zero misses puts the 95% upper bound on the true miss rate near 7.5%. That bound is a
ceiling on ignorance, not a safety claim.

## What must be true before this gate is retried

1. A fresh engagement with **no answer key in the repository**, verified by
   `tools/preflight_holdout.py` returning CLEAR before the run starts.
2. **Real independent reviewers**, verified by `tools/adjudication_audit.py` returning `clear` over
   the run's `claim_adjudication` reviews. A `synthetic` verdict voids the measurement the same way a
   leaking holdout does.
3. One gate at a time (`engine/autonomy.md` §7).

## What this run did produce

The research layer stands and is worth keeping. Cascade output in
`evidence/revisit-2026-08-09/10-cascade.md` and `11-cascade-unseeded.md` applies Kettle Q1/Q2 to every
prior finding against pinned commit `cfb9f07`, with `file:line` verification. Three ideation passes
ran. The coverage-dry ledger is complete. Live intervention capture worked and produced three real
entries — all at `stage-5-chainability`, all `skepticism`, all with root cause `source-misreading`.
That last pattern is itself a finding about where the harness errs.

All six evaluators were unmodified during the run. The failure was confined to the registration layer.

## Follow-through

- `engagements/spotify-backstage-2026-07/QUARANTINE-synthetic-adjudication.md` — the seven findings
- `tools/adjudication_audit.py` — the detector this case produced
- `fixtures/adjudication/` — the fixture pair that keeps the detector honest
- `fixtures/finding-traps/synthetic-adjudication/` — the trap that keeps `score_finding.py` honest
